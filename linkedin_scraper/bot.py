import argparse
import asyncio
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from telegram import Bot, Update
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes

from .config import DEFAULT_CHALLENGE_TIMEOUT, DEFAULT_MAX_PROFILES, ScraperConfig
from .runner import run_scrape_job
from .utils import sanitize_filename_fragment


@dataclass(frozen=True)
class TelegramBotConfig:
    token: str
    output_dir: str
    default_max_profiles: int
    headless: bool
    challenge_timeout: int
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


def parse_bool_env(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default

    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False

    raise ValueError(f"{name} must be a boolean string such as true/false if it is set.")


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
        "--headless",
        action=argparse.BooleanOptionalAction,
        default=parse_bool_env("TELEGRAM_HEADLESS", True),
        help="Run scraping jobs in headless Chrome.",
    )
    parser.add_argument(
        "--challenge-timeout",
        type=int,
        default=parse_int_env("TELEGRAM_CHALLENGE_TIMEOUT", DEFAULT_CHALLENGE_TIMEOUT),
        help="Seconds to wait when a manual verification step appears.",
    )
    parser.add_argument(
        "--allowed-chat-ids",
        default=os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", ""),
        help="Comma-separated Telegram chat IDs allowed to use the bot. Leave empty to allow any chat.",
    )
    args = parser.parse_args()

    if not args.token:
        raise ValueError("Telegram bot token is required. Use --token or TELEGRAM_BOT_TOKEN.")
    if args.default_max_profiles <= 0:
        raise ValueError("--default-max-profiles must be greater than 0.")
    if args.challenge_timeout <= 0:
        raise ValueError("--challenge-timeout must be greater than 0.")

    return TelegramBotConfig(
        token=args.token,
        output_dir=args.output_dir,
        default_max_profiles=args.default_max_profiles,
        headless=args.headless,
        challenge_timeout=args.challenge_timeout,
        allowed_chat_ids=parse_allowed_chat_ids(args.allowed_chat_ids),
    )


class TelegramScraperBot:
    def __init__(self, config: TelegramBotConfig):
        self.config = config
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
            "/scrape <query>\n"
            "/scrape <max_profiles> <query>\n"
            "/status\n"
            "/latest"
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
        state = self.job_states.get(chat_id)
        if state is None:
            await update.message.reply_text("No job has been started in this chat yet.")
            return

        await update.message.reply_text(self.format_state(state))

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
            headless=self.config.headless,
            challenge_timeout=self.config.challenge_timeout,
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

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        print(f"Telegram bot error: {context.error}")


def run_telegram_bot() -> None:
    config = parse_bot_config()
    bot = TelegramScraperBot(config)
    application = bot.build_application()
    application.run_polling()
