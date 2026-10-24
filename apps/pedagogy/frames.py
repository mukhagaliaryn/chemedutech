"""The stages and fields of a lesson, by frame (docs/icpai/SPEC.md §2.3; kept in code, not in the database — D4).

TEMPLATE — a stage of the author's lesson templates (section 4, guide @S4-L1…L3). Its fields are the points of the
assembled lesson (guide @S4-ASSEMBLE 1, items 3–8): the template's labelled blocks are sorted into them by
docs/icpai/tools/gen_lessons.py. The stages themselves come from the template.

RESEARCH_8 — «The development sheet of the digital research practice» (section 5, guide @S5 II): eight fixed stages
with their minutes, aim and fields (names verbatim from the guide in the kk translation). ``explain`` and ``task`` say
which fields prefill «The teacher's explanation» and «Giving the task» of the stepwise trial (@S5 IV); ``time`` is
the minutes field.

MICRO_4 — «The sheet of developing the microlesson and trying it out professionally» (section 6, guide @S6 II): four
fixed stages of a 10-minute microlesson (2 + 3 + 3 + 2) and the fields the student fills in.

FREE — the independent lesson of section 8 (guide @S8 II): stages of the student's own choosing, the same fields each.
"""

from dataclasses import dataclass

from django.utils.translation import gettext_lazy as _


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    icon: str
    number: bool = False  # minutes, not text


@dataclass(frozen=True)
class Stage:
    key: str
    title: str
    start: int
    end: int
    aim: str
    fields: tuple
    explain: tuple = ()
    task: tuple = ()
    time: str = "time"

    @property
    def minutes(self) -> int:
        return self.end - self.start


TEMPLATE = (
    Field("teacher_action", _("Teacher's actions"), "user"),
    Field("student_task", _("Tasks the students do"), "list"),
    Field("experiment", _("Virtual lab experiments and research work"), "lab"),
    Field("methods", _("Digital tools and authorial methods"), "sparkle"),
    Field("assessment", _("Assessment criteria and feedback"), "check"),
    Field("result", _("Stage result"), "award"),
)


def _time(label=None):
    return Field("time", label or _("Time to do it, minutes"), "clock", number=True)


TASK = Field("task", _("The task given to the student"), "list")

RESEARCH_8 = (
    Stage(
        "interest", _("Arousing interest"), 0, 4,
        _("To find out the student's prior knowledge and to arouse interest in the research problem."),
        (Field("teacher_explanation", _("The teacher's explanation"), "user"),
         Field("problem_question", _("Problem question"), "help"), TASK, _time(),
         Field("expected", _("Expected result"), "award")),
        explain=("teacher_explanation", "problem_question"), task=("task",),
    ),
    Stage(
        "misconception", _("Finding misconceptions"), 4, 10,
        _("To find out the student's initial understanding of chemical phenomena and to direct them to correct "
          "wrong scientific reasoning."),
        (Field("statement", _("Statement offered for analysis"), "message"), TASK, _time(),
         Field("criterion", _("Assessment criterion"), "check")),
        explain=("statement",), task=("task",),
    ),
    Stage(
        "evidence", _("Gathering evidence"), 10, 19,
        _("To gather scientific data through a virtual experiment or digital modelling."),
        (Field("research_question", _("Research question"), "help"),
         Field("hypothesis", _("Initial hypothesis"), "sparkle"),
         Field("experiment", _("Content of the experiment"), "lab"),
         Field("parameters", _("Parameters to change"), "settings"),
         Field("indicators", _("Indicators to observe"), "chart"), _time(),
         Field("recording", _("How the results are recorded"), "table")),
        explain=("research_question", "hypothesis"), task=("experiment", "parameters", "indicators", "recording"),
    ),
    Stage(
        "three_levels", _("Explaining at three levels"), 19, 27,
        _("To explain a chemical phenomenon by connecting the macroscopic, submicroscopic and symbolic levels."),
        (Field("macro", _("Macroscopic explanation"), "eye"),
         Field("submicro", _("Submicroscopic model"), "grid"),
         Field("equation", _("Chemical equation or formula"), "activity"), TASK, _time()),
        explain=("macro", "submicro", "equation"), task=("task",),
    ),
    Stage(
        "teach_ai", _("Teaching the AI student"), 27, 34,
        _("To improve the future teacher's skills of explaining chemistry knowledge and answering the student's "
          "questions."),
        (Field("concept", _("The chemical concept to explain"), "book"),
         Field("explanation", _("The teacher's authorial explanation"), "user"),
         Field("visual", _("Visual aids used"), "eye"), _time(_("Length of the explanation, minutes"))),
        explain=("concept", "explanation", "visual"),
    ),
    Stage(
        "new_situation", _("Checking in a new situation"), 34, 39,
        _("To find out whether the student applies the knowledge gained in a new chemical situation."),
        (Field("situation", _("New problem situation"), "help"),
         Field("task", _("Task"), "list"),
         Field("expected", _("Expected scientific result"), "award"), _time()),
        explain=("situation",), task=("task",),
    ),
    Stage(
        "peer_assessment", _("Peer assessment"), 39, 43,
        _("To assess the results of the task by criteria and to give reasoned feedback."),
        (Field("criteria", _("Assessment criteria"), "check"),
         Field("descriptors", _("Descriptors"), "list"),
         Field("feedback", _("Way of feedback"), "message"), _time(_("Assessment time, minutes"))),
        explain=("criteria", "descriptors"), task=("feedback",),
    ),
    Stage(
        "reflection", _("Reflection"), 43, 45,
        _("To find out what the student has learnt, the difficulties met and the directions of further development."),
        (Field("questions", _("Reflection questions"), "help"),
         Field("self_assessment", _("Way of self-assessment"), "check-square"),
         Field("summary", _("Summary of the lesson"), "award"), _time()),
        explain=("summary",), task=("questions", "self_assessment"),
    ),
)  # fmt: skip

MICRO_4 = (
    Stage(
        "interest", _("Arousing interest"), 0, 2,
        _("To draw the student's attention to the lesson topic and to find out their prior knowledge."),
        (Field("intro", _("The teacher's opening words"), "user"),
         Field("problem_question", _("Problem question"), "help"),
         Field("visual", _("Visual aids used"), "eye"),
         Field("expected_action", _("The action expected from the student"), "activity")),
    ),
    Stage(
        "explain", _("Explaining new knowledge"), 2, 5,
        _("To convey the chosen chemical concept scientifically correctly and clearly for the student."),
        (Field("concept", _("Explanation of the chemical concept"), "book"),
         Field("equation", _("Chemical formula or equation"), "activity"),
         Field("model", _("Model or diagram used"), "grid"),
         Field("key_points", _("The main statements of the explanation"), "list")),
    ),
    Stage(
        "apply", _("Applying knowledge"), 5, 8,
        _("To check how the student applies the explained knowledge while doing a task."),
        (Field("task", _("Authorial task"), "list"),
         Field("instructions", _("Instructions for doing the task"), "settings"),
         Field("expected_answer", _("Expected correct answer"), "check"),
         Field("criterion", _("Checking criterion"), "check-square")),
    ),
    Stage(
        "check", _("Checking knowledge and summary"), 8, 10,
        _("To find out what the student has learnt and to give short feedback."),
        (Field("question", _("Consolidation question"), "help"),
         Field("assessment", _("Way of assessment"), "check-square"),
         Field("summary", _("Concluding explanation"), "award")),
    ),
)  # fmt: skip

# FREE — the independent lesson of section 8 (guide @S8 II): the student chooses the stages' names, number, content and
# time (45 minutes at most in all); each stage has the same fields (names as in the earlier sheets of the guide).
FREE = (
    Field("aim", _("Aim"), "award"),
    Field("teacher", _("The teacher's explanation"), "user"),
    Field("task", _("The task given to the student"), "list"),
    Field("visual", _("Visual aids used"), "eye"),
    Field("expected", _("Expected result"), "check"),
    Field("criterion", _("Assessment criterion"), "check-square"),
)

FRAMES = {"template": TEMPLATE, "research_8": RESEARCH_8, "micro_4": MICRO_4, "free": FREE}


def stages_of(frame: str) -> tuple[Stage, ...]:
    """The fixed stages of a frame (empty for TEMPLATE: its stages come from the template)."""
    return {"research_8": RESEARCH_8, "micro_4": MICRO_4}.get(frame, ())


def stage_spec(frame: str, key: str) -> Stage | None:
    return next((s for s in stages_of(frame) if s.key == key), None)


def fields_of(frame: str, key: str = "") -> tuple[Field, ...]:
    """The fields of a stage: the same for every stage of TEMPLATE, per stage in RESEARCH_8."""
    if frame == "template":
        return TEMPLATE
    if frame == "free":
        return FREE
    spec = stage_spec(frame, key)
    return spec.fields if spec else ()


def keys_of(frame: str, key: str = "") -> tuple[str, ...]:
    return tuple(f.key for f in fields_of(frame, key))
