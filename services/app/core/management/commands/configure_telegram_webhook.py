from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.telegram import configure_telegram_webhook, telegram_is_configured


class Command(BaseCommand):
    help = "Register this deployment's Telegram webhook without printing secrets."

    def handle(self, *args, **options):
        if not telegram_is_configured():
            raise CommandError(
                "Configure TELEGRAM_BOT_TOKEN, TELEGRAM_BOT_USERNAME, and "
                "TELEGRAM_WEBHOOK_SECRET first."
            )
        webhook_url = (
            f"{settings.WEB_APP_URL.rstrip('/')}/api/v1/webhooks/telegram"
        )
        if not webhook_url.startswith("https://"):
            raise CommandError("Telegram webhooks require an HTTPS WEB_APP_URL.")
        configure_telegram_webhook(webhook_url)
        self.stdout.write(
            self.style.SUCCESS(f"Telegram webhook registered at {webhook_url}")
        )
