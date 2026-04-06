# LinkedIn Link Scraper

This project searches for LinkedIn profile links through SerpApi and exports the collected URLs to:

- `JSON`
- `Excel`
- clickable `PDF`

Run the script with:

```powershell
set SERPAPI_API_KEY=your_api_key
venv\Scripts\python.exe profile_scrap_new.py
```

At startup, a small GUI prompt lets you change the search query and the maximum number of links to collect.

The CLI and Telegram bot both require a `SERPAPI_API_KEY`.

## Telegram Bot

There is also a Telegram bot entrypoint now:

```powershell
venv\Scripts\python.exe telegram_scraper_bot.py --token <your-bot-token> --api-key <your-serpapi-key>
```

Commands:

- `/start`
- `/help`
- `/scrape <query>`
- `/scrape <max_profiles> <query>`
- `/status` shows bot health, uptime, current job state, and latest completed job
- `/latest`

Bot-triggered export files are stored under `bot_runs/`.

For full VPS deployment instructions, see [DEPLOY_TELEGRAM_BOT.md](/D:/linkedinScrapper/DEPLOY_TELEGRAM_BOT.md).

For Railway deployment, see [DEPLOY_RAILWAY.md](/D:/linkedinScrapper/DEPLOY_RAILWAY.md).
