"""Experiment 1 — displacement of halogens: Cl₂ + KI, Cl₂ + KBr, Br₂ + KCl (the author's instruction, data/1.2)."""
from django.utils.translation import gettext_lazy as _

from apps.labs.engine import ExperimentSpec, Item, JournalField, Option, Question, Step

from .common import BR2_WATER, BROMINE, BROMINE_WATER, CHLORINE_WATER, CL2_WATER, COLOURLESS, IODINE, KBR, KCL, KI, RACK

PARAMS = {
    "rack_item": "rack",
    "tubes": [{"label": "A"}, {"label": "B"}, {"label": "C"}],
    "ops": {
        "add_ki": [{"tube": 0, "pour": COLOURLESS, "level": 0.3, "text": "KI"}],
        "add_cl2_a": [{"tube": 0, "pour": CHLORINE_WATER, "level": 0.42, "dur": 0.8},
                      {"tube": 0, "color": IODINE, "at": 1.2, "dur": 2.5}],
        "add_kbr": [{"tube": 1, "pour": COLOURLESS, "level": 0.3, "text": "KBr"}],
        "add_cl2_b": [{"tube": 1, "pour": CHLORINE_WATER, "level": 0.42, "dur": 0.8},
                      {"tube": 1, "color": BROMINE, "at": 1.2, "dur": 2.5}],
        "add_kcl": [{"tube": 2, "pour": COLOURLESS, "level": 0.3, "text": "KCl"}],
        "add_br2_c": [{"tube": 2, "pour": BROMINE_WATER, "level": 0.42, "dur": 2}],
        "compare": [{"reveal": True}],
    },
}  # fmt: skip

EXPERIMENT = ExperimentSpec(
    key="displacement",
    number=1,
    title=_("Displacement reactions of halogens"),
    goal=_(
        "Find out which halogen displaces which from a solution of its salt and build the series of the "
        "oxidising ability of chlorine, bromine and iodine."
    ),
    scene="tubes",
    equation="Cl<sub>2</sub> + 2KI → 2KCl + I<sub>2</sub>",
    explanation=_(
        "A free halogen oxidises the anions of a halogen below it in the group: chlorine displaces bromine and "
        "iodine, bromine cannot oxidise chloride ions. Oxidising ability: Cl₂ > Br₂ > I₂ (for the whole group "
        "F₂ > Cl₂ > Br₂ > I₂)."
    ),
    extra_equations=(
        (_("Tube A, ionic"), "Cl<sub>2</sub> + 2I<sup>−</sup> → 2Cl<sup>−</sup> + I<sub>2</sub>"),
        (_("Tube B, ionic"), "Cl<sub>2</sub> + 2Br<sup>−</sup> → 2Cl<sup>−</sup> + Br<sub>2</sub>"),
        (_("Tube C"), _("Br₂ + KCl → no reaction")),
    ),
    items=(
        RACK,
        KI,
        KBR,
        KCL,
        CL2_WATER,
        BR2_WATER,
        Item(
            "agno3",
            _("Silver nitrate solution"),
            "reagent",
            "bottle_dark",
            formula="AgNO₃",
            required=False,
            note=_("Silver nitrate detects halide ions; it is used in the next experiment, not for displacement."),
        ),
    ),
    steps=(
        Step("take_rack", _("Take the rack and three test tubes"), _("Test tubes A, B and C are on the bench."),
             "place", items=("rack",)),
        Step("add_ki", _("A: pour the KI solution"), _("Tube A holds a colourless KI solution."), "place",
             items=("ki",), early_warning=_("Put the rack with the test tubes on the bench first.")),
        Step(
            "predict",
            _("Predict: what happens when chlorine water is added to A?"),
            _("The prediction is recorded."),
            "choice",
            options=(
                Option("brown", _("The solution turns brown: iodine is formed"), correct=True,
                       feedback=_("A reasoned prediction. Let us check it.")),
                Option("nothing", _("Nothing changes"),
                       feedback=_("Compare the positions of chlorine and iodine in the group and their oxidising ability.")),
                Option("white", _("A white precipitate forms"),
                       feedback=_("A precipitate with halide ions needs silver ions, and there are none here.")),
            ),
            early_warning=_("Pour the KI solution into tube A first."),
        ),
        Step(
            "add_cl2_a",
            _("A: add chlorine water"),
            _("The solution turns brown: iodine is formed."),
            "place",
            items=("cl2",),
            early_warning=_(
                "Chlorine water is toxic: it is added only to a prepared tube and after the prediction "
                "(here everything is virtual)."
            ),
            safety=True,
        ),
        Step("add_kbr", _("B: pour the KBr solution"), _("Tube B holds a colourless KBr solution."), "place",
             items=("kbr",), early_warning=_("Finish the experiment in tube A first.")),
        Step("add_cl2_b", _("B: add chlorine water"), _("The solution turns yellow-orange: bromine is formed."),
             "process", early_warning=_("Pour the KBr solution into tube B first.")),
        Step("add_kcl", _("C: pour the KCl solution"), _("Tube C holds a colourless KCl solution."), "place",
             items=("kcl",), early_warning=_("Finish the experiment in tube B first.")),
        Step(
            "add_br2_c",
            _("C: add bromine water"),
            _("Only the colour of bromine water itself remains: no new substance is formed — no reaction."),
            "place",
            items=("br2",),
            early_warning=_("Pour the KCl solution into tube C first."),
        ),
        Step(
            "compare",
            _("Compare the three results"),
            _("The series of oxidising ability is built: Cl₂ > Br₂ > I₂."),
            "choice",
            options=(
                Option("cl_br_i", "Cl₂ > Br₂ > I₂", correct=True, feedback=_("Right: each halogen displaces the ones below it.")),
                Option("i_br_cl", "I₂ > Br₂ > Cl₂", feedback=_("Look at tube C: bromine did not displace chlorine.")),
                Option("br_cl_i", "Br₂ > Cl₂ > I₂", feedback=_("Chlorine displaced bromine in tube B: chlorine is stronger.")),
            ),
            early_warning=_("Carry out the experiments in all three tubes first."),
        ),
        Step("journal", _("Save the lab journal"), _("Predictions, observations and equations are recorded."), "journal"),
        Step("finish", _("Finish the experiment"), _("The results are saved and the analysis task opens."), "finish",
             early_warning=_("Fill in the lab journal first.")),
    ),
    journal=(
        JournalField("obs_a", _("What did you observe in tube A?")),
        JournalField("eq_a", _("Tube A: the short ionic equation"), "equation", answer="Cl2 + 2I- -> 2Cl- + I2"),
        JournalField("eq_b", _("Tube B: the short ionic equation"), "equation", answer="Cl2 + 2Br- -> 2Cl- + Br2"),
        JournalField(
            "obs_c",
            _("What happened in tube C?"),
            "choice",
            options=(
                Option("none", _("No reaction: bromine cannot oxidise chloride ions"), correct=True),
                Option("cl2", _("Chlorine was released")),
                Option("ppt", _("A precipitate formed")),
            ),
        ),
        JournalField("conclusion", _("Conclusion: how does the oxidising ability of halogens change?")),
    ),
    questions=(
        Question(
            "why_cl2",
            _("Why can Cl₂ oxidise iodide ions, while Br₂ cannot oxidise chloride ions?"),
            (
                Option("potential", _("The Cl₂/Cl⁻ pair is a stronger oxidising agent than Br₂/Br⁻ and I₂/I⁻"), correct=True),
                Option("liquid", _("Because bromine is a liquid")),
                Option("absent", _("Because there are no chloride ions in the solution")),
            ),
        ),
        Question(
            "trend",
            _("Why does the oxidising ability of halogens decrease down the group?"),
            (
                Option("radius", _("The atomic radius and the screening grow, an electron is attracted more weakly"), correct=True),
                Option("mass", _("The molecules become heavier")),
                Option("colour", _("The colour of the substances becomes darker")),
            ),
        ),
        Question(
            "reducer",
            _("Which particle is the reducing agent in Cl₂ + 2I⁻ → 2Cl⁻ + I₂?"),
            (
                Option("i", _("The iodide ion I⁻"), correct=True),
                Option("cl2", _("The chlorine molecule Cl₂")),
                Option("cl", _("The chloride ion Cl⁻")),
            ),
        ),
        Question(
            "teach",
            _("How would you show these reactions to school students without real dangerous reagents?"),
        ),
    ),
    params=PARAMS,
)  # fmt: skip
