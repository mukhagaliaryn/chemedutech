from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.courses.models import Course, Enrollment, Module, Stage, Topic
from apps.courses.services import enroll
from apps.organizations.testing import make_student

from . import services
from .grading import grade_for
from .models import CourseResult, ProgressEvent, StageProgress, TopicResult

S = StageProgress.Status
FULL = ["theory", "video", "lab", "practice", "test"]


def build_course(*modules, sequential=True, **course_fields):
    """modules: lists of topics; a topic is a list of stage kinds. Returns (course, [[stages per topic]])."""
    course = Course.objects.create(
        title="C", slug=f"c{Course.objects.count()}", status="published", is_sequential=sequential, **course_fields
    )
    topics, number = [], 0
    for m_index, topic_kinds in enumerate(modules, start=1):
        module = Module.objects.create(course=course, order=m_index, title=f"M{m_index}")
        for kinds in topic_kinds:
            number += 1
            topic = Topic.objects.create(
                module=module, number=number, order=number, title=f"T{number}", is_published=True
            )
            topics.append(
                [
                    Stage.objects.create(topic=topic, order=i, kind=k, title=f"{k} {i}")
                    for i, k in enumerate(kinds, start=1)
                ]
            )
    return course, topics


class Base(TestCase):
    def setUp(self):
        self.student = make_student("s1")
        self.teacher = User.objects.create_user("t", "t@example.kz", "x", role=User.Role.TEACHER)

    def enrol(self, course):
        e = enroll(self.student, course, "admin")
        services.ensure_progress(e)
        return e

    def status(self, enrollment, stage):
        return StageProgress.objects.get(enrollment=enrollment, stage=stage).status

    def pass_all(self, enrollment, stages, score=100):
        for stage in stages:
            services.complete_stage(enrollment, stage, score)


class GatingTests(Base):
    def test_only_the_first_stage_opens_on_enrolment(self):
        course, (t1, t2) = build_course([FULL, FULL])
        e = self.enrol(course)
        self.assertEqual(self.status(e, t1[0]), S.AVAILABLE)
        self.assertTrue(all(self.status(e, s) == S.LOCKED for s in t1[1:] + t2))
        self.assertEqual(TopicResult.objects.get(enrollment=e, topic=t1[0].topic).status, "available")
        self.assertEqual(TopicResult.objects.get(enrollment=e, topic=t2[0].topic).status, "locked")

    def test_stages_open_one_after_another(self):
        course, (t1,) = build_course([FULL])
        e = self.enrol(course)
        for i, stage in enumerate(t1):
            self.assertEqual(self.status(e, stage), S.AVAILABLE)
            if i + 1 < len(t1):
                self.assertEqual(self.status(e, t1[i + 1]), S.LOCKED)
            services.complete_stage(e, stage, 90)
            self.assertEqual(self.status(e, stage), S.PASSED)

    def test_next_topic_opens_after_the_topic_is_completed(self):
        course, (t1, t2) = build_course([["theory", "test"], ["theory"]])
        e = self.enrol(course)
        services.complete_stage(e, t1[0], 100)
        self.assertEqual(self.status(e, t2[0]), S.LOCKED)
        services.complete_stage(e, t1[1], 100)
        self.assertEqual(self.status(e, t2[0]), S.AVAILABLE)
        self.assertEqual(TopicResult.objects.get(enrollment=e, topic=t1[0].topic).status, "completed")

    def test_url_bypass_is_impossible(self):
        """Opening a locked stage's URL directly: no access, and its result cannot be recorded."""
        course, (t1, t2) = build_course([FULL, FULL])
        e = self.enrol(course)
        for stage in (t1[2], t2[0]):
            self.assertFalse(services.can_access(e, stage))
            with self.assertRaises(services.StageLocked):
                services.start_stage(e, stage)
            with self.assertRaises(services.StageLocked):
                services.complete_stage(e, stage, 100)
        self.assertEqual(self.status(e, t1[2]), S.LOCKED)

    def test_failed_checkpoint_keeps_the_next_stage_closed(self):
        course, (t1,) = build_course([FULL])
        e = self.enrol(course)
        services.start_stage(e, t1[0])
        services.complete_stage(e, t1[0], 50, passed=False)  # the quiz's verdict
        self.assertEqual(self.status(e, t1[0]), S.IN_PROGRESS)
        self.assertEqual(self.status(e, t1[1]), S.LOCKED)
        self.assertTrue(services.can_access(e, t1[0]))  # may retake

    def test_quiz_verdict_overrides_the_stage_pass_mark(self):
        course, (t1,) = build_course([["theory", "test"]])
        e = self.enrol(course)
        # 70 % is above the stage's 60 %, but the checkpoint quiz requires 75 %
        services.complete_stage(e, t1[0], 70, passed=False)
        self.assertEqual(self.status(e, t1[1]), S.LOCKED)
        services.complete_stage(e, t1[0], 80, passed=True)
        self.assertEqual(self.status(e, t1[1]), S.AVAILABLE)

    def test_stage_pass_mark_is_used_without_a_verdict(self):
        course, (t1,) = build_course([["lab", "test"]])
        t1[0].pass_percent = 70
        t1[0].save()
        e = self.enrol(course)
        services.complete_stage(e, t1[0], 65)
        self.assertEqual(self.status(e, t1[0]), S.IN_PROGRESS)
        services.complete_stage(e, t1[0], 70)
        self.assertEqual(self.status(e, t1[0]), S.PASSED)

    def test_attempts_exhausted_passes_with_attention(self):
        course, (t1,) = build_course([["practice", "test"]])
        e = self.enrol(course)
        services.complete_stage(e, t1[0], 40, attempts_exhausted=True)
        sp = StageProgress.objects.get(enrollment=e, stage=t1[0])
        self.assertEqual(sp.status, S.PASSED)
        self.assertTrue(sp.needs_attention)
        self.assertEqual(self.status(e, t1[1]), S.AVAILABLE)

    def test_passed_stage_is_not_downgraded_by_a_worse_retake(self):
        course, (t1,) = build_course([["theory", "test"]])
        e = self.enrol(course)
        services.complete_stage(e, t1[0], 100)
        services.complete_stage(e, t1[0], 20, passed=False)
        self.assertEqual(self.status(e, t1[0]), S.PASSED)
        self.assertEqual(self.status(e, t1[1]), S.AVAILABLE)

    def test_three_practices_open_one_by_one(self):
        course, (t1,) = build_course([["theory", "practice", "practice", "practice", "test"]])
        e = self.enrol(course)
        services.complete_stage(e, t1[0], 100)
        p1, p2, p3 = t1[1:4]
        self.assertEqual([self.status(e, s) for s in (p1, p2, p3)], [S.AVAILABLE, S.LOCKED, S.LOCKED])
        services.complete_stage(e, p1, 80)
        self.assertEqual([self.status(e, s) for s in (p2, p3)], [S.AVAILABLE, S.LOCKED])
        services.complete_stage(e, p2, 80)
        self.assertEqual(self.status(e, p3), S.AVAILABLE)

    def test_needs_review_opens_the_next_stage_but_not_the_next_topic(self):
        """Decision D3: awaiting_check counts for the order of stages, not for topic completion."""
        course, (t1, t2) = build_course([["practice", "test"], ["theory"]])
        e = self.enrol(course)
        services.complete_stage(e, t1[0], 55, awaiting_check=True)
        self.assertEqual(self.status(e, t1[0]), S.AWAITING_CHECK)
        self.assertEqual(self.status(e, t1[1]), S.AVAILABLE)
        services.complete_stage(e, t1[1], 100)
        topic = TopicResult.objects.get(enrollment=e, topic=t1[0].topic)
        self.assertEqual(topic.status, "in_progress")
        self.assertEqual(self.status(e, t2[0]), S.LOCKED)
        # the teacher confirms the grade → the topic completes and the next one opens
        services.confirm_stage(e, t1[0], 75, by=self.teacher)
        self.assertEqual(TopicResult.objects.get(pk=topic.pk).status, "completed")
        self.assertEqual(self.status(e, t2[0]), S.AVAILABLE)
        self.assertTrue(ProgressEvent.objects.filter(action="confirmed", actor=self.teacher).exists())

    def test_returned_practice_goes_back_to_in_progress(self):
        course, (t1, t2) = build_course([["practice", "lab", "test"], ["theory"]])
        e = self.enrol(course)
        services.complete_stage(e, t1[0], 90)
        services.complete_stage(e, t1[1], 90)
        services.return_stage(e, t1[0], by=self.teacher)
        self.assertEqual(self.status(e, t1[0]), S.IN_PROGRESS)
        self.assertEqual(self.status(e, t1[1]), S.PASSED)  # finished work is kept
        self.assertEqual(self.status(e, t1[2]), S.LOCKED)  # not started yet → waits again
        services.complete_stage(e, t1[0], 95)
        services.complete_stage(e, t1[2], 95)
        self.assertEqual(self.status(e, t2[0]), S.AVAILABLE)

    def test_teacher_unlock_survives_recalculation(self):
        course, (t1, t2) = build_course([FULL, FULL])
        e = self.enrol(course)
        services.unlock_stage(e, t2[3], by_teacher=self.teacher)
        services.recalculate(e)
        self.assertTrue(services.can_access(e, t2[3]))
        self.assertFalse(services.can_access(e, t2[2]))
        sp = StageProgress.objects.get(enrollment=e, stage=t2[3])
        self.assertEqual(sp.unlocked_by, self.teacher)
        self.assertTrue(ProgressEvent.objects.filter(enrollment=e, action="unlocked", stage=t2[3]).exists())
        self.assertEqual(TopicResult.objects.get(enrollment=e, topic=t2[0].topic).status, "available")

    def test_blocking_stage_names_what_to_finish_first(self):
        course, (t1, t2) = build_course([["theory", "lab", "test"], ["theory"]])
        e = self.enrol(course)
        self.assertEqual(services.blocking_stage(e, t1[2]), t1[0])
        services.complete_stage(e, t1[0], 100)
        self.assertEqual(services.blocking_stage(e, t1[2]), t1[1])
        self.assertEqual(services.blocking_stage(e, t2[0]), t1[1])
        self.assertIsNone(services.blocking_stage(e, t1[1]))

    def test_optional_stage_does_not_block_and_is_not_scored(self):
        course, (t1,) = build_course([["theory", "video", "test"]])
        t1[1].is_required = False
        t1[1].save()
        e = self.enrol(course)
        services.complete_stage(e, t1[0], 100)
        self.assertEqual(self.status(e, t1[2]), S.AVAILABLE)
        services.complete_stage(e, t1[2], 50, passed=True)
        topic = TopicResult.objects.get(enrollment=e, topic=t1[0].topic)
        self.assertEqual(topic.status, "completed")
        self.assertEqual(topic.score_percent, Decimal("66.67"))  # (10·100 + 20·50) / 30

    def test_non_sequential_course_opens_everything(self):
        course, (t1, t2) = build_course([FULL, FULL], sequential=False)
        e = self.enrol(course)
        self.assertTrue(all(self.status(e, s) == S.AVAILABLE for s in t1 + t2))

    def test_unpublished_topic_is_skipped(self):
        course, (t1, t2, t3) = build_course([["theory"], ["theory"], ["theory"]])
        Topic.objects.filter(pk=t2[0].topic_id).update(is_published=False)
        e = self.enrol(course)
        services.complete_stage(e, t1[0], 100)
        self.assertEqual(self.status(e, t3[0]), S.AVAILABLE)
        self.assertFalse(services.can_access(e, t2[0]))
        self.assertEqual(CourseResult.objects.get(enrollment=e).topics_total, 2)

    def test_stage_added_later_gets_progress(self):
        course, (t1,) = build_course([["theory", "test"]])
        e = self.enrol(course)
        self.pass_all(e, t1)
        extra = Stage.objects.create(topic=t1[0].topic, order=3, kind="practice", title="New practice")
        services.recalculate(e)
        self.assertEqual(self.status(e, extra), S.AVAILABLE)  # the earlier ones are passed
        self.assertEqual(TopicResult.objects.get(enrollment=e, topic=t1[0].topic).status, "in_progress")

    def test_dropped_student_has_no_access(self):
        course, (t1,) = build_course([["theory"]])
        e = self.enrol(course)
        Enrollment.objects.filter(pk=e.pk).update(status="dropped")
        e.refresh_from_db()
        self.assertFalse(services.can_access(e, t1[0]))

    def test_time_is_added_in_capped_chunks(self):
        course, (t1,) = build_course([["theory"]])
        e = self.enrol(course)
        services.add_time(e, t1[0], 120)
        services.add_time(e, t1[0], 10_000)
        services.add_time(e, t1[0], -5)
        self.assertEqual(StageProgress.objects.get(enrollment=e, stage=t1[0]).time_spent_s, 120 + 1800)


class ScoringTests(Base):
    def test_default_kind_shares(self):
        course, (t1,) = build_course([FULL])
        e = self.enrol(course)
        for stage, score in zip(t1, (100, 80, 90, 70, 60), strict=True):
            services.complete_stage(e, stage, score)
        # (10·100 + 10·80 + 40·90 + 20·70 + 20·60) / 100
        self.assertEqual(TopicResult.objects.get(enrollment=e).score_percent, Decimal("80.00"))

    def test_kind_share_is_split_between_stages_of_that_kind(self):
        course, (t1,) = build_course([["theory", "video", "lab", "practice", "practice", "practice", "test"]])
        weights = services.stage_weights(course, t1)
        practice = [weights[s.pk] for s in t1 if s.kind == "practice"]
        self.assertEqual(len(practice), 3)
        self.assertAlmostEqual(float(practice[0]), 20 / 3, places=4)
        self.assertEqual(sum(weights.values()), Decimal("100"))
        e = self.enrol(course)
        for stage, score in zip(t1, (100, 100, 100, 100, 70, 40, 100), strict=True):
            services.complete_stage(e, stage, score, passed=True)
        # practice average 70 → 20·70 = 1400; the rest 80·100 = 8000 → 94.00
        self.assertEqual(TopicResult.objects.get(enrollment=e).score_percent, Decimal("94.00"))

    def test_missing_kind_is_normalised(self):
        course, (t1,) = build_course([["theory", "lab", "practice", "test"]])  # no video
        e = self.enrol(course)
        for stage, score in zip(t1, (100, 50, 100, 100), strict=True):
            services.complete_stage(e, stage, score, passed=True)
        # (10·100 + 40·50 + 20·100 + 20·100) / 90 = 7000 / 90
        self.assertEqual(TopicResult.objects.get(enrollment=e).score_percent, Decimal("77.78"))

    def test_course_specific_kind_shares(self):
        course, (t1,) = build_course([["lab", "test"]], stage_kind_weights={"lab": 50, "test": 50})
        e = self.enrol(course)
        services.complete_stage(e, t1[0], 100)
        services.complete_stage(e, t1[1], 60)
        self.assertEqual(TopicResult.objects.get(enrollment=e).score_percent, Decimal("80.00"))

    def test_author_weight_overrides_the_share(self):
        course, (t1,) = build_course([["lab", "test"]])
        t1[1].weight = Decimal("40")  # test now weighs as much as the lab
        t1[1].save()
        e = self.enrol(course)
        services.complete_stage(e, t1[0], 100)
        services.complete_stage(e, t1[1], 60)
        self.assertEqual(TopicResult.objects.get(enrollment=e).score_percent, Decimal("80.00"))

    def test_module_and_course_weighted_averages_and_letter(self):
        course, (t1, t2, t3) = build_course([["test"], ["test"]], [["test"]])
        Topic.objects.filter(pk=t2[0].topic_id).update(weight=3)
        Module.objects.filter(pk=t3[0].topic.module_id).update(weight=2)
        e = self.enrol(course)
        services.complete_stage(e, t1[0], 100)
        services.complete_stage(e, t2[0], 60)
        result = CourseResult.objects.get(enrollment=e)
        # module 1 current = (1·100 + 3·60) / 4 = 70; module 2 has nothing yet
        self.assertEqual(result.current_percent, Decimal("70.00"))
        self.assertIsNone(result.score_percent)
        self.assertEqual(result.letter, "")
        self.assertEqual(result.topics_completed, 2)
        services.complete_stage(e, t3[0], 85)
        result.refresh_from_db()
        # course = (1·70 + 2·85) / 3 = 80
        self.assertEqual(result.score_percent, Decimal("80.00"))
        self.assertEqual((result.letter, result.gpa_points), ("B", Decimal("3.00")))
        self.assertTrue(result.passed)
        self.assertIsNotNone(result.completed_at)
        e.refresh_from_db()
        self.assertEqual(e.status, "completed")
        self.assertTrue(ProgressEvent.objects.filter(enrollment=e, action="course_completed").exists())

    def test_current_score_ignores_unfinished_topics(self):
        course, (t1, t2) = build_course([["theory", "test"], ["theory", "test"]])
        e = self.enrol(course)
        self.pass_all(e, t1, score=90)
        services.complete_stage(e, t2[0], 10, passed=True)  # t2 not finished
        result = CourseResult.objects.get(enrollment=e)
        self.assertEqual(result.current_percent, Decimal("90.00"))
        self.assertIsNone(result.score_percent)

    def test_failing_course_and_reopening(self):
        course, (t1,) = build_course([["practice"]], passing_score=50)
        e = self.enrol(course)
        services.complete_stage(e, t1[0], 30, attempts_exhausted=True)
        result = CourseResult.objects.get(enrollment=e)
        self.assertEqual((result.letter, result.passed), ("F", False))
        services.return_stage(e, t1[0], by=self.teacher)  # teacher returns → course is open again
        result.refresh_from_db()
        e.refresh_from_db()
        self.assertIsNone(result.completed_at)
        self.assertEqual(e.status, "active")

    def test_grade_scale(self):
        cases = {
            100: "A", 95: "A", 94.6: "A", 94.4: "A-", 90: "A-", 89: "B+", 85: "B+", 80: "B", 75: "B-",
            70: "C+", 65: "C", 60: "C-", 55: "D+", 50: "D", 49.4: "F", 0: "F",
        }  # fmt: skip
        for percent, letter in cases.items():
            with self.subTest(percent):
                self.assertEqual(grade_for(percent).letter, letter)
        self.assertEqual(grade_for(91).gpa, Decimal("3.67"))


class AdminTests(Base):
    def test_admin_pages_and_unlock_action(self):
        course, (t1,) = build_course([FULL])
        e = self.enrol(course)
        admin = User.objects.create_superuser("root", "root@example.kz", "x")
        self.client.force_login(admin)
        for name in ("stageprogress", "topicresult", "moduleresult", "courseresult", "progressevent"):
            self.assertEqual(self.client.get(reverse(f"admin:progress_{name}_changelist")).status_code, 200)
        sp = StageProgress.objects.get(enrollment=e, stage=t1[3])
        self.client.post(
            reverse("admin:progress_stageprogress_changelist"),
            {"action": "open_for_student", "_selected_action": [sp.pk]},
        )
        sp.refresh_from_db()
        self.assertEqual((sp.status, sp.unlocked_by), (S.AVAILABLE, admin))
