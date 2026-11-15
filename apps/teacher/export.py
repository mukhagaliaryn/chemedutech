"""The students table of an ICPAI section page as a file (STEP-47): CSV (UTF-8 with BOM, opens in Excel) or .xlsx.
One row per student of the chosen group: name, login, group, the section's status and percent, then the section's own
columns (the course score, the diagnostics by stage and component, the video watched, the lessons, the portfolio).
Built from the same rows the page shows (teacher.sections), so the file and the page always agree."""

import csv

from django.http import HttpResponse
from django.utils.http import content_disposition_header
from django.utils.translation import gettext as _

from apps.core import xlsx
from apps.programme.models import Level, Section
from apps.programme.selectors import COMPONENT_LABELS

PHASES = ("I", "II", "III")
LEVELS = dict(Level.choices)


def response(fmt: str, table: list[list], name: str) -> HttpResponse:
    if fmt == "xlsx":
        out = HttpResponse(xlsx.build(table, sheet_name=name[:31]), content_type=xlsx.CONTENT_TYPE)
    else:
        out = HttpResponse(content_type="text/csv; charset=utf-8")
        out.write("﻿")
        csv.writer(out).writerows(table)
    out["Content-Disposition"] = content_disposition_header(True, f"{name}.{fmt}")  # a Cyrillic group name too
    return out


def _num(value):
    return "" if value is None else value


def _status(r) -> str:
    if not r["joined"]:
        return _("Not in the programme")
    p = r["progress"]
    return p.get_status_display() if p else _("Locked")


def section_table(section, rows, extra) -> list[list]:
    head, cells = _columns(section, extra)
    table = [[_("Student"), _("Login"), _("Group"), _("Status"), _("Progress, %"), *head]]
    for r in rows:
        student, p = r["student"], r["progress"]
        profile = getattr(student, "student_profile", None)
        table.append([
            student.full_name or student.username, student.username, str(profile.group) if profile and profile.group else "",
            _status(r), _num(p.percent if p else None), *cells(r),
        ])  # fmt: skip
    return table


def _columns(section, extra):
    """(header, row → cells) of the section's own columns."""
    kind = section.kind
    if kind == Section.Kind.COURSE:

        def course(r):
            e, res = r.get("enrollment"), r.get("result")
            return [e.get_status_display() if e else "", _num(res.current_percent if res else None),
                    res.letter if res else ""]  # fmt: skip

        return [_("Course"), _("Course score"), _("Letter grade")], course
    if kind == Section.Kind.DIAGNOSTIC:
        head = []
        for p in PHASES:
            head += [f"{p}: {_('points')}", f"{p}: {_('maximum')}", f"{p}: %", f"{p}: {_('level')}"]
        head += [f"{p} · {label}, %" for p in PHASES for _c, label in COMPONENT_LABELS]

        def diagnostic(r):
            out = []
            for d in r["phases"]:
                s = d["summary"]
                out += (
                    [_num(s["earned"]), _num(s["maximum"]), _num(s["percent"]), str(LEVELS.get(s["level"], ""))]
                    if s
                    else ["", "", "", ""]
                )
            out += [_num(r["components"].get((p, c))) for p in PHASES for c, _l in COMPONENT_LABELS]
            return out

        return head, diagnostic
    if kind == Section.Kind.VIDEO:
        return [_("Watched, %")], lambda r: [_num(r.get("watched"))]
    if kind == Section.Kind.DESIGNER:
        head = [f"№{t['template'].number} {t['template'].name}" for t in extra["templates"]]
        return head, lambda r: [x["lesson"].get_status_display() if x["lesson"] else "" for x in r["lessons"]]
    if kind == Section.Kind.PORTFOLIO:

        def portfolio(r):
            x = r.get("portfolio")
            return [
                x.get_status_display() if x else "",
                x.submitted_at.strftime("%Y-%m-%d") if x and x.submitted_at else "",
            ]

        return [_("Portfolio"), _("Submitted")], portfolio

    def lessons(r):
        w = r.get("work")
        if not w:
            return ["", "", "", ""]
        latest = w["latest"]
        return [w["lessons"], w["final"], _num(w["best"]), latest.get_status_display() if latest else ""]

    return [_("Works"), _("Finished"), _("Best grade (of 10)"), _("Latest work")], lessons
