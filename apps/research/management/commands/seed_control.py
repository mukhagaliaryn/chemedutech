"""The control group's made-up students (the user, 2026-11-15): 62 students student61…student122 in 1504-14 (control)
who go through the whole platform — the course with the topic scores of a given Excel file and all eight ICPAI
sections — like seed_demo's students (scripted AI, dates set back, nothing leaves the machine). Not research data.

The Excel file (``--source``), sheet 1: one row per student — «Тема 1…10» (topic scores), «Итоговый балл» (the course
score), «Буквенная оценка» (its letter), «Завершённые темы» (the day the course is completed). Sheet 2: the 10 answers
(0 / 1) of the pre- and the post-test, used as the section 2 diagnostics I and III (II lies between them). Only these
values are read: the IDs, names and groups of the file are not (the names are made up, the group is ``--group``).
When sheet 1 has fewer rows than sheet 2, the missing students get made-up scores around the group's mean.

    seed_control --source backups/контр_группа_оценки.xlsx      create and walk them through
    seed_control --delete                                       remove this command's students (the group stays)

The logins, passwords and the scores reached go to ``--excel`` (default backups/1504-14_students.xlsx).
Runs only with DEBUG (a local database) unless --allow-prod."""

import random
import secrets
import statistics
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone, translation

from apps.accounts.models import User
from apps.accounts.services.registration import register_student
from apps.assessments import services as quiz_services
from apps.assessments.models import Question
from apps.courses.models import Course, Enrollment
from apps.courses.services import sync_student_enrollments
from apps.organizations.models import AcademicGroup
from apps.programme import services as programme
from apps.programme.models import DiagnosticResult, ProgrammeEnrollment, SectionProgress
from apps.programme.services import diagnostics
from apps.progress.models import CourseResult, ModuleResult, TopicResult

from ._demo.answers import quiz_answers_exact
from ._demo.chats import add_section_chats
from ._demo.clock import Clock
from ._demo.icpai import IcpaiWalk, portfolio_status
from ._demo.people import FEMALE, MALE, PASSWORD_ALPHABET, SURNAME_ROOTS, Student, surname
from ._demo.purge import purge
from ._demo.target import TargetCourseWalk, topic_days
from ._demo.tutor import DemoTutor

COURSE_SLUG = "chemistry"
FIRST_NUMBER = 61  # student61…: after seed_demo's student01…student60
START = (2026, 9, 7)  # the course starts; each student signs up within the following week
USERNAMES = r"^student[0-9]{2,3}$"
TOPICS = 10


class ControlIcpaiWalk(IcpaiWalk):
    """The section 2 diagnostics answered exactly as given: {"I": [0/1 × 10], "II": …, "III": …}."""

    def __init__(self, *args, answers, **kwargs):
        super().__init__(*args, **kwargs)
        self.answers = answers

    def diagnostics(self):
        section = self.sections[2]
        if self.rng.random() < 0.6:
            self.explain_section(2)
        for index, test in enumerate(diagnostics.tests_of(section)):
            if index:
                self.clock.next_day(1, 2)
            attempt = diagnostics.start(self.pe, test)
            self.clock.tick(8, 16)
            questions = list(
                Question.objects.filter(pk__in=attempt.question_ids).prefetch_related("choices").order_by("order")
            )
            pattern = self.answers[test.phase]
            right = {q.pk for q, value in zip(questions, pattern, strict=False) if value}
            attempt = quiz_services.submit_attempt(attempt, quiz_answers_exact(questions, right, self.rng))
            diagnostics.record(self.pe, test, attempt)


def read_source(path: Path) -> tuple[list[dict], list[dict]]:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # a local tool, not in requirements.txt
        raise CommandError("pip install openpyxl — needed for the Excel files") from exc
    book = load_workbook(path, data_only=True, read_only=True)
    sheets = book.worksheets
    head, *rows = list(sheets[0].iter_rows(values_only=True))
    col = {str(name).strip(): i for i, name in enumerate(head) if name}
    topics = [col[f"Тема {n}"] for n in range(1, TOPICS + 1)]
    scores = []
    for row in rows:
        if row[topics[0]] is None:
            continue
        done = row[col["Завершённые темы"]]
        scores.append({
            "topics": [int(row[i]) for i in topics],
            "final": float(row[col["Итоговый балл"]]),
            "letter": str(row[col["Буквенная оценка"]]).strip(),
            "done": done.date() if isinstance(done, datetime) else done,
        })  # fmt: skip
    head, *rows = list(sheets[1].iter_rows(values_only=True))
    col = {str(name).strip(): i for i, name in enumerate(head) if name}
    tests = []
    for row in rows:
        if row[col["pre_q1"]] is None:
            continue
        tests.append({
            "pre": [int(row[col[f"pre_q{n}"]]) for n in range(1, 11)],
            "post": [int(row[col[f"post_q{n}"]]) for n in range(1, 11)],
        })  # fmt: skip
    return scores, tests


def made_up_scores(scores, rng) -> dict:
    """A student the file has no row for: topic scores around the group's mean, its completion day."""
    from apps.progress.grading import grade_for

    base = statistics.mean(s["final"] for s in scores) + rng.uniform(-6, 6)
    topics = [max(50, min(86, round(base + rng.gauss(0, 5)))) for _ in range(TOPICS)]
    half = TOPICS // 2
    m1, m2 = sum(topics[:half]) / half, sum(topics[half:]) / (TOPICS - half)
    final = round((m1 + m2) / 2, 2)
    return {
        "topics": topics,
        "final": final,
        "letter": grade_for(Decimal(str(final))).letter,
        "done": scores[0]["done"],
    }


class Command(BaseCommand):
    help = "Create the control group's made-up students (1504-14) from an Excel file of scores and walk them through."

    def add_arguments(self, parser):
        parser.add_argument("--source", default="backups/контр_группа_оценки.xlsx", help="The Excel file of scores.")
        parser.add_argument(
            "--group", default="1504-14", help="The control group (must exist, attached to the course)."
        )
        parser.add_argument("--count", type=int, default=62, help="How many students (the file's rows, then made up).")
        parser.add_argument(
            "--excel", default="backups/1504-14_students.xlsx", help="Where to write logins, passwords."
        )
        parser.add_argument("--seed", type=int, default=1504, help="Random seed of names, plans and answers.")
        parser.add_argument("--delete", action="store_true", help="Remove this command's students (the group stays).")
        parser.add_argument("--allow-prod", action="store_true", help="Run without DEBUG (not recommended).")

    def handle(self, *args, source, group, count, excel, seed, delete, **options):
        if not settings.DEBUG and not options["allow_prod"]:
            raise CommandError("seed_control runs on a local database (DEBUG=True); use --allow-prod to override.")
        group = AcademicGroup.objects.filter(name=group).first()
        if group is None:
            raise CommandError("The group does not exist.")
        if delete:
            with transaction.atomic():
                users = self.users(group)
                n = users.count()
                purge(users)
            self.stdout.write(self.style.SUCCESS(f"Removed {n} students of {group.name} and their data."))
            return
        if self.users(group).exists():
            raise CommandError(f"{group.name} has made-up students already: run seed_control --delete first.")
        course = Course.objects.filter(slug=COURSE_SLUG).first()
        teacher = User.objects.filter(course_roles__course=course).first() if course else None
        if course is None or teacher is None:
            raise CommandError("Run seed_course and seed_icpai first; the course needs a teacher.")
        if group.research_cohort != "control":
            self.stdout.write(self.style.WARNING(f"{group.name} is «{group.research_cohort or '—'}», not control."))
        rng = random.Random(seed)
        scores, tests = read_source(Path(source))
        while len(scores) < count:
            scores.append(made_up_scores(scores, rng))
        if len(tests) < count:
            raise CommandError(f"Sheet 2 has {len(tests)} students, {count} are needed.")
        people = self.people(rng, count)
        rows = []
        for person, score, test in zip(people, scores[:count], tests[:count], strict=True):
            rows.append(self.student(person, score, test, group, course, teacher, rng))
        self.stdout.write("Section chats …")
        add_section_chats(User.objects.filter(username__in=[p.username for p in people]).order_by("username"),
                          random.Random(seed + 7))  # fmt: skip
        self.excel(Path(excel), rows)
        self.stdout.write(self.style.SUCCESS(f"{len(rows)} students are ready in {group.name}; logins: {excel}"))

    def users(self, group):
        return User.objects.filter(
            student_profile__group=group, username__regex=USERNAMES, email__endswith="@example.com"
        )

    def people(self, rng, count) -> list[Student]:
        used = set(User.objects.filter(role=User.Role.STUDENT).values_list("first_name", "last_name"))
        people = []
        for index in range(count):
            while True:
                female = rng.random() < 0.55
                first = rng.choice(FEMALE if female else MALE)
                last = surname(rng.choice(SURNAME_ROOTS), female)
                if (first, last) not in used:
                    used.add((first, last))
                    break
            password = "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(8))
            people.append(Student(FIRST_NUMBER + index, first, last, "medium", 0.7, password))
        return people

    def student(self, person, score, test, group, course, teacher, rng):
        tz = timezone.get_current_timezone()
        start = timezone.make_aware(datetime(*START, 10, 0), tz)
        joined = start + timedelta(days=rng.randint(0, 6), hours=rng.randint(0, 9), minutes=rng.randint(0, 59))
        end = timezone.make_aware(datetime.combine(score["done"], datetime.min.time()), tz).replace(hour=10)
        days = topic_days(joined + timedelta(days=1), end, TOPICS, random.Random(rng.random()))
        clock = Clock(joined, random.Random(rng.random()), limit=timezone.now() - timedelta(hours=3))
        tutor = DemoTutor()
        targets = {n: score["topics"][n - 1] for n in range(1, TOPICS + 1)}
        middle = [p if p == q else rng.choice((p, q)) for p, q in zip(test["pre"], test["post"], strict=True)]
        answers = {"I": test["pre"], "II": middle, "III": test["post"]}
        with translation.override("kk"), tutor.active(), clock.running(), transaction.atomic():
            user = register_student(email=person.email, password=person.password, first_name=person.first_name,
                                    last_name=person.last_name, group=group)  # fmt: skip
            User.objects.filter(pk=user.pk).update(date_joined=clock.now)
            sync_student_enrollments(user)
            enrollment = Enrollment.objects.get(student=user, course=course)
            programme.sync_student(user)
            clock.tick(1, 5)
            TargetCourseWalk(
                enrollment, person, clock, clock.rng, targets, (score["final"], score["letter"]), days
            ).run()
            person.accuracy = round(score["final"] / 100, 3)  # the ICPAI work's quality follows the course
            pe = programme.refresh(user)
            if pe is not None:
                revised = 0.2 if person.accuracy >= 0.75 else 0.4 if person.accuracy >= 0.65 else 0.6
                plan = {"depth": 8, "portfolio": "revised" if rng.random() < revised else "accepted", "confirmed": True}
                ControlIcpaiWalk(pe, person, clock, clock.rng, tutor, teacher, answers=answers).run(plan)
            User.objects.filter(pk=user.pk).update(last_login=clock.now)
        if clock.now >= timezone.now():
            raise CommandError(f"{person.username}: the made-up dates reached today.")
        row = self.row(person, group, enrollment, score)
        self.stdout.write(f"  {person.username} · {row[18]} {row[19]} (Excel {score['final']:.2f} {score['letter']})")
        return row

    def row(self, person, group, enrollment, score) -> list:
        result = CourseResult.objects.filter(enrollment=enrollment).first()
        topics = {t.topic.number: t.score_percent for t in TopicResult.objects.filter(enrollment=enrollment)
                  .select_related("topic")}  # fmt: skip
        modules = list(ModuleResult.objects.filter(enrollment=enrollment).order_by("module__order")
                       .values_list("score_percent", flat=True))  # fmt: skip
        pe = ProgrammeEnrollment.objects.filter(student=enrollment.student).first()
        passed = SectionProgress.objects.filter(enrollment=pe, status="passed").count() if pe else 0
        diag = {r["phase"]: r for r in DiagnosticResult.objects.filter(enrollment=pe).values("phase")
                .annotate(earned=Sum("earned"))} if pe else {}  # fmt: skip
        return [
            person.number - FIRST_NUMBER + 1, person.full_name, person.username, person.email, person.password,
            group.name,
            *[float(topics[n]) if topics.get(n) is not None else None for n in range(1, TOPICS + 1)],
            *[float(m) if m is not None else None for m in modules],
            float(result.score_percent) if result and result.score_percent is not None else None,
            result.letter if result else "",
            score["final"], score["letter"],
            *[float(diag[p]["earned"]) if p in diag else None for p in ("I", "II", "III")],
            timezone.localtime(result.completed_at).strftime("%Y-%m-%d") if result and result.completed_at else "",
            f"{passed} / 8", portfolio_status(pe) if pe else "",
        ]  # fmt: skip

    def excel(self, path: Path, rows):
        from openpyxl import Workbook
        from openpyxl.styles import Font

        book = Workbook()
        sheet = book.active
        sheet.title = "Бақылау тобы"
        head = ["№", "Аты-жөні", "Логин", "Email", "Пароль", "Топ", *[f"Тақырып {n}" for n in range(1, TOPICS + 1)],
                "Модуль 1", "Модуль 2", "Курс ұпайы", "Баға", "Excel: курс ұпайы", "Excel: баға",
                "Диагностика I", "Диагностика II", "Диагностика III", "Курс аяқталды", "ICPAI: өткен бөлімдер",
                "Портфолио"]  # fmt: skip
        sheet.append(head)
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for row in rows:
            sheet.append(row)
        sheet.freeze_panes = "A2"
        path.parent.mkdir(parents=True, exist_ok=True)
        book.save(path)
