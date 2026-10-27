"""Demo data for looking at the interface: 2 groups (1504-14 control, 1507-14 experimental) × 30 made-up students
student01…student60 who went through the course at different levels (complete high / medium / low, in the middle,
just started), with dates set back in time. See _demo/__init__.py: no AI is called. The groups carry a research cohort
(the user's choice, 2026-10-27), so the demo data shows in the comparisons and exports — remove it before the real
experiment.

    seed_demo                    create the demo students and walk them through (refuses when they exist)
    seed_demo --delete           remove the demo students and their data (the groups stay)
    seed_demo --wipe-students    remove EVERY student account and its data first (teachers, admins and
                                 organisations stay); asks for confirmation unless --yes
    seed_demo --add-chats        add the «Let the AI explain» chats to the section pages of the existing demo
                                 students where they have none or a short one (logins and passwords stay)

The logins and passwords go to an Excel file (``--excel``, default demo_students.xlsx, ignored by git).
Runs only with DEBUG (a local database) unless --allow-prod.
"""

import random
from datetime import date, datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone, translation

from apps.accounts.models import User
from apps.accounts.services.registration import register_student
from apps.ai import services as ai
from apps.ai.models import Mode
from apps.certificates.models import Certificate
from apps.courses.models import Course, Enrollment
from apps.courses.services import assign_group, sync_student_enrollments
from apps.courses.services.groups import set_research_cohort
from apps.organizations.models import AcademicGroup, Department, Specialty
from apps.programme import services as programme
from apps.programme.models import ProgrammeEnrollment, SectionProgress
from apps.progress.models import CourseResult

from ._demo import texts
from ._demo.clock import Clock
from ._demo.course import CourseWalk, course_stages
from ._demo.icpai import IcpaiWalk, portfolio_status
from ._demo.people import LEVEL_NAMES, make_students
from ._demo.purge import purge
from ._demo.tutor import DemoTutor

DEMO_USERNAMES = r"^student[0-9]{2}$"
# (name, research cohort): an existing group of that name is used, a missing one is created
GROUPS = (("1504-14", "control"), ("1507-14", "experimental"))
COURSE_SLUG = "chemistry"
START = (2026, 9, 7)  # the groups start the course; each student signs up within the following week
# students still at work joined later, so their last activity is recent: (days after START: from, to)
JOINED = {"progress": (38, 44), "started": (47, 49)}
IN_PROGRESS_TOPICS = (3, 8)  # a student «in the middle» stops at a stage of one of these topics


def demo_users():
    return User.objects.filter(username__regex=DEMO_USERNAMES, email__endswith="@example.com")


class Command(BaseCommand):
    help = "Create 60 demo students who went through the course (interface review data, not research data)."

    def add_arguments(self, parser):
        parser.add_argument("--delete", action="store_true", help="Remove the demo students (the groups stay).")
        parser.add_argument("--add-chats", action="store_true", help="Add section chats to the existing demo students.")
        parser.add_argument("--wipe-students", action="store_true", help="Remove every student and their data.")
        parser.add_argument("--yes", action="store_true", help="Do not ask before --wipe-students.")
        parser.add_argument("--seed", type=int, default=2026, help="Random seed of names, levels and answers.")
        parser.add_argument("--excel", default="demo_students.xlsx", help="Where to write logins and passwords.")
        parser.add_argument("--per-group", type=int, default=30, help="Students per group (tests use fewer).")
        parser.add_argument("--allow-prod", action="store_true", help="Run without DEBUG (not recommended).")

    def handle(self, *args, delete=False, wipe_students=False, yes=False, seed=2026, excel="", per_group=30, **options):
        if not settings.DEBUG and not options["allow_prod"]:
            raise CommandError("seed_demo runs on a local database (DEBUG=True); use --allow-prod to override.")
        if wipe_students:
            self.wipe(yes)
        if delete:
            self.delete()
            return
        if options.get("add_chats"):
            self.add_chats(seed)
            return
        self.create(seed, Path(excel), per_group)

    # --- removing --------------------------------------------------------------------------------

    def wipe(self, yes):
        students = User.objects.filter(role=User.Role.STUDENT)
        count = students.count()
        if not yes:
            answer = input(f"Delete ALL {count} student accounts with their attempts and results? Type «yes»: ")
            if answer.strip() != "yes":
                raise CommandError("Cancelled.")
        with transaction.atomic():
            purge(students)
        self.stdout.write(self.style.WARNING(f"Removed {count} student accounts and their data."))

    def delete(self):
        with transaction.atomic():
            users = demo_users()
            count = users.count()
            purge(users)
        self.stdout.write(self.style.SUCCESS(f"Removed {count} demo students and their data."))

    # --- the section pages' chats of the existing demo students ------------------------------------

    def add_chats(self, seed):
        """Every open section of every demo student gets an «explain the section» request (when missing) and one or
        two questions of the student's own, dated after the student opened the section (or after the last message)."""
        rng = random.Random(seed + 7)
        limit = timezone.now() - timedelta(minutes=30)
        added = 0
        for user in demo_users().order_by("username"):
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
        self.stdout.write(self.style.SUCCESS(f"Section chats added or extended: {added}."))

    # --- creating --------------------------------------------------------------------------------

    def create(self, seed, excel: Path, per_group: int = 30):
        if demo_users().exists():
            raise CommandError("Demo students exist already: run seed_demo --delete first.")
        course = Course.objects.filter(slug=COURSE_SLUG).first()
        if course is None or not course_stages(course):
            raise CommandError("Run seed_course and seed_icpai first.")
        teacher = (
            User.objects.filter(course_roles__course=course).first()
            or User.objects.filter(role=User.Role.TEACHER).first()
        )
        department = Department.objects.order_by("pk").first()
        if teacher is None or department is None:
            raise CommandError("A teacher and a department are needed (create them in the admin).")
        rng = random.Random(seed)
        start = timezone.make_aware(datetime(*START, 10, 0))
        with Clock(start, rng).running():
            groups = [self.group(name, cohort, course, teacher, department) for name, cohort in GROUPS]
        people = make_students(rng, len(groups), per_group)
        stages = course_stages(course)
        rows = []
        for group, students in zip(groups, people, strict=True):
            for student in students:
                rows.append(self.student(student, group, course, stages, rng, start, teacher))
                self.stdout.write(f"  {student.username} · {LEVEL_NAMES[student.level]}")
        self.excel(excel, rows)
        self.stdout.write(self.style.SUCCESS(f"{len(rows)} demo students are ready; logins and passwords: {excel}"))

    def group(self, name, cohort, course, teacher, department):
        group = AcademicGroup.objects.filter(name=name).first() or AcademicGroup.objects.create(
            department=department,
            specialty=Specialty.objects.filter(department=department).order_by("pk").first(),
            name=name,
            admission_year=2023,
            study_year=3,
            curator=teacher,
        )
        set_research_cohort(group, cohort)  # before the students join: their enrolments copy it
        assign_group(course, group, teacher=teacher, starts_on=date(*START))
        return group

    def stop_index(self, student, stages, rng):
        if student.level == "started":
            return rng.randint(0, 1)
        if student.level == "progress":
            low, high = IN_PROGRESS_TOPICS
            middle = [i for i, s in enumerate(stages) if low <= s.topic.number <= high]
            return rng.choice(middle or list(range(len(stages) // 2, len(stages))))  # a short course: its 2nd half
        return None

    def icpai_plan(self, student, rng) -> dict:
        """ICPAI after the course: every student who completed it goes through all eight sections and the teacher
        reviews everything; a weaker student gets the portfolio back for more work more often."""
        if student.level in ("progress", "started"):
            return {"depth": 2}  # still at the course: only what is open
        revised = {"high": 0.2, "medium": 0.4, "low": 0.6}[student.level]
        return {"depth": 8, "portfolio": "revised" if rng.random() < revised else "accepted", "confirmed": True}

    def student(self, student, group, course, stages, rng, start, teacher):
        days = rng.randint(*JOINED.get(student.level, (1, 7)))
        joined = start + timedelta(days=days, hours=rng.randint(0, 9), minutes=rng.randint(0, 59))
        clock = Clock(joined, random.Random(rng.random()), limit=timezone.now() - timedelta(hours=3))
        tutor = DemoTutor()
        with translation.override("kk"), tutor.active(), clock.running(), transaction.atomic():
            user = register_student(
                email=student.email,
                password=student.password,
                first_name=student.first_name,
                last_name=student.last_name,
                group=group,
            )
            User.objects.filter(pk=user.pk).update(date_joined=clock.now)
            sync_student_enrollments(user)
            enrollment = Enrollment.objects.get(student=user, course=course)
            programme.sync_student(user)
            clock.tick(1, 5)
            CourseWalk(enrollment, student, clock, clock.rng).run(self.stop_index(student, stages, rng))
            pe = programme.refresh(user)
            if pe is not None:
                IcpaiWalk(pe, student, clock, clock.rng, tutor, teacher).run(self.icpai_plan(student, rng))
            User.objects.filter(pk=user.pk).update(last_login=clock.now)
        if clock.now >= timezone.now():
            raise CommandError(f"{student.username}: the made-up dates reached today — move START back.")
        return self.row(student, group, enrollment)

    def row(self, student, group, enrollment) -> list:
        result = CourseResult.objects.filter(enrollment=enrollment).first()
        certificate = Certificate.objects.filter(enrollment=enrollment).exists()
        pe = ProgrammeEnrollment.objects.filter(student=enrollment.student).first()
        passed = SectionProgress.objects.filter(enrollment=pe, status="passed").count() if pe else 0
        return [
            student.number,
            student.full_name,
            student.username,
            student.email,
            student.password,
            group.name,
            LEVEL_NAMES[student.level],
            float(result.score_percent) if result and result.score_percent is not None else None,
            result.letter if result else "",
            f"{result.topics_completed} / {result.topics_total}" if result else "",
            "иә" if certificate else "жоқ",
            f"{passed} / 8",
            portfolio_status(pe) if pe else "",
        ]

    # --- the Excel file --------------------------------------------------------------------------

    def excel(self, path: Path, rows):
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font
        except ImportError as exc:  # a local tool, not in requirements.txt
            raise CommandError("pip install openpyxl — needed for the Excel file") from exc
        book = Workbook()
        sheet = book.active
        sheet.title = "Демо студенттер"
        head = [
            "№", "Аты-жөні", "Логин", "Email", "Пароль", "Топ", "Деңгейі", "Курс ұпайы, %", "Баға",
            "Аяқталған тақырыптар", "Сертификат", "ICPAI: өткен бөлімдер", "Портфолио",
        ]  # fmt: skip
        sheet.append(head)
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for row in rows:
            sheet.append(row)
        widths = (5, 28, 12, 26, 12, 10, 16, 14, 7, 20, 11, 20, 22)
        for column, width in zip("ABCDEFGHIJKLM", widths, strict=True):
            sheet.column_dimensions[column].width = width
        sheet.freeze_panes = "A2"
        book.save(path)
