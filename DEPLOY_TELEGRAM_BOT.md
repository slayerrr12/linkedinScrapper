# Deploy Telegram Bot

This guide shows the easiest path to:

1. Create a Telegram bot
2. Get the bot token
3. Restrict usage to your own Telegram chat
4. Deploy the bot on a Linux VPS
5. Keep it running permanently with `systemd`

## 1. Create the bot in Telegram

Telegram's official bot setup flow is through [@BotFather](https://t.me/BotFather).

Steps:

1. Open Telegram.
2. Search for `@BotFather`.
3. Open the chat and send `/start`.
4. Send `/newbot`.
5. Enter a display name for the bot.
6. Enter a username for the bot.
   The username must end with `bot`, for example `linkedin_scraper_bot`.
7. BotFather will send you a bot token.

Keep that token private. Anyone with the token can control your bot.

Official references:

- [Telegram Bot Features](https://core.telegram.org/bots/features)
- [From BotFather to "Hello World"](https://core.telegram.org/bots/tutorial)

## 2. Start the bot once in Telegram

1. Open your new bot in Telegram.
2. Press `Start` or send `/start`.

This creates a chat with the bot, which you will use later for commands like `/scrape`, `/status`, and `/latest`.

## 3. Get your Telegram chat ID

The simplest official way is:

1. Send `/start` to your bot.
2. Open this URL in your browser after replacing `<TOKEN>`:

```text
https://api.telegram.org/bot<TOKEN>/getUpdates
```

3. Look for:

```json
"chat": {
  "id": 123456789,
  ...
}
```

That `id` is your personal chat ID. You can use it to lock the bot to your account only.

Official reference:

- [Telegram Bot API](https://core.telegram.org/bots/api)

## 4. Create a VPS

Any Linux VPS is fine. Ubuntu 22.04 or 24.04 is the easiest path.

Suggested minimum:

- 2 GB RAM
- 2 vCPU
- Ubuntu LTS

## 5. SSH into the VPS

Example:

```bash
ssh your-user@your-server-ip
```

## 6. Install system packages

On Ubuntu:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip
```

## 7. Clone the repository

If the repo is public:

```bash
cd /opt
sudo git clone https://github.com/slayerrr12/linkedinScrapper.git
sudo chown -R $USER:$USER /opt/linkedinScrapper
cd /opt/linkedinScrapper
```

If the repo is private, clone it with a GitHub token or SSH key instead.

## 8. Create the Python environment

```bash
cd /opt/linkedinScrapper
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 9. Create the bot environment file

Copy the example file:

```bash
cp deploy/systemd/telegram-scraper-bot.env.example deploy/systemd/telegram-scraper-bot.env
```

Edit it:

```bash
nano deploy/systemd/telegram-scraper-bot.env
```

Set these values:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_ALLOWED_CHAT_IDS`

Example:

```bash
TELEGRAM_BOT_TOKEN=123456789:AA...
TELEGRAM_ALLOWED_CHAT_IDS=123456789
```

If you want multiple allowed chats, separate them with commas.

## 10. Test the bot manually

Run this first before enabling the service:

```bash
cd /opt/linkedinScrapper
source venv/bin/activate
set -a
source deploy/systemd/telegram-scraper-bot.env
set +a
python telegram_scraper_bot.py --allowed-chat-ids "$TELEGRAM_ALLOWED_CHAT_IDS"
```

Now open Telegram and send:

```text
/start
```

Then try:

```text
/scrape 10 mit computer science
```

If it works, stop the process with `Ctrl+C`.

## 11. Install the systemd service

Copy the example service:

```bash
sudo cp deploy/systemd/telegram-scraper-bot.service.example /etc/systemd/system/telegram-scraper-bot.service
```

Edit it:

```bash
sudo nano /etc/systemd/system/telegram-scraper-bot.service
```

Check these values:

- `User=ubuntu`
- `WorkingDirectory=/opt/linkedinScrapper`
- `EnvironmentFile=/opt/linkedinScrapper/deploy/systemd/telegram-scraper-bot.env`
- `ExecStart=/opt/linkedinScrapper/venv/bin/python /opt/linkedinScrapper/telegram_scraper_bot.py ...`

Change `User=ubuntu` if your Linux username is different.

## 12. Enable and start the service

```bash
sudo systemctl daemon-reload
sudo systemctl enable telegram-scraper-bot
sudo systemctl start telegram-scraper-bot
```

## 13. Check logs

```bash
sudo systemctl status telegram-scraper-bot
sudo journalctl -u telegram-scraper-bot -f
```

## 14. How you will use it day to day

After deployment, you only need Telegram.

Commands:

- `/start`
- `/help`
- `/scrape <query>`
- `/scrape <max_profiles> <query>`
- `/status`
- `/latest`

Examples:

```text
/scrape mit computer science
```

```text
/scrape 25 stanford ai researchers
```

```text
/status
```

```text
/latest
```

## 15. How to update the bot later

SSH into the VPS and run:

```bash
cd /opt/linkedinScrapper
git pull
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart telegram-scraper-bot
```

## 16. Important limitation

This bot currently scrapes Google search results in headless Chrome. If Google serves a CAPTCHA or another manual verification page, the background job may fail because there is no interactive browser window on a typical VPS.

That means:

- normal runs can work fine
- challenge pages can interrupt some jobs
- this is a scraping reliability issue, not a Telegram issue

## Files added for deployment

- [deploy/systemd/telegram-scraper-bot.env.example](/D:/linkedinScrapper/deploy/systemd/telegram-scraper-bot.env.example)
- [deploy/systemd/telegram-scraper-bot.service.example](/D:/linkedinScrapper/deploy/systemd/telegram-scraper-bot.service.example)
