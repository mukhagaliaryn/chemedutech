from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.organizations.testing import make_student

from . import selectors, services
from .models import Notification


@override_settings(ALLOWED_HOSTS=["testserver"])
class NotificationTests(TestCase):
    def setUp(self):
        self.student = make_student("s1")
        self.other = make_student("s2")
        self.client.force_login(self.student)

    def test_notify_and_count(self):
        services.notify(self.student, Notification.Kind.GRADED, "Практикалық жұмыс 1", "/learn/chemistry/1/5/")
        services.notify(self.other, Notification.Kind.RETURNED, "x")
        self.assertEqual(selectors.unread_count(self.student), 1)
        self.assertEqual(services.mark_all_read(self.student), 1)
        self.assertEqual(selectors.unread_count(self.student), 0)
        self.assertEqual(selectors.unread_count(self.other), 1)

    def test_open_marks_read_and_follows_the_link(self):
        n = services.notify(self.student, Notification.Kind.UNLOCKED, "Видеосабақ", "/me/courses/")
        r = self.client.get(reverse("feedback:open", args=[n.pk]))
        self.assertRedirects(r, "/me/courses/", fetch_redirect_response=False)
        n.refresh_from_db()
        self.assertTrue(n.is_read)

    def test_foreign_and_external_links(self):
        theirs = services.notify(self.other, Notification.Kind.GRADED, "x", "/me/")
        r = self.client.get(reverse("feedback:open", args=[theirs.pk]))
        self.assertRedirects(r, reverse("feedback:notifications"))
        theirs.refresh_from_db()
        self.assertFalse(theirs.is_read)
        evil = services.notify(self.student, Notification.Kind.GRADED, "x", "https://evil.example.com/")
        r = self.client.get(reverse("feedback:open", args=[evil.pk]))
        self.assertRedirects(r, reverse("feedback:notifications"))

    def test_pages(self):
        services.notify(self.student, Notification.Kind.RETURNED, "Практикалық жұмыс 2", "/me/")
        r = self.client.get(reverse("feedback:notifications"))
        self.assertContains(r, "Практикалық жұмыс 2")
        self.assertEqual(r.context["unread"], 1)
        r = self.client.get(reverse("feedback:badge"), headers={"HX-Request": "true"})
        self.assertContains(r, 'id="notif-badge"')
        self.assertContains(r, 'hx-swap-oob="true"')
        self.client.post(reverse("feedback:read_all"))
        self.assertEqual(selectors.unread_count(self.student), 0)

    def test_badge_in_the_cabinet(self):
        services.notify(self.student, Notification.Kind.GRADED, "x")
        r = self.client.get(reverse("student:courses"))
        self.assertContains(r, 'id="notif-badge"')
        self.assertContains(r, reverse("feedback:badge"))

    def test_teacher_sees_the_teacher_layout(self):
        teacher = User.objects.create_user("t", "t@example.kz", "x", role=User.Role.TEACHER)
        self.client.force_login(teacher)
        r = self.client.get(reverse("feedback:notifications"))
        self.assertTemplateUsed(r, "layouts/teacher.html")

    def test_login_required(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("feedback:notifications")).status_code, 302)
        self.assertEqual(self.client.get(reverse("feedback:badge")).status_code, 302)
