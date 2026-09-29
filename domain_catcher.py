import argparse
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation

import requests

# Load private user configuration.
# config.py is ignored by Git and should never be committed.
try:
    from config import (
        CLOUDFLARE_ACCOUNT_ID,
        CLOUDFLARE_API_TOKEN,
        DOMAIN,
        MAX_PRICE_USD,
        CHECK_INTERVAL_SECONDS,
        AUTO_RENEW,
        PRIVACY_MODE,
        TELEGRAM_BOT_TOKEN,
        TELEGRAM_CHAT_ID,
        STATUS_INTERVAL_SECONDS,
        SANDBOX_TEST_DOMAIN,
        SANDBOX_CONTACT,
    )
except ImportError:
    raise SystemExit(
        "\nMissing config.py\n\n"
        "Copy config.example.py to config.py and fill in your settings:\n"
        "    cp config.example.py config.py\n"
    )


def log(message: str) -> None:
    """Print a timestamped log message."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)


class TelegramNotifier:
    """Send best-effort status alerts without interrupting registration."""

    def __init__(self) -> None:
        self.enabled = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)
        self.url = (
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        )

    def send(self, message: str) -> None:
        if not self.enabled:
            return

        try:
            response = requests.post(
                self.url,
                json={"chat_id": TELEGRAM_CHAT_ID, "text": message},
                timeout=15,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            # Alerts must never block or duplicate a registration attempt.
            log(f"Telegram notification failed: {type(exc).__name__}")


def parse_args():
    """Read command-line options such as --sandbox."""
    parser = argparse.ArgumentParser(
        description=(
            "Monitor and automatically register a domain "
            "using Cloudflare Registrar."
        )
    )

    parser.add_argument(
        "--sandbox",
        action="store_true",
        help=(
            "Use Cloudflare Registrar Sandbox. "
            "No real domain is registered and no money is charged."
        ),
    )

    return parser.parse_args()


def validate_config(sandbox: bool) -> None:
    """
    Make sure required configuration values exist before
    we start making requests to Cloudflare.
    """

    if not CLOUDFLARE_ACCOUNT_ID:
        raise ValueError("CLOUDFLARE_ACCOUNT_ID is empty.")

    if not CLOUDFLARE_API_TOKEN:
        raise ValueError("CLOUDFLARE_API_TOKEN is empty.")

    if not DOMAIN:
        raise ValueError("DOMAIN is empty.")

    if CHECK_INTERVAL_SECONDS < 1:
        raise ValueError(
            "CHECK_INTERVAL_SECONDS must be at least 1 second."
        )

    if STATUS_INTERVAL_SECONDS < 60:
        raise ValueError("STATUS_INTERVAL_SECONDS must be at least 60 seconds.")

    # Decimal is used instead of float for safer money comparisons.
    try:
        Decimal(str(MAX_PRICE_USD))
    except InvalidOperation as exc:
        raise ValueError(
            "MAX_PRICE_USD must be a valid number."
        ) from exc

    # Sandbox registrations require contact data explicitly.
    if sandbox:
        if not SANDBOX_TEST_DOMAIN:
            raise ValueError("SANDBOX_TEST_DOMAIN is empty.")

        required_contact_fields = [
            "email",
            "phone",
            "name",
            "street",
            "city",
            "state",
            "postal_code",
            "country_code",
        ]

        for field in required_contact_fields:
            if not SANDBOX_CONTACT.get(field):
                raise ValueError(
                    f"SANDBOX_CONTACT is missing required field: {field}"
                )


class CloudflareRegistrar:
    """
    Small wrapper around Cloudflare's Registrar API.

    It automatically switches between the sandbox and
    production endpoints.
    """

    def __init__(self, sandbox: bool):
        self.sandbox = sandbox

        registrar_path = (
            "registrar-sandbox"
            if sandbox
            else "registrar"
        )

        self.base_url = (
            f"https://api.cloudflare.com/client/v4/accounts/"
            f"{CLOUDFLARE_ACCOUNT_ID}/{registrar_path}"
        )

        # Every Cloudflare API request uses the same headers.
        self.headers = {
            "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
            "Content-Type": "application/json",
        }

    def check_domain(self, domain: str) -> dict:
        """
        Ask Cloudflare whether the domain is currently registrable.

        This check does not purchase anything.
        """

        response = requests.post(
            f"{self.base_url}/domain-check",
            headers=self.headers,
            json={
                "domains": [domain]
            },
            timeout=15,
        )

        # Raises an exception for HTTP errors such as 401 or 500.
        response.raise_for_status()

        data = response.json()

        if not data.get("success"):
            raise RuntimeError(
                f"Cloudflare availability check failed: "
                f"{data.get('errors', data)}"
            )

        domains = data.get("result", {}).get("domains", [])

        if not domains:
            raise RuntimeError(
                "Cloudflare returned no domain availability information."
            )

        return domains[0]

    def register_domain(self, domain: str) -> dict:
        """
        Submit a domain registration request.

        In production mode this is a REAL, billable operation.
        """

        payload = {
            "domain_name": domain,
            "auto_renew": AUTO_RENEW,
            "privacy_mode": PRIVACY_MODE,
        }

        # The sandbox does not automatically use the account's
        # saved default registrant contact, so we include it here.
        if self.sandbox:
            payload["contacts"] = {
                "registrant": {
                    "email": SANDBOX_CONTACT["email"],
                    "phone": SANDBOX_CONTACT["phone"],
                    "postal_info": {
                        "name": SANDBOX_CONTACT["name"],
                        "address": {
                            "street": SANDBOX_CONTACT["street"],
                            "city": SANDBOX_CONTACT["city"],
                            "state": SANDBOX_CONTACT["state"],
                            "postal_code": SANDBOX_CONTACT["postal_code"],
                            "country_code": SANDBOX_CONTACT["country_code"],
                        },
                    },
                }
            }

        response = requests.post(
            f"{self.base_url}/registrations",
            headers=self.headers,
            json=payload,
            timeout=30,
        )

        response.raise_for_status()

        return response.json()


def validate_registration_candidate(
    domain_info: dict,
    expected_domain: str
) -> Decimal:
    """
    Run all safety checks before allowing a purchase.

    Returns the registration price if everything is valid.
    """

    returned_domain = domain_info.get("name")

    # Prevent accidentally buying a different domain.
    if returned_domain != expected_domain:
        raise RuntimeError(
            f"Domain mismatch: expected {expected_domain}, "
            f"Cloudflare returned {returned_domain}"
        )

    if not domain_info.get("registrable", False):
        raise RuntimeError(
            "Registration validation called for a domain "
            "that is not registrable."
        )

    # Reject premium or unexpected pricing tiers.
    tier = domain_info.get("tier")

    if tier != "standard":
        raise RuntimeError(
            f"Refusing registration because domain tier is "
            f"'{tier}', not 'standard'."
        )

    pricing = domain_info.get("pricing")

    if not pricing:
        raise RuntimeError(
            "Cloudflare did not return pricing information."
        )

    currency = pricing.get("currency")

    # Our price limit is configured in USD.
    if currency != "USD":
        raise RuntimeError(
            f"Unexpected currency '{currency}'. "
            "Automatic purchase cancelled."
        )

    registration_cost = pricing.get("registration_cost")

    if registration_cost is None:
        raise RuntimeError(
            "Cloudflare did not return a registration cost."
        )

    try:
        price = Decimal(str(registration_cost))
    except InvalidOperation as exc:
        raise RuntimeError(
            f"Invalid registration price returned: {registration_cost}"
        ) from exc

    max_price = Decimal(str(MAX_PRICE_USD))

    # Never buy if Cloudflare reports a price above the configured limit.
    if price > max_price:
        raise RuntimeError(
            f"Registration price ${price} exceeds configured "
            f"maximum of ${max_price}."
        )

    return price


def run_sandbox(
    registrar: CloudflareRegistrar,
    notifier: TelegramNotifier,
) -> None:
    """
    Test the full check -> validate -> register flow safely.

    Cloudflare sandbox does not register a real domain.
    """

    # Generate a unique sandbox domain for every test run.
    # This prevents previous sandbox registrations from making
    # the test domain unavailable on future runs.
    timestamp = int(time.time())

    domain = f"{SANDBOX_TEST_DOMAIN}-{timestamp}.com"

    log("=" * 60)
    log("SANDBOX MODE")
    log("=" * 60)
    log("No real domain will be registered.")
    log("No money will be charged.")
    notifier.send("Domain Catcher sandbox test started. No real domain will be registered.")
    log(f"Testing domain: {domain}")
    log("")

    # First verify the sandbox domain is available.
    info = registrar.check_domain(domain)

    log(f"Registrable: {info.get('registrable')}")
    log(f"Tier: {info.get('tier')}")

    if not info.get("registrable", False):
        raise RuntimeError(
            f"Sandbox domain {domain} is not registrable."
        )

    # Run the exact same safety checks used in production.
    price = validate_registration_candidate(
        info,
        domain
    )

    log(f"Sandbox registration price: ${price}")
    log("Submitting sandbox registration...")

    result = registrar.register_domain(domain)

    log(
        "Cloudflare sandbox response received "
        f"(success={result.get('success')})."
    )

    if not result.get("success"):
        raise RuntimeError(
            f"Sandbox registration failed: "
            f"{result.get('errors', result)}"
        )

    registration_result = result.get("result", {})
    state = registration_result.get("state")

    if state == "succeeded":
        log("")
        log("=" * 60)
        log("SANDBOX TEST PASSED")
        log("=" * 60)
        notifier.send("Domain Catcher sandbox test passed.")
        return

    raise RuntimeError(
        f"Sandbox registration did not succeed. State: {state}"
    )


def run_production(
    registrar: CloudflareRegistrar,
    notifier: TelegramNotifier,
) -> None:
    """
    Continuously monitor the real domain.

    Once it becomes available, the script validates the price
    and submits exactly one registration request.
    """

    domain = DOMAIN

    log("=" * 60)
    log("PRODUCTION MODE")
    log("=" * 60)

    log(f"Watching: {domain}")
    log(f"Maximum registration price: ${MAX_PRICE_USD}")
    log(f"Check interval: {CHECK_INTERVAL_SECONDS} seconds")
    log(f"Auto-renew: {AUTO_RENEW}")
    log(f"Privacy mode: {PRIVACY_MODE}")
    log("")

    log(
        "WARNING: If the domain becomes available and passes "
        "all safety checks, this script will attempt a REAL purchase."
    )

    log("")
    log("Press Ctrl+C to stop.")
    log("")

    notifier.send(
        f"Domain Catcher started for {domain}. "
        f"I will report status every {STATUS_INTERVAL_SECONDS // 60} minutes."
    )
    next_status_at = time.monotonic() + STATUS_INTERVAL_SECONDS
    last_status = "starting"

    while True:
        if time.monotonic() >= next_status_at:
            notifier.send(
                f"Still monitoring {domain}. Last status: {last_status}."
            )
            next_status_at = time.monotonic() + STATUS_INTERVAL_SECONDS

        try:
            # Poll Cloudflare until the domain becomes registrable.
            domain_info = registrar.check_domain(domain)

            if not domain_info.get("registrable", False):
                reason = domain_info.get(
                    "reason",
                    "domain unavailable"
                )
                last_status = f"unavailable ({reason})"

                log(
                    f"{domain} unavailable "
                    f"({reason})"
                )

                time.sleep(CHECK_INTERVAL_SECONDS)
                continue

            # --------------------------------------------------
            # Domain has become available
            # --------------------------------------------------

            log("")
            log("!" * 60)
            log(f"{domain} IS NOW REGISTRABLE!")
            log("!" * 60)

            # Verify domain, tier, currency, and price before buying.
            price = validate_registration_candidate(
                domain_info,
                domain
            )

            log(f"Tier: {domain_info.get('tier')}")
            log(f"Registration price: ${price}")
            log(
                f"Price is within configured limit "
                f"(${MAX_PRICE_USD})."
            )

            log("")
            log("Submitting REAL registration request NOW...")
            notifier.send(
                f"{domain} is registrable and passed safety checks. "
                f"Submitting registration at ${price}."
            )

            # This is the only place where the real purchase is attempted.
            registration = registrar.register_domain(domain)

            log("")
            log(
                "Cloudflare registration response received "
                f"(success={registration.get('success')})."
            )

            if not registration.get("success"):
                log("REGISTRATION FAILED.")
                log(
                    f"Errors: "
                    f"{registration.get('errors', [])}"
                )

                # Do not blindly retry a potentially billable operation.
                log(
                    "Stopping to avoid duplicate billable "
                    "registration attempts."
                )
                notifier.send(
                    f"Registration attempt for {domain} failed. "
                    "The monitor stopped to prevent duplicate charges."
                )

                return

            result = registration.get("result", {})

            state = result.get("state")
            completed = result.get("completed")

            if state == "succeeded":
                log("")
                log("=" * 60)
                log("SUCCESS!")
                log(f"{domain} was registered successfully.")
                log("=" * 60)
                notifier.send(f"SUCCESS: {domain} was registered successfully.")
                return

            if completed is True:
                log(
                    f"Registration completed with state: {state}"
                )
                notifier.send(
                    f"Registration for {domain} completed with state: {state}."
                )
                return

            # Cloudflare accepted the request but may still be processing it.
            log(
                f"Registration submitted. Current state: {state}"
            )

            log(
                "Stopping to avoid duplicate billable requests."
            )
            notifier.send(
                f"Registration for {domain} was submitted with state: {state}. "
                "The monitor stopped to prevent duplicate charges."
            )

            return

        except KeyboardInterrupt:
            # Allows Ctrl+C to shut down cleanly.
            log("")
            log("Stopped by user.")
            return

        except requests.exceptions.Timeout:
            last_status = "Cloudflare request timed out; retrying"
            log(
                "Cloudflare request timed out. "
                "Retrying availability check."
            )

        except requests.exceptions.ConnectionError:
            last_status = "network connection error; retrying"
            log(
                "Network connection error. "
                "Retrying availability check."
            )

        except requests.exceptions.HTTPError as exc:
            status_code = None

            if exc.response is not None:
                status_code = exc.response.status_code

            log(
                f"HTTP error from Cloudflare "
                f"(status={status_code}): {exc}"
            )
            last_status = f"Cloudflare HTTP error (status={status_code}); retrying"

            # Slow down if Cloudflare rate-limits the script.
            if status_code == 429:
                log(
                    "Rate limit reached. "
                    "Waiting 60 seconds."
                )

                time.sleep(60)
                continue

        except RuntimeError as exc:
            log(f"Safety/API error: {exc}")
            last_status = f"Cloudflare safety/API error; retrying"

            message = str(exc)

            # These errors are intentionally fatal.
            # We do not want the program to keep trying after them.
            fatal_conditions = [
                "Refusing registration",
                "exceeds configured maximum",
                "Unexpected currency",
                "Domain mismatch",
            ]

            if any(
                condition in message
                for condition in fatal_conditions
            ):
                log("Fatal safety condition reached. Stopping.")
                notifier.send(
                    f"Monitoring {domain} stopped for safety: {message}"
                )
                return

        except Exception as exc:
            last_status = f"unexpected {type(exc).__name__}; retrying"
            # Catch unexpected errors so one temporary issue
            # does not immediately kill the monitor.
            log(
                f"Unexpected error: "
                f"{type(exc).__name__}: {exc}"
            )

        time.sleep(CHECK_INTERVAL_SECONDS)


def main() -> None:
    """Program entry point."""
    args = parse_args()

    validate_config(args.sandbox)

    # Create either a sandbox or production API client.
    registrar = CloudflareRegistrar(
        sandbox=args.sandbox
    )
    notifier = TelegramNotifier()

    if args.sandbox:
        run_sandbox(registrar, notifier)
    else:
        run_production(registrar, notifier)


if __name__ == "__main__":
    main()
