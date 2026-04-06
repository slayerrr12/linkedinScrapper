import argparse
import asyncio
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from telegram import Bot, Update
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes

from .config import (
    DEFAULT_MAX_PROFILES,
    DEFAULT_SERPAPI_COUNTRY,
    DEFAULT_SERPAPI_GOOGLE_DOMAIN,
    DEFAULT_SERPAPI_LANGUAGE,
    ScraperConfig,
)
from .runner import run_scrape_job
from .utils import sanitize_filename_fragment


@dataclass(frozen=True)
class TelegramBotConfig:
    token: str
    serpapi_api_key: str
    google_domain: str
    language: str
    country: str
    output_dir: str
    default_max_profiles: int
    allowed_chat_ids: set[int]


@dataclass
class BotJobState:
    job_id: str
    query: str
    max_profiles: int
    status: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    total_links: int = 0
    output_paths: dict[str, Path] = field(default_factory=dict)
    error: Optional[str] = None


def parse_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default

    try:
        return int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer if it is set.") from exc


def parse_allowed_chat_ids(raw_value: str) -> set[int]:
    if not raw_value.strip():
        return set()
    return {int(part.strip()) for part in raw_value.split(",") if part.strip()}


def parse_bot_config() -> TelegramBotConfig:
    parser = argparse.ArgumentParser(description="Run the Telegram bot for background LinkedIn link scraping.")
    parser.add_argument(
        "--token",
        default=os.getenv("TELEGRAM_BOT_TOKEN"),
        help="Telegram bot token. Can also be provided via TELEGRAM_BOT_TOKEN.",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("SERPAPI_API_KEY", ""),
        help="SerpApi API key. Can also be provided via SERPAPI_API_KEY.",
    )
    parser.add_argument(
        "--google-domain",
        default=os.getenv("SERPAPI_GOOGLE_DOMAIN", DEFAULT_SERPAPI_GOOGLE_DOMAIN),
        help="Google domain used by SerpApi, for example google.com or google.co.in.",
    )
    parser.add_argument(
        "--hl",
        default=os.getenv("SERPAPI_HL", DEFAULT_SERPAPI_LANGUAGE),
        help="Google UI language for SerpApi, for example en.",
    )
    parser.add_argument(
        "--gl",
        default=os.getenv("SERPAPI_GL", DEFAULT_SERPAPI_COUNTRY),
        help="Google country code for SerpApi, for example in or us.",
    )
    parser.add_argument(
        "--output-dir",
        default=os.getenv("TELEGRAM_OUTPUT_DIR", "bot_runs"),
        help="Directory where bot-triggered exports will be stored.",
    )
    parser.add_argument(
        "--default-max-profiles",
        type=int,
        default=parse_int_env("TELEGRAM_DEFAULT_MAX_PROFILES", DEFAULT_MAX_PROFILES),
        help="Default max profile count when /scrape is called without a leading number.",
    )
    parser.add_argument(
        "--allowed-chat-ids",
        default=os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", ""),
        help="Comma-separated Telegram chat IDs allowed to use the bot. Leave empty to allow any chat.",
    )
    args = parser.parse_args()

    if not args.token:
        raise ValueError("Telegram bot token is required. Use --token or TELEGRAM_BOT_TOKEN.")
    if not args.api_key.strip():
        raise ValueError("A SerpApi API key is required. Use --api-key or set SERPAPI_API_KEY.")
    if args.default_max_profiles <= 0:
        raise ValueError("--default-max-profiles must be greater than 0.")

    return TelegramBotConfig(
        token=args.token,
        serpapi_api_key=args.api_key.strip(),
        google_domain=args.google_domain.strip() or DEFAULT_SERPAPI_GOOGLE_DOMAIN,
        language=args.hl.strip() or DEFAULT_SERPAPI_LANGUAGE,
        country=args.gl.strip().lower(),
        output_dir=args.output_dir,
        default_max_profiles=args.default_max_profiles,
        allowed_chat_ids=parse_allowed_chat_ids(args.allowed_chat_ids),
    )


class TelegramScraperBot:
    def __init__(self, config: TelegramBotConfig):
        self.config = config
        self.started_at = datetime.now(timezone.utc)
        self.active_jobs: dict[int, asyncio.Task] = {}
        self.job_states: dict[int, BotJobState] = {}
        self.latest_success: dict[int, BotJobState] = {}

    def build_application(self) -> Application:
        application = ApplicationBuilder().token(self.config.token).build()
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(CommandHandler("scrape", self.scrape_command))
        application.add_handler(CommandHandler("status", self.status_command))
        application.add_handler(CommandHandler("latest", self.latest_command))
        application.add_error_handler(self.error_handler)
        return application

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self.ensure_authorized(update):
            return
        await update.message.reply_text(
            "Telegram scraper bot is ready.\n"
            "Use /scrape <query> or /scrape <max_profiles> <query> to start a background job.\n"
            "Use /status to check progress and /latest to download the newest export files."
        )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self.ensure_authorized(update):
            return
        await update.message.reply_text(
            "Commands:\n"
            "/scrape <query> - start a scrape with the default max profile count\n"
            "/scrape <max_profiles> <query> - start a scrape with your chosen limit\n"
            "/status - show bot health, current job state, and latest completed job\n"
            "/latest - send the newest exported files for this chat"
        )

    async def scrape_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self.ensure_authorized(update):
            return

        chat_id = update.effective_chat.id
        existing_task = self.active_jobs.get(chat_id)
        if existing_task and not existing_task.done():
            await update.message.reply_text("A scrape job is already running for this chat. Use /status to check it.")
            return

        try:
            query, max_profiles = self.parse_scrape_command_args(context.args)
        except ValueError as exc:
            await update.message.reply_text(str(exc))
            return

        job_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        state = BotJobState(
            job_id=job_id,
            query=query,
            max_profiles=max_profiles,
            status="queued",
            started_at=datetime.now(timezone.utc),
        )
        self.job_states[chat_id] = state

        task = asyncio.create_task(self.run_background_job(chat_id, query, max_profiles, context.bot))
        self.active_jobs[chat_id] = task
        await update.message.reply_text(
            f"Started background scrape job {job_id}.\nQuery: {query}\nMax profiles: {max_profiles}"
        )

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self.ensure_authorized(update):
            return

        chat_id = update.effective_chat.id
        await update.message.reply_text(self.format_status_message(chat_id))

    async def latest_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self.ensure_authorized(update):
            return

        chat_id = update.effective_chat.id
        state = self.latest_success.get(chat_id)
        if state is None:
            await update.message.reply_text("No completed scrape is available yet for this chat.")
            return

        await update.message.reply_text(self.format_state(state))
        await self.send_output_files(context.bot, chat_id, state.output_paths)

    async def run_background_job(
        self,
        chat_id: int,
        query: str,
        max_profiles: int,
        bot: Bot,
    ) -> None:
        state = self.job_states[chat_id]
        state.status = "running"
        state.started_at = datetime.now(timezone.utc)

        output_base = self.build_output_base(query, state.job_id)
        scrape_config = ScraperConfig(
            query=query,
            max_profiles=max_profiles,
            output_base=str(output_base),
            serpapi_api_key=self.config.serpapi_api_key,
            google_domain=self.config.google_domain,
            language=self.config.language,
            country=self.config.country,
        )

        try:
            result = await asyncio.to_thread(run_scrape_job, scrape_config)
            state.status = "completed"
            state.finished_at = datetime.now(timezone.utc)
            state.total_links = result.total_links
            state.output_paths = result.paths
            self.latest_success[chat_id] = state

            await bot.send_message(
                chat_id=chat_id,
                text=(
                    f"Scrape job {state.job_id} completed.\n"
                    f"Query: {query}\n"
                    f"Total links: {result.total_links}"
                ),
            )
            await self.send_output_files(bot, chat_id, result.paths)
        except Exception as exc:
            state.status = "failed"
            state.finished_at = datetime.now(timezone.utc)
            state.error = str(exc)
            await bot.send_message(
                chat_id=chat_id,
                text=f"Scrape job {state.job_id} failed.\nError: {exc}",
            )
        finally:
            self.active_jobs.pop(chat_id, None)

    async def send_output_files(self, bot: Bot, chat_id: int, paths: dict[str, Path]) -> None:
        for label in ("json", "excel", "pdf"):
            path = paths.get(label)
            if path is None:
                continue
            with path.open("rb") as document:
                await bot.send_document(
                    chat_id=chat_id,
                    document=document,
                    filename=path.name,
                )

    async def ensure_authorized(self, update: Update) -> bool:
        if not self.config.allowed_chat_ids:
            return True

        chat_id = update.effective_chat.id
        if chat_id in self.config.allowed_chat_ids:
            return True

        await update.message.reply_text("This bot is not authorized for your chat ID.")
        return False

    def parse_scrape_command_args(self, args: list[str]) -> tuple[str, int]:
        if not args:
            raise ValueError(
                "Usage:\n"
                "/scrape <query>\n"
                "/scrape <max_profiles> <query>"
            )

        if args[0].isdigit():
            max_profiles = int(args[0])
            query = " ".join(args[1:]).strip()
            if not query:
                raise ValueError("Please provide a query after the max_profiles value.")
            return query, max_profiles

        return " ".join(args).strip(), self.config.default_max_profiles

    def build_output_base(self, query: str, job_id: str) -> Path:
        base_dir = Path(self.config.output_dir)
        base_dir.mkdir(parents=True, exist_ok=True)
        safe_query = sanitize_filename_fragment(query)
        return base_dir / f"{job_id}_{safe_query}"

    def format_state(self, state: BotJobState) -> str:
        lines = [
            f"Job ID: {state.job_id}",
            f"Status: {state.status}",
            f"Query: {state.query}",
            f"Max profiles: {state.max_profiles}",
            f"Started: {state.started_at.astimezone().strftime('%Y-%m-%d %H:%M:%S')}",
        ]

        if state.finished_at is not None:
            lines.append(f"Finished: {state.finished_at.astimezone().strftime('%Y-%m-%d %H:%M:%S')}")
        if state.total_links:
            lines.append(f"Total links: {state.total_links}")
        if state.error:
            lines.append(f"Error: {state.error}")

        return "\n".join(lines)

    def format_status_message(self, chat_id: int) -> str:
        current_state = self.job_states.get(chat_id)
        latest_state = self.latest_success.get(chat_id)

        lines = [
            "Bot status: online",
            f"Uptime: {self.format_duration(datetime.now(timezone.utc) - self.started_at)}",
            f"Default max profiles: {self.config.default_max_profiles}",
        ]

        location_bits = [self.config.google_domain, self.config.language]
        if self.config.country:
            location_bits.append(self.config.country)
        lines.append(f"Search config: {', '.join(location_bits)}")

        if current_state is None:
            lines.append("Current job: idle")
        else:
            lines.append("")
            lines.append("Current job:")
            lines.append(self.format_state(current_state))
            if current_state.status in {"queued", "running"}:
                elapsed = datetime.now(timezone.utc) - current_state.started_at
                lines.append(f"Elapsed: {self.format_duration(elapsed)}")

        if latest_state is not None and latest_state is not current_state:
            lines.append("")
            lines.append("Latest completed job:")
            lines.append(self.format_state(latest_state))

        return "\n".join(lines)

    @staticmethod
    def format_duration(duration) -> str:
        total_seconds = max(int(duration.total_seconds()), 0)
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        parts: list[str] = []
        if hours:
            parts.append(f"{hours}h")
        if minutes or hours:
            parts.append(f"{minutes}m")
        parts.append(f"{seconds}s")
        return " ".join(parts)

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        print(f"Telegram bot error: {context.error}")


def run_telegram_bot() -> None:
    config = parse_bot_config()
    bot = TelegramScraperBot(config)
    application = bot.build_application()
    application.run_polling()
