# Cloudflare Domain Catcher

A small Python monitor that checks a domain's availability through Cloudflare Registrar and, when it becomes available, can submit a single registration request after enforcing price and safety checks.

> **Warning:** Running without `--sandbox` may result in a real, billable domain registration. Review your configuration carefully before using production mode.

## What it does

- Polls Cloudflare for a domain's availability.
- Rejects non-standard tiers, unexpected currencies, and prices above your limit.
- Verifies the returned domain matches the domain requested.
- Stops after submitting a registration to avoid duplicate purchases.
- Includes a Cloudflare Registrar Sandbox mode for end-to-end testing without a real registration.

## Requirements

- Python 3.10 or newer (Python 3.11–3.13 recommended)
- A Cloudflare account with Registrar access
- A Cloudflare API token with the required Registrar permissions

## Setup

Clone the repository, then create your private local configuration:

```bash
cp config.example.py config.py
```

Edit `config.py` with your Cloudflare account ID, API token, domain, maximum price, and sandbox contact information. This file is excluded from Git and must never be committed.

Create and activate a virtual environment, then install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

If the standard virtual-environment setup has certificate issues on macOS, `uv` is an alternative:

```bash
brew install uv
uv venv --python 3.13
source .venv/bin/activate
uv pip install -r requirements.txt
```

## Test safely

Run the sandbox flow first:

```bash
python domain_catcher.py --sandbox
```

Successful output ends with `SANDBOX TEST PASSED`. Sandbox requests do not register a real domain or charge money.

## Telegram alerts

Create a bot through [@BotFather](https://t.me/BotFather), open the bot, and send `/start`. Then add its token and your chat ID to your private `config.py`:

```python
TELEGRAM_BOT_TOKEN = "your_bot_token"
TELEGRAM_CHAT_ID = "your_chat_id"
STATUS_INTERVAL_SECONDS = 3600
```

The monitor sends a startup notice, a heartbeat every hour while the domain remains unavailable, and an immediate notification when it attempts or completes a registration. If the computer is offline, Telegram messages and availability checks resume once the connection returns.

## Run automatically on macOS

For restart-at-login and automatic recovery after an unexpected exit, install the included LaunchAgent after you have created `.venv` and tested Telegram:

```bash
./install_macos_launch_agent.sh
```

It starts after you log in and restarts the monitor if it exits. A laptop cannot run the monitor while asleep, powered off, or disconnected; use an always-on server if uninterrupted monitoring is required.

## Production mode

Only after confirming your settings and completing a sandbox test:

```bash
python domain_catcher.py
```

The program will keep checking the configured domain. If Cloudflare reports it as registrable, the script validates the domain name, tier, currency, and price before sending one registration request.

## Security

- Keep `config.py` private. It contains API credentials and may include personal contact details.
- Use a least-privilege Cloudflare API token and revoke it immediately if it is ever exposed.
- Do not paste tokens into issues, pull requests, logs, or screenshots.
- Set a conservative `MAX_PRICE_USD`; the program will refuse a higher price.

## Disclaimer

This project is provided as-is. You are responsible for verifying Cloudflare's current API requirements, your account permissions, and all registration details before use.
