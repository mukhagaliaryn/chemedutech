"""Experiment 4 — rate of H₂O₂ decomposition with and without MnO₂."""
from django.utils.translation import gettext_lazy as _

from apps.labs.engine import ExperimentSpec, Item, JournalField, Option, Question, Step

from .common import H2O2, MNO2

# 5 mL of 3% H₂O₂ → ≈ 49 mL O₂ in both tubes (catalyst changes rate, not yield).
PARAMS = {"h2o2_ml": 5, "v_max_ml": 49.4, "k_a_per_s": 0.0004, "k_b_per_s": 0.025, "seconds": 300, "time_scale": 10}

EXPERIMENT = ExperimentSpec(
    key="rate",
    number=4,
    title=_("Rate of hydrogen peroxide decomposition"),
    goal=_("Compare how fast oxygen is released in two test tubes: without a catalyst (A) and with MnO₂ (B)."),
    scene="rate",
    equation='2H<sub>2</sub>O<sub>2</sub> <span class="eq-cat"><span>MnO<sub>2</sub></span>→</span> 2H<sub>2</sub>O + O<sub>2</sub>↑',
    explanation=_(
        "A catalyst changes the rate of the reaction, but it does not increase the theoretical total amount "
        "of oxygen formed when the same initial amount of hydrogen peroxide decomposes completely."
    ),
    items=(
        Item("tube_a", _("Test tube A"), "glass", "test_tube"),
        Item("tube_b", _("Test tube B"), "glass", "test_tube"),
        Item("syringes", _("Gas syringes"), "device", "syringe"),
        H2O2,
        MNO2,
        Item(
            "spirit_lamp",
            _("Spirit lamp"),
            "device",
            "lamp",
            required=False,
            note=_("Heating would also speed up the reaction and mix two factors. Change only one variable: the catalyst."),
        ),
    ),
    steps=(
        Step(
            "place_tubes",
            _("Select two test tubes"),
            _("Tubes A and B are placed and connected to gas syringes."),
            "place",
            items=("tube_a", "tube_b", "syringes"),
            hint=_("You need tube A, tube B and the gas syringes."),
        ),
        Step(
            "add_h2o2",
            _("Add H₂O₂"),
            _("The same initial amount (5 mL) is poured into both tubes."),
            "place",
            items=("h2o2",),
            early_warning=_("Place both test tubes first."),
        ),
        Step(
            "add_mno2",
            _("Add MnO₂"),
            _("The catalyst is added to tube B only."),
            "place",
            items=("mno2",),
            early_warning=_("Pour H₂O₂ into both tubes first."),
        ),
        Step(
            "timer",
            _("Start the timer"),
            _("The comparison of the two reactions begins."),
            "process",
            early_warning=_("Prepare both tubes first."),
        ),
        Step(
            "graph",
            _("Open the graph"),
            _("The volume of O₂ released is plotted against time."),
            "action",
            early_warning=_("Start the timer first."),
        ),
        Step(
            "conclusion",
            _("Write a conclusion"),
            _("Explain the effect of the catalyst on the reaction rate."),
            "journal",
        ),
        Step(
            "finish",
            _("Finish the experiment"),
            _("The results are saved and the analysis task opens."),
            "finish",
            early_warning=_("Fill in the lab journal first."),
        ),
    ),
    journal=(
        JournalField("v_a_2min", _("V(O₂) in tube A after 2 min"), "number", unit=_("mL")),
        JournalField("v_b_2min", _("V(O₂) in tube B after 2 min"), "number", unit=_("mL")),
        JournalField(
            "effect",
            _("Conclusion"),
            "choice",
            options=(
                Option("rate_only", _("The catalyst speeds up the reaction but does not change the total volume of O₂"), correct=True),
                Option("more_o2", _("The catalyst increases the amount of O₂")),
                Option("slower", _("The catalyst slows the reaction down")),
            ),
        ),
        JournalField("explain", _("Explain the effect of the catalyst in your own words")),
    ),
    questions=(
        Question(
            "total",
            _("How much oxygen will be formed in each tube when H₂O₂ decomposes completely (5 mL, 3%)?"),
            (
                Option("same", _("About 49 mL in both tubes"), correct=True),
                Option("b_more", _("More in tube B")),
                Option("a_more", _("More in tube A")),
            ),
        ),
        Question(
            "variable",
            _("Which variable was changed in this experiment?"),
            (
                Option("catalyst", _("Only the presence of the catalyst"), correct=True),
                Option("temp", _("The temperature")),
                Option("conc", _("The concentration of H₂O₂")),
            ),
        ),
        Question("activation", _("Using the idea of activation energy, explain why MnO₂ speeds up the decomposition.")),
    ),
    params=PARAMS,
)
