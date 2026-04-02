# LinkedIn Link Scraper

This project searches Google for LinkedIn profile links and exports the collected URLs to:

- `JSON`
- `Excel`
- clickable `PDF`

Run the script with:

```powershell
venv\Scripts\python.exe profile_scrap_new.py
```

At startup, a small GUI prompt lets you change the search query and the maximum number of links to collect.

## Telegram Bot

There is also a Telegram bot entrypoint now:

```powershell
venv\Scripts\python.exe telegram_scraper_bot.py --token <your-bot-token>
```

Commands:

- `/start`
- `/help`
- `/scrape <query>`
- `/scrape <max_profiles> <query>`
- `/status`
- `/latest`

Bot-triggered export files are stored under `bot_runs/`.

Note: the bot runs scraping jobs in headless Chrome by default. If Google serves a CAPTCHA or manual verification page, that background job can fail because there is no interactive browser window to solve it in.

For full VPS deployment instructions, see [DEPLOY_TELEGRAM_BOT.md](/D:/linkedinScrapper/DEPLOY_TELEGRAM_BOT.md).

For Railway deployment, see [DEPLOY_RAILWAY.md](/D:/linkedinScrapper/DEPLOY_RAILWAY.md).
