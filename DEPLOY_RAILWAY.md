# Deploy The Telegram Bot On Railway

This repo is now set up so Railway can deploy it directly from GitHub with the included `Dockerfile`.

## Before You Deploy

1. Regenerate your Telegram bot token in `@BotFather`.
   You pasted the old token into chat, so treat it as exposed and replace it before using the bot in production.
2. Send `/start` to your bot in Telegram.
3. Get your Telegram chat ID.
   An easy way is to message `@userinfobot`, or call the Bot API `getUpdates` endpoint after sending `/start` to your bot.

## Railway Setup

1. Push your latest code to GitHub.
2. Sign in at Railway and create a new project.
3. Choose `Deploy from GitHub repo`.
4. Select `slayerrr12/linkedinScrapper`.
5. Railway will detect the `Dockerfile` and build the container automatically.

## Required Railway Variables

Add these in the Railway service `Variables` tab:

```text
TELEGRAM_BOT_TOKEN=your_new_bot_token
TELEGRAM_ALLOWED_CHAT_IDS=your_numeric_chat_id
TELEGRAM_HEADLESS=true
TELEGRAM_DEFAULT_MAX_PROFILES=25
TELEGRAM_CHALLENGE_TIMEOUT=600
```

Optional:

```text
TELEGRAM_OUTPUT_DIR=/data/bot_runs
```

Use `TELEGRAM_OUTPUT_DIR=/data/bot_runs` only if you attach a Railway volume in the next step.

## Optional Volume

Railway service storage is ephemeral by default. That is fine if you only need the bot to send files back to Telegram immediately.

If you want generated files to survive redeploys or restarts:

1. Open the service in Railway.
2. Add a volume.
3. Mount it at `/data`.
4. Set `TELEGRAM_OUTPUT_DIR=/data/bot_runs`.

## Deploy And Run

1. Click `Deploy`.
2. Wait for the first build to finish.
3. Open `Deployments` or `Logs` and confirm the bot starts without errors.

You do not need to expose a public port or add a domain for this bot, because it uses Telegram long polling instead of incoming webhooks.

## Test The Bot

Open Telegram and run:

```text
/start
/scrape 10 iit guwahati mtech cse
/status
/latest
```

## Updating Later

Push to the connected GitHub branch again and Railway will rebuild and redeploy automatically.

## Important Limitation

This bot runs headless on Railway. If Google presents a CAPTCHA or manual verification page, that job can fail because there is no visible browser window to solve it.
