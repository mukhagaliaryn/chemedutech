from unittest import mock

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.core.permissions import ADMIN, STUDENT, TEACHER, has_role, home_url_for

from .models import JOIN_CODE_ALPHABET, JOIN_CODE_LENGTH
from .selectors import group_by_join_code, research_cohort_for
from .services import regenerate_join_code
from .testing import make_group, make_student


class JoinCodeTests(TestCase):
    def test_new_group_gets_a_readable_unique_code(self):
        a, b = make_group(), make_group()
        for group in (a, b):
            self.assertEqual(len(group.join_code), JOIN_CODE_LENGTH)
            self.assertTrue(set(group.join_code) <= set(JOIN_CODE_ALPHABET))
        self.assertNotEqual(a.join_code, b.join_code)

    def test_regenerate_replaces_the_old_code(self):
        group = make_group()
        old = group.join_code
        new = regenerate_join_code(group)
        self.assertNotEqual(old, new)
        self.assertIsNone(group_by_join_code(old))
        self.assertEqual(group_by_join_code(new.lower()), group)

    def test_regenerate_retries_on_collision(self):
        taken, group = make_group(), make_group()
        codes = iter([taken.join_code, "ABCDEFGH"])
        with mock.patch("apps.organizations.services.groups.generate_join_code", lambda: next(codes)):
            self.assertEqual(regenerate_join_code(group), "ABCDEFGH")

    def test_inactive_university_hides_its_groups(self):
        group = make_group()
        university = group.department.faculty.university
        university.is_active = False
        university.save()
        self.assertIsNone(group_by_join_code(group.join_code))


class CohortTests(TestCase):
    def test_research_cohort_comes_from_the_group(self):
        group = make_group(research_cohort="control")
        self.assertEqual(research_cohort_for(make_student("s1", group=group)), "control")
        self.assertEqual(research_cohort_for(make_student("s2")), "")
        teacher = User.objects.create_user("t", "t@example.kz", "x", role=User.Role.TEACHER)
        self.assertEqual(research_cohort_for(teacher), "")


class PermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.student = make_student("s")
        cls.teacher = User.objects.create_user("t", "t@example.kz", "x", role=User.Role.TEACHER)
        cls.admin = User.objects.create_superuser("root", "root@example.kz", "x")

    def test_has_role(self):
        self.assertTrue(has_role(self.student, STUDENT))
        self.assertFalse(has_role(self.student, TEACHER, ADMIN))
        self.assertTrue(has_role(self.teacher, TEACHER, ADMIN))

    def test_home_url_by_role(self):
        self.assertEqual(home_url_for(self.student), reverse("student:courses"))
        self.assertEqual(home_url_for(self.teacher), reverse("research:dashboard"))
        self.assertEqual(home_url_for(self.admin), reverse("admin:index"))

    def test_student_cannot_open_research(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse("research:dashboard")).status_code, 403)
        self.assertEqual(self.client.get(reverse("research:export_attempts")).status_code, 403)

    def test_anonymous_goes_to_login(self):
        r = self.client.get(reverse("research:dashboard"))
        self.assertRedirects(r, f"{reverse('accounts:login')}?next={reverse('research:dashboard')}")

    def test_teacher_and_admin_open_research(self):
        for user in (self.teacher, self.admin):
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse("research:dashboard")).status_code, 200)

    def test_only_admin_gets_into_django_admin(self):
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 302)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 200)


class AdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser("root", "root@example.kz", "x")
        cls.group = make_group()
        cls.student = make_student("s", group=cls.group)

    def setUp(self):
        self.client.force_login(self.admin)

    def test_changelists_and_forms_render(self):
        for model in ("university", "faculty", "department", "specialty", "academicgroup", "studentprofile",
                      "teacherprofile"):  # fmt: skip
            self.assertEqual(self.client.get(reverse(f"admin:organizations_{model}_changelist")).status_code, 200)
            self.assertEqual(self.client.get(reverse(f"admin:organizations_{model}_add")).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:accounts_user_changelist")).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("admin:accounts_user_change", args=[self.student.pk])).status_code, 200
        )

    def test_admin_adds_a_teacher_with_profile(self):
        url = reverse("admin:accounts_user_add")
        r = self.client.get(url)
        self.assertContains(r, 'value="teacher" selected')
        data = {
            "username": "erlan.m",
            "email": "erlan@example.kz",
            "role": "teacher",
            "last_name": "Мұратов",
            "first_name": "Ерлан",
            "middle_name": "",
            "password1": "Teach-chem-2026!",
            "password2": "Teach-chem-2026!",
            "usable_password": "true",
            "teacher_profile-TOTAL_FORMS": "1",
            "teacher_profile-INITIAL_FORMS": "0",
            "teacher_profile-MIN_NUM_FORMS": "0",
            "teacher_profile-MAX_NUM_FORMS": "1",
            "teacher_profile-0-department": self.group.department_id,
            "teacher_profile-0-position": "Senior lecturer",
            "teacher_profile-0-academic_degree": "PhD",
        }
        r = self.client.post(url, data)
        self.assertEqual(r.status_code, 302, r.context and r.context["adminform"].form.errors)
        teacher = User.objects.get(username="erlan.m")
        self.assertEqual(teacher.role, User.Role.TEACHER)
        self.assertFalse(teacher.is_staff)
        self.assertEqual(teacher.teacher_profile.department, self.group.department)

    def test_regenerate_action(self):
        old = self.group.join_code
        self.client.post(
            reverse("admin:organizations_academicgroup_changelist"),
            {"action": "regenerate_codes", "_selected_action": [self.group.pk]},
        )
        self.group.refresh_from_db()
        self.assertNotEqual(self.group.join_code, old)

    def test_lab_attempts_cannot_be_deleted(self):
        from django.contrib import admin

        from apps.labs.models import LabAttempt

        r = self.client.get(reverse("admin:labs_labattempt_changelist"))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(admin.site._registry[LabAttempt].has_delete_permission(r.wsgi_request))
