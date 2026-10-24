"""The ICPAI programme: the programme on the seeded course and its 8 sections (docs/icpai/SPEC.md §0).

Run after seed_course. Safe on every deploy: missing sections are added; existing ones keep the texts and
pass marks an administrator may have edited, unless --replace (then titles, kinds, texts and anchors come
from _icpai/ again). Student enrolments are made lazily when students open their cabinet.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.courses.models import Course
from apps.programme.models import Programme, Section

from ._icpai import COURSE_SLUG, PROGRAMME, SECTIONS


class Command(BaseCommand):
    help = "Create the ICPAI programme and its sections on the seeded course."

    def add_arguments(self, parser):
        parser.add_argument("--replace", action="store_true", help="Rewrite the section texts from the code.")

    @transaction.atomic
    def handle(self, *args, replace=False, verbosity=1, **options):
        course = Course.objects.filter(slug=COURSE_SLUG).first()
        if course is None:
            raise CommandError(f"Course «{COURSE_SLUG}» not found — run seed_course first.")
        programme, _created = Programme.objects.get_or_create(
            slug=PROGRAMME["slug"], defaults={"title": PROGRAMME["title"], "course": course}
        )
        added = 0
        for number, kind, title, purpose, anchor in SECTIONS:
            values = {"kind": kind, "title": title, "purpose": purpose, "guide_anchor": anchor}
            section, made = Section.objects.get_or_create(programme=programme, number=number, defaults=values)
            added += made
            if replace and not made:
                for field, value in values.items():
                    setattr(section, field, value)
                section.save()
        if verbosity:
            self.stdout.write(
                self.style.SUCCESS(f"Programme «{programme.title}» is ready: {len(SECTIONS)} sections ({added} new).")
            )
