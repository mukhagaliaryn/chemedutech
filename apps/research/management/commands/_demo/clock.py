"""A clock set back in time: while it runs, django.utils.timezone.now (auto_now fields, services) reads it."""

from contextlib import contextmanager
from datetime import timedelta
from unittest import mock

from django.utils import timezone


class Clock:
    def __init__(self, start, rng, limit=None):
        self.now = start
        self.rng = rng
        self.limit = limit  # the made-up days never reach it (today)

    def tick(self, minutes_from, minutes_to=None):
        minutes = self.rng.uniform(minutes_from, minutes_to if minutes_to is not None else minutes_from)
        self.now += timedelta(minutes=minutes)
        return int(minutes * 60)

    def next_day(self, days_from=1, days_to=2):
        """Another study day: 1–2 days later, between 9:00 and 21:00 local time."""
        local = timezone.localtime(self.now) + timedelta(days=self.rng.randint(days_from, days_to))
        local = local.replace(hour=self.rng.randint(9, 20), minute=self.rng.randint(0, 59), second=0, microsecond=0)
        if local <= self.now:  # «the same day» at an hour already past: later that day instead
            local = self.now + timedelta(minutes=self.rng.randint(30, 180))
        if self.limit and local >= self.limit:  # no days left before today: go on within the same session
            local = self.now + timedelta(minutes=self.rng.randint(5, 20))
        self.now = local

    @contextmanager
    def running(self):
        with mock.patch("django.utils.timezone.now", lambda: self.now):
            yield self
