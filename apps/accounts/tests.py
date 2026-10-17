from django.contrib.auth import authenticate
from django.core import mail
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.organizations.models import StudentProfile
from apps.organizations.testing import make_group, make_student

from .models import User


def signup_data(group, /, **overrides):
    data = {
        "first_name": "Айгерім",
        "last_name": "Сапарова",
        "email": "Aigerim@Example.kz",
        "password1": "Chem-lab-2026!",
        "password2": "Chem-lab-2026!",
        "group_mode": "list",
        "university": group.department.faculty.university_id,
        "faculty": group.department.faculty_id,
        "department": group.department_id,
        "group": group.pk,
    }
    data.update(overrides)
    return data


class UserModelTests(TestCase):
    def test_email_is_unique_case_insensitively(self):
        User.objects.create_user("a", "same@example.kz", "x")
        with self.assertRaises(IntegrityError):
            User.objects.create_user("b", "SAME@example.kz", "x")

    def test_is_staff_follows_role(self):
        user = User.objects.create_user("t", "t@example.kz", "x", role=User.Role.TEACHER, is_staff=True)
        self.assertFalse(user.is_staff)
        user.role = User.Role.ADMIN
        user.save(update_fields=["role"])
        user.refresh_from_db()
        self.assertTrue(user.is_staff)

    def test_createsuperuser_is_admin(self):
        user = User.objects.create_superuser("root", "root@example.kz", "x")
        self.assertEqual(user.role, User.Role.ADMIN)
        self.assertTrue(user.is_admin_role and user.is_staff and user.is_superuser)

    def test_full_name_order(self):
        user = User(username="u", first_name="Айгерім", last_name="Сапарова", middle_name="Ерланқызы")
        self.assertEqual(user.full_name, "Сапарова Айгерім Ерланқызы")


class LoginTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = make_student("aigerim", email="Aigerim@Example.kz", password="secret-pass-1")
        cls.teacher = User.objects.create_user("teacher", "t@example.kz", "secret-pass-1", role=User.Role.TEACHER)

    def test_backend_username_or_email(self):
        self.assertEqual(authenticate(username="aigerim", password="secret-pass-1"), self.user)
        self.assertEqual(authenticate(username="aigerim@example.KZ", password="secret-pass-1"), self.user)
        self.assertIsNone(authenticate(username="aigerim", password="wrong"))
        self.assertIsNone(authenticate(username="nobody@example.kz", password="secret-pass-1"))

    def test_inactive_user_cannot_log_in(self):
        self.user.is_active = False
        self.user.save()
        self.assertIsNone(authenticate(username="aigerim", password="secret-pass-1"))

    def test_login_by_email_redirects_student_to_cabinet(self):
        r = self.client.post(reverse("accounts:login"), {"username": "AIGERIM@example.kz", "password": "secret-pass-1"})
        self.assertRedirects(r, reverse("student:dashboard"), fetch_redirect_response=False)

    def test_login_redirects_by_role(self):
        r = self.client.post(reverse("accounts:login"), {"username": "teacher", "password": "secret-pass-1"})
        self.assertRedirects(r, reverse("teacher:dashboard"), fetch_redirect_response=False)
        self.client.logout()
        User.objects.create_superuser("root", "root@example.kz", "secret-pass-1")
        r = self.client.post(reverse("accounts:login"), {"username": "root", "password": "secret-pass-1"})
        self.assertRedirects(r, reverse("admin:index"), fetch_redirect_response=False)

    def test_wrong_password_message(self):
        r = self.client.post(reverse("accounts:login"), {"username": "aigerim", "password": "nope"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.context["form"].non_field_errors())

    def test_remember_me_keeps_the_session(self):
        self.client.post(
            reverse("accounts:login"), {"username": "aigerim", "password": "secret-pass-1", "remember": "on"}
        )
        self.assertFalse(self.client.session.get_expire_at_browser_close())

    def test_remember_me_unchecked(self):
        form_data = {"username": "aigerim", "password": "secret-pass-1"}
        self.client.post(reverse("accounts:login"), form_data)
        # unchecked checkbox → not in POST → session ends with the browser
        self.assertTrue(self.client.session.get_expire_at_browser_close())

    def test_password_reset_sends_email(self):
        r = self.client.post(reverse("accounts:password_reset"), {"email": "aigerim@EXAMPLE.kz"})
        self.assertRedirects(r, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/accounts/reset/", mail.outbox[0].body)


@override_settings(LANGUAGE_CODE="en")
class SignupTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.group = make_group(name="Chem-23-1", research_cohort="experimental", study_year=2)

    def test_signup_from_list_creates_student_with_profile(self):
        r = self.client.post(reverse("accounts:signup"), signup_data(self.group, research_consent="on"))
        self.assertRedirects(r, reverse("student:dashboard"), fetch_redirect_response=False)
        user = User.objects.get(username="aigerim")
        self.assertEqual(user.role, User.Role.STUDENT)
        self.assertFalse(user.is_staff)
        profile = user.student_profile
        self.assertEqual(profile.group, self.group)
        self.assertEqual(profile.study_year, 2)
        self.assertTrue(profile.research_consent)
        self.assertIsNotNone(profile.research_consent_at)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_signup_by_join_code(self):
        data = signup_data(self.group, group_mode="code", join_code=f" {self.group.join_code.lower()} ")
        data.update(university="", faculty="", department="", group="")
        self.client.post(reverse("accounts:signup"), data)
        profile = User.objects.get(username="aigerim").student_profile
        self.assertEqual(profile.group, self.group)
        self.assertFalse(profile.research_consent)
        self.assertIsNone(profile.research_consent_at)

    def test_wrong_or_inactive_join_code(self):
        r = self.client.post(
            reverse("accounts:signup"), signup_data(self.group, group_mode="code", join_code="ZZZZZZZZ")
        )
        self.assertTrue(r.context["form"].has_error("join_code"))
        self.group.is_active = False
        self.group.save()
        r = self.client.post(
            reverse("accounts:signup"), signup_data(self.group, group_mode="code", join_code=self.group.join_code)
        )
        self.assertTrue(r.context["form"].has_error("join_code"))
        self.assertFalse(User.objects.exists())

    def test_group_is_required(self):
        r = self.client.post(reverse("accounts:signup"), signup_data(self.group, group=""))
        self.assertTrue(r.context["form"].has_error("group"))
        self.assertFalse(User.objects.exists())

    def test_group_must_belong_to_the_chosen_department(self):
        other = make_group(name="Other")
        r = self.client.post(reverse("accounts:signup"), signup_data(self.group, group=other.pk))
        self.assertTrue(r.context["form"].has_error("group"))

    def test_teacher_cannot_sign_up_themselves(self):
        data = signup_data(self.group, role="teacher", is_staff="on", is_superuser="on")
        self.client.post(reverse("accounts:signup"), data)
        user = User.objects.get(username="aigerim")
        self.assertEqual(user.role, User.Role.STUDENT)
        self.assertFalse(user.is_staff or user.is_superuser)

    def test_duplicate_email_any_case(self):
        make_student("first", email="aigerim@example.kz")
        r = self.client.post(reverse("accounts:signup"), signup_data(self.group))
        self.assertTrue(r.context["form"].has_error("email"))

    def test_login_is_made_from_the_email_and_kept_unique(self):
        make_student("aigerim", email="first@example.kz")
        make_student("Aigerim-2", email="second@example.kz")
        self.client.post(reverse("accounts:signup"), signup_data(self.group, username="ignored"))
        user = User.objects.get(email__iexact="aigerim@example.kz")
        self.assertEqual(user.username, "aigerim-3")
        self.assertFalse(User.objects.filter(username="ignored").exists())

    def test_username_from_email_keeps_allowed_characters_only(self):
        from apps.accounts.services.registration import username_from_email

        self.assertEqual(username_from_email("Ай.Gerim+lab@uni.kz"), "gerimlab")
        self.assertEqual(username_from_email("Әсем@uni.kz"), "user")
        self.assertEqual(username_from_email("a.b_c-d@uni.kz"), "a.b_c-d")

    def test_signed_in_user_is_redirected(self):
        self.client.force_login(make_student("s"))
        self.assertEqual(self.client.get(reverse("accounts:signup")).status_code, 302)


@override_settings(LANGUAGE_CODE="en")
class SignupCascadeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.group = make_group(name="Chem-23-1")
        cls.closed = make_group(name="Chem-19-1", department=cls.group.department, is_active=False)
        cls.other = make_group(name="Bio-23-1")

    def cascade(self, **params):
        r = self.client.get(reverse("accounts:signup_cascade"), params, HTTP_HX_REQUEST="true")
        self.assertEqual(r.status_code, 200)
        return r.context["form"], r.content.decode()

    def test_children_follow_the_parent(self):
        dep = self.group.department
        form, html = self.cascade(university=dep.faculty.university_id)
        self.assertEqual(list(form.fields["faculty"].queryset), [dep.faculty])
        self.assertFalse(form.fields["department"].queryset.exists())
        form, html = self.cascade(university=dep.faculty.university_id, faculty=dep.faculty_id, department=dep.pk)
        self.assertEqual(list(form.fields["group"].queryset), [self.group])  # inactive group hidden
        self.assertIn("Chem-23-1", html)
        self.assertNotIn("Chem-19-1", html)
        self.assertNotIn("Bio-23-1", html)

    def test_changing_the_university_drops_stale_children(self):
        dep = self.group.department
        other_uni = self.other.department.faculty.university_id
        form, html = self.cascade(university=other_uni, faculty=dep.faculty_id, department=dep.pk, group=self.group.pk)
        self.assertNotIn(dep.faculty, form.fields["faculty"].queryset)
        self.assertFalse(form.fields["department"].queryset.exists())
        self.assertFalse(form.fields["group"].queryset.exists())
        self.assertNotIn("Chem-23-1", html)

    def test_signup_page_renders(self):
        r = self.client.get(reverse("accounts:signup"))
        self.assertContains(r, 'id="signup-cascade"')
        self.assertContains(r, reverse("accounts:signup_cascade"))


class LanguageTests(TestCase):
    def test_login_page_is_kazakh_by_default(self):
        r = self.client.get(reverse("accounts:login"), HTTP_ACCEPT_LANGUAGE="ru")
        self.assertContains(r, "Логин немесе email")  # also proves locale/*.po compile

    def test_set_language_is_saved_on_the_account(self):
        user = make_student("s")
        self.client.force_login(user)
        self.client.post(reverse("set_language"), {"language": "ru", "next": "/"})
        user.refresh_from_db()
        self.assertEqual(user.language, "ru")
        # the saved language wins over a different cookie on the next request
        self.client.cookies["django_language"] = "kk"
        r = self.client.get(reverse("student:courses"))
        self.assertEqual(r["Content-Language"], "ru")


class ProfileTests(TestCase):
    def test_profile_is_created_once(self):
        user = make_student("s", group=make_group())
        self.assertEqual(StudentProfile.objects.filter(user=user).count(), 1)
