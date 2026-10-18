"""Experiment 2 — halide ions with silver nitrate.

The author's instruction lists this study in the journal and the rubric, but its commands were missing
(sections 5–6 of data/1.2); they are written here from the lecture (§5) and the test (question 3).
"""
from django.utils.translation import gettext_lazy as _

from apps.labs.engine import ExperimentSpec, Item, JournalField, Option, Question, Step

from .common import AGBR, AGCL, AGI, COLOURLESS, KBR, KCL, KI, RACK

PARAMS = {
    "rack_item": "rack",
    "tubes": [{"label": "A"}, {"label": "B"}, {"label": "C"}],
    "ops": {
        "add_halides": [
            {"tube": 0, "pour": COLOURLESS, "level": 0.3, "text": "KCl"},
            {"tube": 1, "pour": COLOURLESS, "level": 0.3, "text": "KBr", "at": 0.3},
            {"tube": 2, "pour": COLOURLESS, "level": 0.3, "text": "KI", "at": 0.6},
        ],
        "acidify": [{"tube": i, "pour": COLOURLESS, "level": 0.34, "at": i * 0.3} for i in range(3)],
        "add_agno3": [
            {"tube": 0, "pour": COLOURLESS, "level": 0.42},
            {"tube": 0, "cloud": 0.85, "cloud_color": AGCL, "at": 0.8},
            {"tube": 0, "precipitate": AGCL, "at": 1.6, "dur": 2.5},
            {"tube": 1, "pour": COLOURLESS, "level": 0.42, "at": 0.4},
            {"tube": 1, "cloud": 0.85, "cloud_color": AGBR, "at": 1.2},
            {"tube": 1, "precipitate": AGBR, "at": 2.0, "dur": 2.5},
            {"tube": 2, "pour": COLOURLESS, "level": 0.42, "at": 0.8},
            {"tube": 2, "cloud": 0.85, "cloud_color": AGI, "at": 1.6},
            {"tube": 2, "precipitate": AGI, "at": 2.4, "dur": 2.5},
        ],
        "compare": [{"tube": i, "cloud": 0.35, "dur": 2} for i in range(3)] + [{"reveal": True}],
    },
}

EXPERIMENT = ExperimentSpec(
    key="silver_halides",
    number=2,
    title=_("Detecting halide ions with silver nitrate"),
    goal=_("Tell chloride, bromide and iodide ions apart by the colour of their silver precipitates."),
    scene="tubes",
    equation="Ag<sup>+</sup> + X<sup>−</sup> → AgX↓ (X = Cl, Br, I)",
    explanation=_(
        "Silver ions give poorly soluble precipitates with halide ions: AgCl is white, AgBr is pale cream, AgI is "
        "yellow. The solution is acidified with nitric acid so that other anions (carbonate, hydroxide) do not "
        "precipitate. Fluoride gives no precipitate: AgF is soluble."
    ),
    extra_equations=(
        (_("Tube A"), "Ag<sup>+</sup> + Cl<sup>−</sup> → AgCl↓"),
        (_("Tube B"), "Ag<sup>+</sup> + Br<sup>−</sup> → AgBr↓"),
        (_("Tube C"), "Ag<sup>+</sup> + I<sup>−</sup> → AgI↓"),
    ),
    items=(
        RACK,
        KCL,
        KBR,
        KI,
        Item("hno3", _("Dilute nitric acid"), "reagent", "bottle", formula="HNO₃"),
        Item("agno3", _("Silver nitrate solution"), "reagent", "bottle_dark", formula="AgNO₃"),
        Item(
            "naf",
            _("Sodium fluoride solution"),
            "reagent",
            "bottle",
            formula="NaF",
            required=False,
            note=_("Silver fluoride is soluble: a fluoride gives no precipitate with AgNO₃, so it is not used here."),
        ),
    ),
    steps=(
        Step("take_rack", _("Take the rack and three test tubes"), _("Test tubes A, B and C are on the bench."),
             "place", items=("rack",)),
        Step(
            "add_halides",
            _("Pour KCl into A, KBr into B and KI into C"),
            _("Three colourless solutions of halides are in the tubes."),
            "place",
            items=("kcl", "kbr", "ki"),
            early_warning=_("Put the rack with the test tubes on the bench first."),
            hint=_("You need three solutions: KCl, KBr and KI."),
        ),
        Step(
            "acidify",
            _("Acidify the solutions with dilute HNO₃"),
            _("A few drops of dilute nitric acid are added to each tube."),
            "place",
            items=("hno3",),
            early_warning=_("Pour the halide solutions first."),
        ),
        Step(
            "predict",
            _("Predict the colours of the precipitates with AgNO₃"),
            _("The prediction is recorded."),
            "choice",
            options=(
                Option("right", _("A — white, B — pale cream, C — yellow"), correct=True,
                       feedback=_("Let us check it.")),
                Option("white", _("All three are white"),
                       feedback=_("The precipitates differ: this is what makes the test qualitative.")),
                Option("reverse", _("A — yellow, B — pale cream, C — white"),
                       feedback=_("The colour deepens from chloride to iodide, not the other way round.")),
            ),
            early_warning=_("Acidify the solutions first."),
        ),
        Step(
            "add_agno3",
            _("Add AgNO₃ solution to each tube"),
            _("Precipitates form: white in A, pale cream in B, yellow in C."),
            "place",
            items=("agno3",),
            early_warning=_("Acidify the solutions and make a prediction first: other anions could also precipitate."),
        ),
        Step(
            "compare",
            _("Compare the precipitates"),
            _("The precipitates settle; their colours are compared with the table."),
            "process",
            early_warning=_("Add silver nitrate first."),
        ),
        Step("journal", _("Save the lab journal"), _("Observations and equations are recorded."), "journal"),
        Step("finish", _("Finish the experiment"), _("The results are saved and the analysis task opens."), "finish",
             early_warning=_("Fill in the lab journal first.")),
    ),
    journal=(
        JournalField(
            "colour_c",
            _("Which precipitate is yellow?"),
            "choice",
            options=(
                Option("agi", "AgI", correct=True),
                Option("agbr", "AgBr"),
                Option("agcl", "AgCl"),
            ),
        ),
        JournalField("eq_cl", _("Tube A: the short ionic equation"), "equation", answer="Ag+ + Cl- -> AgCl"),
        JournalField("eq_br", _("Tube B: the short ionic equation"), "equation", answer="Ag+ + Br- -> AgBr"),
        JournalField("eq_i", _("Tube C: the short ionic equation"), "equation", answer="Ag+ + I- -> AgI"),
        JournalField("obs", _("How can the three ions be told apart?")),
    ),
    questions=(
        Question(
            "why_hno3",
            _("Why are the solutions acidified with nitric acid before adding AgNO₃?"),
            (
                Option("other", _("So that other anions (CO₃²⁻, OH⁻) do not give precipitates with silver"), correct=True),
                Option("faster", _("To speed up the reaction")),
                Option("colour", _("To colour the precipitates")),
            ),
        ),
        Question(
            "fluoride",
            _("Why does a fluoride give no precipitate with AgNO₃?"),
            (
                Option("soluble", _("Silver fluoride is soluble in water"), correct=True),
                Option("no_ion", _("Fluoride does not form ions in solution")),
                Option("gas", _("Fluorine is released as a gas")),
            ),
        ),
        Question(
            "ammonia",
            _("Which precipitate dissolves in dilute ammonia solution?"),
            (
                Option("agcl", "AgCl", correct=True),
                Option("agbr", "AgBr"),
                Option("agi", "AgI"),
            ),
        ),
        Question("teach", _("What would you ask school students to compare in this experiment, and why?")),
    ),
    params=PARAMS,
)  # fmt: skip
