"""The fields of a lesson stage, by frame (docs/icpai/SPEC.md §2.3; kept in code, not in the database — D4).

TEMPLATE — a stage of the author's lesson templates (section 4, guide @S4-L1…L3). Its fields are the points of the
assembled lesson (guide @S4-ASSEMBLE 1, items 3–8): the template's labelled blocks are sorted into them by
docs/icpai/tools/gen_lessons.py. The other frames (CONSTRUCTOR_8, RESEARCH_SHEET_8, MICRO_4, FREE) come with their
sections.
"""

from dataclasses import dataclass

from django.utils.translation import gettext_lazy as _


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    icon: str


TEMPLATE = (
    Field("teacher_action", _("Teacher's actions"), "user"),
    Field("student_task", _("Tasks the students do"), "list"),
    Field("experiment", _("Virtual lab experiments and research work"), "lab"),
    Field("methods", _("Digital tools and authorial methods"), "sparkle"),
    Field("assessment", _("Assessment criteria and feedback"), "check"),
    Field("result", _("Stage result"), "award"),
)

FRAMES = {"template": TEMPLATE}


def fields_of(frame: str) -> tuple[Field, ...]:
    return FRAMES[frame]


def keys_of(frame: str) -> tuple[str, ...]:
    return tuple(f.key for f in FRAMES[frame])
