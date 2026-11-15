"""The «Let the AI explain» chats of the section pages for made-up students: scripted answers (tutor.py) stored by the
real AI layer, so the history is kept like a real chat (model «demo»; nothing leaves the machine)."""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone, translation

from apps.ai import services as ai
from apps.ai.models import Mode
from apps.programme.models import ProgrammeEnrollment, SectionProgress

from . import texts
from .clock import Clock
from .tutor import DemoTutor


def add_section_chats(users, rng) -> int:
    """Every open section of every given student gets an «explain the section» request (when missing) and one or two
    questions of the student's own, dated after the student opened the section (or after the last message)."""
    limit = timezone.now() - timedelta(minutes=30)
    added = 0
    for user in users:
        pe = ProgrammeEnrollment.objects.filter(student=user).first()
        if pe is None:
            continue
        rows = SectionProgress.objects.filter(enrollment=pe).exclude(opened_at=None).select_related("section")
        for row in rows.order_by("section__number"):
            section = row.section
            conversation = ai.conversation_for(user, Mode.ASSISTANT, "section", section.pk)
            if conversation and conversation.messages.count() >= 4:
                continue
            last = conversation.messages.order_by("-created_at").first() if conversation else None
            start = (last.created_at if last else row.opened_at) + timedelta(minutes=rng.randint(2, 20))
            if start >= limit:
                start = limit - timedelta(minutes=rng.randint(20, 120))
            clock, tutor = Clock(start, rng, limit), DemoTutor()
            with translation.override("kk"), tutor.active(), clock.running(), transaction.atomic():
                if conversation is None:
                    purpose = section.purpose.split(". ")[0].rstrip(".") + "."
                    tutor.next(texts.SECTION_EXPLAIN.format(title=section.title, purpose=purpose))
                    ai.ask(user, context_type="section", context_id=section.pk, context=section.purpose,
                           intent="explain_section")  # fmt: skip
                    clock.tick(1, 4)
                for question, answer in rng.sample(texts.SECTION_QA[section.number], k=rng.randint(1, 2)):
                    tutor.next(answer)
                    ai.ask(user, context_type="section", context_id=section.pk, context=section.purpose,
                           text=question)  # fmt: skip
                    clock.tick(1, 5)
            added += 1
    return added
