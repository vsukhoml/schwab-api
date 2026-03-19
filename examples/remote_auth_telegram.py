import os
import time
import sys

try:
    import telebot
except ImportError:
    print("Please install pyTelegramBotAPI to run this example:")
    print("pip install pyTelegramBotAPI")
    sys.exit(1)

from schwab_api.client import Client
from schwab_api.exceptions import AuthError

# Replace with your actual Telegram Bot Token and Chat ID
# You can get a Bot Token from @BotFather on Telegram.
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID")

APP_KEY = os.getenv("SCHWAB_APP_KEY", "YOUR_APP_KEY")
APP_SECRET = os.getenv("SCHWAB_APP_SECRET", "YOUR_APP_SECRET")


def telegram_auth_flow(auth_url: str, callback_url: str) -> str:
    """
    A custom authentication hook that signals the user via Telegram when a manual
    login is required (e.g. refresh token expired after 7 days).

    It supports two workflows:
    1. Pasting the redirect URL back into Telegram.
    2. Updating tokens locally and SCPing the tokens.json file to the server.
    """
    if BOT_TOKEN == "YOUR_BOT_TOKEN" or CHAT_ID == "YOUR_CHAT_ID":
        print(f"\n[Fallback Console] Login required:\n{auth_url}")
        return input(f"Paste redirect URL starting with {callback_url}: ")

    bot = telebot.TeleBot(BOT_TOKEN)

    msg = (
        "🚨 *Schwab API Login Required!*\n\n"
        "*Option 1 (Direct URL):*\n"
        f"Open this link locally:\n`{auth_url}`\n"
        "After logging in, paste the full localhost redirect URL here.\n\n"
        "*Option 2 (SCP File-Drop):*\n"
        "Login locally using your desktop, then SCP the tokens file to the server:\n"
        "`scp ~/.config/schwab-api/tokens.json user@cloud:~/.config/schwab-api/tokens.json`\n\n"
        "Once copied, reply with `/scp_done`."
    )
    bot.send_message(CHAT_ID, msg, parse_mode="Markdown")
    print("Sent Telegram notification. Waiting for user response...")

    result = None

    @bot.message_handler(func=lambda m: True)
    def handle_message(message):
        nonlocal result
        text = message.text.strip()
        if text.startswith(callback_url):
            result = text
            bot.reply_to(message, "✅ Received callback URL. Resuming execution...")
            bot.stop_polling()
        elif text == "/scp_done":
            result = "SCP_DONE"
            bot.reply_to(message, "✅ SCP acknowledged. Reloading tokens from disk...")
            bot.stop_polling()
        else:
            bot.reply_to(
                message,
                "⚠️ Unrecognized input.\n"
                f"Please reply with the URL starting with `{callback_url}` or `/scp_done`.",
                parse_mode="Markdown",
            )

    bot.polling(timeout=120)

    if result == "SCP_DONE":
        # Returning an empty string gracefully aborts the automated OAuth POST.
        # The underlying Schwab request will fail with an AuthError,
        # which we catch in our main loop to retry and load the newly SCP'd tokens.
        return ""

    return result or ""


def main():
    print("Initializing Client...")

    # We use a retry loop because if the user chooses the SCP method,
    # the initial API request will fail (since it was initiated with expired tokens).
    # Catching the AuthError and creating a new Client instance ensures we
    # reload the newly transferred tokens.json file from disk.

    while True:
        try:
            client = Client(
                app_key=APP_KEY, app_secret=APP_SECRET, call_for_auth=telegram_auth_flow
            )

            print("\nFetching linked accounts...")
            accounts_response = client.linked_accounts()
            accounts = accounts_response.json()

            print("\nSuccess! Linked Accounts:")
            for acc in accounts:
                print(
                    f"- Account: {acc.get('accountNumber')} (Hash: {acc.get('hashValue')[:10]}...)"
                )

            # Execution successful, break out of the retry loop
            break

        except AuthError:
            print(
                "\nAuthentication failed (likely because SCP was used or URL was invalid)."
            )
            print("Retrying in 2 seconds to reload tokens from disk...")
            time.sleep(2)
        except Exception as e:
            print(f"\nAn unexpected error occurred: {e}")
            break


if __name__ == "__main__":
    main()
