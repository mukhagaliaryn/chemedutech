"""The daily reminders of section 8 (guide @S8 IV): run once a day (systemd timer or cron, see DEPLOY.md)."""

from django.core.management.base import BaseCommand

from apps.programme.services import schedule


class Command(BaseCommand):
    help = "Send the section 8 deadline reminders (two days before the hand-in date)."

    def handle(self, *args, verbosity=1, **options):
        sent = schedule.remind()
        if verbosity:
            self.stdout.write(self.style.SUCCESS(f"Reminders sent: {sent}"))
