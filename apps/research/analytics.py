"""Course analytics for the teacher / researcher (ARCHITECTURE §8, STEP-12). Reads only.

Scope = the teacher's enrolments in one course (optionally one group), one topic or the whole course.
Cohorts come from Enrollment.research_cohort (the snapshot at enrolment, D36).
"""

from collections import defaultdict

from django.db.models import Count
from django.utils.translation import gettext as _

from apps.assessments.models import QuizAttempt
from apps.core import stats
from apps.courses import selectors as course_selectors
from apps.courses.models import Stage, Topic
from apps.labs.engine import get_lab
from apps.labs.models import LabAttempt, LabEvent
from apps.practice.models import AIGrade, TeacherReview
from apps.practice.services import sampling
from apps.programme import selectors as programme_selectors
from apps.progress.models import StageProgress, TopicResult

COHORTS = ("experimental", "control")
DONE = (StageProgress.Status.PASSED, StageProgress.Status.AWAITING_CHECK)
ERROR_TYPES = ("order_error", "safety_warning", "wrong_item", "wrong_choice")


def scope(user, course, group=None, topic=None):
    """(enrollments, topics, stages) of the analysis."""
    enrollments = list(course_selectors.teacher_enrollments(user, course).select_related("student", "group"))
    if group is not None:
        enrollments = [e for e in enrollments if e.group_id == group.pk]
    topics = (
        [topic] if topic else list(Topic.objects.filter(module__course=course, is_published=True).order_by("number"))
    )
    stages = list(
        Stage.objects.filter(topic__in=topics)
        .select_related("topic", "checkpoint_quiz", "test_content__quiz", "lab_content")
        .order_by("topic__number", "order", "pk")
    )
    return enrollments, topics, stages


def _by_cohort(enrollments):
    groups = defaultdict(list)
    for e in enrollments:
        groups[e.research_cohort or ""].append(e.pk)
    return groups


# --- per-enrolment measures (also the CSV) ------------------------------------------------------


def measures(enrollments, topics, stages) -> dict[int, dict]:
    """{enrollment_id: {test, lab, checkpoint_first, completed, time_s}} over the selected topics."""
    ids = [e.pk for e in enrollments]
    out = {pk: {"test": [], "lab": [], "checkpoint_first": [], "completed": 0, "time_s": 0} for pk in ids}
    kinds = {s.pk: s.kind for s in stages}
    for sp in StageProgress.objects.filter(enrollment_id__in=ids, stage__in=stages):
        row = out[sp.enrollment_id]
        row["time_s"] += sp.time_spent_s
        if sp.status in DONE and sp.score_percent is not None and kinds[sp.stage_id] in ("test", "lab"):
            row[kinds[sp.stage_id]].append(sp.score_percent)
    checkpoints = [s.checkpoint_quiz_id for s in stages if s.checkpoint_quiz_id]
    for a in QuizAttempt.objects.filter(enrollment_id__in=ids, quiz_id__in=checkpoints, attempt_no=1).exclude(
        finished_at=None
    ):
        out[a.enrollment_id]["checkpoint_first"].append(a.passed)
    for r in TopicResult.objects.filter(enrollment_id__in=ids, topic__in=topics, status=TopicResult.Status.COMPLETED):
        out[r.enrollment_id]["completed"] += 1
    for row in out.values():
        row["test_mean"] = stats.describe(row["test"])["mean"]
        row["lab_mean"] = stats.describe(row["lab"])["mean"]
        row["completed_share"] = row["completed"] / len(topics) * 100 if topics else None
    return out


def _fmt(value, kind):
    if value is None:
        return "—"
    if kind == "time":
        minutes = int(value) // 60
        hours, minutes = divmod(minutes, 60)
        return _("%(h)s h %(m)s min") % {"h": hours, "m": minutes} if hours else _("%(m)s min") % {"m": minutes}
    if kind == "rate":
        return f"{value:.0f}%"
    return f"{value:.1f}"


def _diff(a, b, kind):
    if a is None or b is None:
        return "—"
    d = a - b
    if kind == "time":
        return f"{'+' if d >= 0 else '−'}{_fmt(abs(d), 'time')}"
    if kind == "rate":
        return _("%(sign)s%(d)s p.p.") % {"sign": "+" if d >= 0 else "−", "d": f"{abs(d):.0f}"}
    return f"{'+' if d >= 0 else '−'}{abs(d):.1f}"


def cohort_table(enrollments, per) -> dict:
    """Control vs experimental: mean, median, n of each measure (significance tests are done on the CSV)."""
    groups = _by_cohort(enrollments)
    spec = [
        ("test_mean", _("Topic test score"), "score"),
        ("lab_mean", _("Lab score"), "score"),
        ("checkpoint_first", _("Checkpoint quizzes passed at the first attempt"), "rate"),
        ("completed_share", _("Topics completed"), "rate"),
        ("time_s", _("Time spent on the topics"), "time"),
    ]
    rows = []
    for key, title, kind in spec:
        cells = {}
        for cohort in COHORTS:
            values = [per[pk][key] for pk in groups.get(cohort, [])]
            if key == "checkpoint_first":
                d = stats.share([flag for v in values for flag in v])
                cells[cohort] = {"mean": d["rate"], "median": None, "n": d["n"]}
            else:
                if key == "time_s":
                    values = [v for v in values if v]  # only students who opened the topics
                cells[cohort] = stats.describe(values)
        rows.append(
            {
                "title": title,
                "kind": kind,
                "cells": [
                    {
                        "value": _fmt(cells[c]["mean"], kind),
                        "median": _fmt(cells[c]["median"], kind)
                        if cells[c]["median"] is not None and kind != "rate"
                        else "",
                        "n": cells[c]["n"],
                    }
                    for c in COHORTS
                ],
                "diff": _diff(cells["experimental"]["mean"], cells["control"]["mean"], kind),
            }
        )
    return {
        "rows": rows,
        "n": {c: len(groups.get(c, [])) for c in COHORTS},
        "unassigned": len(groups.get("", [])),
    }


# --- stages ---------------------------------------------------------------------------------------


def stage_overview(enrollments, stages) -> list[dict]:
    """Funnel (students done per stage) and mean stage score per cohort."""
    ids = [e.pk for e in enrollments]
    cohort_of = {e.pk: e.research_cohort for e in enrollments}
    done = defaultdict(set)
    scores = defaultdict(lambda: defaultdict(list))
    for sp in StageProgress.objects.filter(enrollment_id__in=ids, stage__in=stages, status__in=DONE):
        done[sp.stage_id].add(sp.enrollment_id)
        if sp.score_percent is not None:
            scores[sp.stage_id][cohort_of[sp.enrollment_id]].append(sp.score_percent)
            scores[sp.stage_id]["all"].append(sp.score_percent)
    rows = []
    for s in stages:
        rows.append(
            {
                "stage": s,
                "done": len(done[s.pk]),
                "total": len(ids),
                "share": len(done[s.pk]) / len(ids) * 100 if ids else 0,
                "mean": {k: stats.describe(scores[s.pk][k])["mean"] for k in ("all", *COHORTS)},
            }
        )
    return rows


# --- lab --------------------------------------------------------------------------------------------


def _step_titles(lab_key, experiment_key):
    lab = get_lab(lab_key)
    spec = lab.experiment(experiment_key) if lab else None
    if spec is None:
        return None, {}
    return spec, {step.key: step.command for step in spec.steps}


def lab_errors(enrollments, stages, limit=15) -> dict:
    """Where students go wrong: error events by experiment × step × type (students, not clicks) + time per step."""
    ids = [e.pk for e in enrollments]
    lab_stages = [s for s in stages if s.kind == "lab"]
    attempts = LabAttempt.objects.filter(enrollment_id__in=ids, stage__in=lab_stages)
    tried = {
        (r["lab_key"], r["experiment_key"]): r["n"]
        for r in attempts.values("lab_key", "experiment_key").annotate(n=Count("enrollment", distinct=True))
    }
    rows = (
        LabEvent.objects.filter(attempt__in=attempts, type__in=ERROR_TYPES)
        .values("attempt__lab_key", "attempt__experiment_key", "step", "type")
        .annotate(students=Count("attempt__enrollment", distinct=True), events=Count("id"))
        .order_by("-students", "-events")
    )
    times = defaultdict(list)
    for a in attempts.exclude(status=LabAttempt.Status.IN_PROGRESS).only("lab_key", "experiment_key", "step_times"):
        for step, ms in (a.step_times or {}).items():
            if isinstance(ms, int | float):
                times[(a.lab_key, a.experiment_key, step)].append(ms / 1000)
    type_labels = dict(LabEvent.Type.choices)
    errors = []
    for r in rows[:limit]:
        lab_key, exp_key = r["attempt__lab_key"], r["attempt__experiment_key"]
        spec, titles = _step_titles(lab_key, exp_key)
        errors.append(
            {
                "experiment": f"{spec.number}. {spec.title}" if spec else exp_key,
                "number": spec.number if spec else "",
                "step": titles.get(r["step"], r["step"] or "—"),
                "type": r["type"],
                "type_label": type_labels.get(r["type"], r["type"]),
                "students": r["students"],
                "tried": tried.get((lab_key, exp_key), 0),
                "events": r["events"],
                "time": stats.describe(times.get((lab_key, exp_key, r["step"]), []))["mean"],
            }
        )
    experiments = []
    for (lab_key, exp_key), n in sorted(tried.items()):
        spec, titles = _step_titles(lab_key, exp_key)
        if spec is None:
            continue
        steps = [
            {"title": step.command, "time": stats.describe(times.get((lab_key, exp_key, step.key), []))}
            for step in spec.steps
        ]
        experiments.append({"title": f"{spec.number}. {spec.title}", "students": n, "steps": steps})
    return {"errors": errors, "experiments": experiments}


# --- AI ↔ teacher -----------------------------------------------------------------------------------


def ai_agreement(enrollments) -> dict:
    """How far the teacher's checked grades are from the AI's (§5.6).

    Answer level: AI and teacher points as % of the field's points → mean difference (teacher − AI),
    mean absolute difference, Pearson r. Criterion level: Cohen's kappa and exact agreement on the points
    of each criterion (reviews made on the grading page store them). The latest review of an answer counts.
    """
    ids = [e.pk for e in enrollments]
    reviews = (
        TeacherReview.objects.filter(answer__submission__enrollment_id__in=ids, ai_points__isnull=False)
        .select_related("answer__item")
        .order_by("answer_id", "-created_at", "-pk")
    )
    latest = {}
    for r in reviews:
        latest.setdefault(r.answer_id, r)
    grades = {g.answer_id: g for g in AIGrade.objects.filter(answer_id__in=latest)}
    ai, teacher, criteria_pairs = [], [], []
    for answer_id, review in latest.items():
        top = review.answer.item.points or 0
        if top:
            ai.append(float(review.ai_points) / float(top) * 100)
            teacher.append(float(review.teacher_points) / float(top) * 100)
        grade = grades.get(answer_id)
        if grade and review.criteria_scores:
            ai_by = {c.get("criterion_id"): c.get("points") for c in grade.criteria_scores}
            for c in review.criteria_scores:
                if c.get("criterion_id") in ai_by and ai_by[c["criterion_id"]] is not None:
                    criteria_pairs.append((stats.label(ai_by[c["criterion_id"]]), stats.label(c.get("points", 0))))
    diffs = [t - a for a, t in zip(ai, teacher, strict=True)]
    exact = sum(1 for a, b in criteria_pairs if a == b)
    return {
        "answers": len(ai),
        "mean_diff": stats.describe(diffs)["mean"],
        "mean_abs_diff": stats.describe([abs(d) for d in diffs])["mean"],
        "pearson": stats.pearson(ai, teacher),
        "criteria": len(criteria_pairs),
        "kappa": stats.cohen_kappa(criteria_pairs),
        "exact": exact / len(criteria_pairs) * 100 if criteria_pairs else None,
    }


def sample_status(enrollments) -> dict:
    ids = [e.pk for e in enrollments]
    population = sampling.ai_graded(ids)
    sampled = population.exclude(sampled_at=None)
    return {
        "ai_graded": population.count(),
        "sampled": sampled.count(),
        "checked": sampled.filter(teacher_override=True).count(),
    }


# --- pre/post knowledge test (STEP-22) ---------------------------------------------------------------


def pre_post_scores(enrollments, course) -> dict[int, dict]:
    """{enrollment_id: {"pre", "post", "gain", "norm_gain"}} from the finished attempts of the course's pre/post test.

    gain = post − pre (p.p.); norm_gain = Hake's (post − pre) / (100 − pre), undefined when pre is 100.
    """
    out = {e.pk: {"pre": None, "post": None, "gain": None, "norm_gain": None} for e in enrollments}
    if not course.benchmark_quiz_id:
        return out
    attempts = (
        QuizAttempt.objects.filter(enrollment_id__in=out, quiz_id=course.benchmark_quiz_id, phase__in=("pre", "post"))
        .exclude(finished_at=None)
        .order_by("attempt_no")
    )
    for a in attempts:
        row = out[a.enrollment_id]
        if row[a.phase] is None:  # the first finished attempt of a phase counts
            row[a.phase] = float(a.percent)
    for row in out.values():
        if row["pre"] is not None and row["post"] is not None:
            row["gain"] = row["post"] - row["pre"]
            if row["pre"] < 100:
                row["norm_gain"] = row["gain"] / (100 - row["pre"])
    return out


def pre_post_table(enrollments, scores) -> list[dict]:
    """Per cohort (+ everybody): pre and post over all who took them, gain and normalized gain over pairs."""
    groups = _by_cohort(enrollments)
    everyone = [e.pk for e in enrollments]
    rows = []
    for key, ids in (*((c, groups.get(c, [])) for c in COHORTS), ("all", everyone)):
        pairs = [scores[pk] for pk in ids if scores[pk]["gain"] is not None]
        rows.append(
            {
                "cohort": key,
                "students": len(ids),
                "pre": stats.describe([scores[pk]["pre"] for pk in ids]),
                "post": stats.describe([scores[pk]["post"] for pk in ids]),
                "paired": len(pairs),
                "paired_pre": stats.describe([r["pre"] for r in pairs]),
                "paired_post": stats.describe([r["post"] for r in pairs]),
                "gain": stats.describe([r["gain"] for r in pairs]),
                "norm_gain": stats.describe([r["norm_gain"] for r in pairs]),
            }
        )
    return rows


def diagnostics_table(enrollments, course) -> list[dict]:
    """ICPAI diagnostics (D71): per component × cohort (+ everybody) — stages I, II, III (all who took them) and the
    gains II − I, III − I over the students with both stages (p.p.). Cohort = the course enrolment's research group."""
    cohort_of = {e.student_id: e.research_cohort or "" for e in enrollments}
    values: dict[tuple[str, int], dict[str, float]] = defaultdict(dict)
    for r in programme_selectors.diagnostic_results_of_course(course, list(cohort_of)):
        values[(r.component, r.enrollment.student_id)][r.phase] = float(r.percent)
    labels = dict(programme_selectors.COMPONENT_LABELS)
    rows = []
    for component in programme_selectors.COMPONENTS:
        for cohort in (*COHORTS, "all"):
            students = [s for s, c in cohort_of.items() if cohort == "all" or c == cohort]
            per = [values.get((component, s), {}) for s in students]
            rows.append(
                {
                    "component": component,
                    "label": labels[component],
                    "cohort": cohort,
                    "students": len(students),
                    "I": stats.describe([v["I"] for v in per if "I" in v]),
                    "II": stats.describe([v["II"] for v in per if "II" in v]),
                    "III": stats.describe([v["III"] for v in per if "III" in v]),
                    "gain_II": stats.describe([v["II"] - v["I"] for v in per if "I" in v and "II" in v]),
                    "gain_III": stats.describe([v["III"] - v["I"] for v in per if "I" in v and "III" in v]),
                }
            )
    return rows


def page(user, course, group=None, topic=None) -> dict:
    enrollments, topics, stages = scope(user, course, group, topic)
    per = measures(enrollments, topics, stages)
    pre_post = pre_post_scores(enrollments, course)
    return {
        "enrollments": enrollments,
        "topics": topics,
        "stages": stages,
        "cohorts": cohort_table(enrollments, per),
        "stage_rows": stage_overview(enrollments, stages),
        "lab": lab_errors(enrollments, stages),
        "agreement": ai_agreement(enrollments),
        "sample": sample_status(enrollments),
        "per": per,
        "benchmark_quiz": course.benchmark_quiz,
        "pre_post": pre_post,
        "pre_post_rows": pre_post_table(enrollments, pre_post),
        "diagnostic_rows": diagnostics_table(enrollments, course),
        "has_programme": programme_selectors.programme_of_course(course) is not None,
    }


def csv_rows(data) -> list[list]:
    """One row per enrolment — for t-tests / Mann–Whitney in a statistics package."""
    header = [
        "enrollment_id", "username", "full_name", "group", "cohort", "topics", "topic_test_mean", "lab_mean",
        "checkpoint_first_passed", "checkpoint_first_total", "topics_completed", "time_spent_s",
        # STEP-22: appended so that existing scripts keep their column positions
        "pre_percent", "post_percent", "gain", "normalized_gain",
    ]  # fmt: skip
    rows = [header]
    numbers = ",".join(str(t.number) for t in data["topics"])
    for e in data["enrollments"]:
        m = data["per"][e.pk]
        pp = data["pre_post"][e.pk]
        rows.append(
            [
                e.pk, e.student.username, e.student.full_name, e.group.name if e.group else "", e.research_cohort,
                numbers, round(m["test_mean"], 2) if m["test_mean"] is not None else "",
                round(m["lab_mean"], 2) if m["lab_mean"] is not None else "", sum(m["checkpoint_first"]),
                len(m["checkpoint_first"]), m["completed"], m["time_s"],
                *(round(pp[k], 4 if k == "norm_gain" else 2) if pp[k] is not None else ""
                  for k in ("pre", "post", "gain", "norm_gain")),
            ]
        )  # fmt: skip
    return rows
