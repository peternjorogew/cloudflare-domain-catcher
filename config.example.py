CLOUDFLARE_ACCOUNT_ID = "your_account_id_here"
CLOUDFLARE_API_TOKEN = "your_api_token_here"

DOMAIN = "example.com"

# Maximum price the script is allowed to pay.
MAX_PRICE_USD = 50.00

# Seconds between availability checks.
CHECK_INTERVAL_SECONDS = 3

AUTO_RENEW = True
PRIVACY_MODE = "redaction"

# Telegram alerts. Create a bot with @BotFather, send it /start, then fill in
# the token and your private chat ID. Leave both values empty to disable alerts.
TELEGRAM_BOT_TOKEN = ""
TELEGRAM_CHAT_ID = ""

# Send a heartbeat while the monitor is running.
STATUS_INTERVAL_SECONDS = 3600


# ---------------------------------------------------------
# SANDBOX SETTINGS
# ---------------------------------------------------------

SANDBOX_TEST_DOMAIN = "test-example.com"

SANDBOX_CONTACT = {
    "email": "you@example.com",

    # Cloudflare expects international format.
    # Example:
    # +49.1701234567
    "phone": "+49.1701234567",

    "name": "John Doe",

    "street": "Example Street 1",
    "city": "Berlin",
    "state": "Berlin",
    "postal_code": "10115",
    "country_code": "DE",
}
