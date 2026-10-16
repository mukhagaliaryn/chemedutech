"""Experiment 2 — obtaining oxygen from H₂O₂ with and without MnO₂.

Order note: the gas collector is attached *before* the reaction starts
(otherwise the gas is lost), and the reaction is run first without and then
with the catalyst so the student can compare the rates (required by the ТЗ).
"""
from django.utils.translation import gettext_lazy as _

from apps.labs.engine import ExperimentSpec, Item, JournalField, Option, Question, Step

from .common import H2O2, MNO2, SPIRIT_LAMP_NO_HEAT

# 10 mL of 3% H₂O₂ = 0.00882 mol → 0.00441 mol O₂ ≈ 99 mL (normal conditions)
PARAMS = {
    "h2o2_ml": 10,
    "v_max_ml": 99,
    "k_nocat_per_s": 0.0006,
    "k_cat_per_s": 0.09,
    "nocat_seconds": 60,
    "cat_seconds": 60,
    "time_scale": 4,
    "collector_ml": 120,
}

EXPERIMENT = ExperimentSpec(
    key="oxygen",
    number=2,
    title=_("Obtaining oxygen"),
    goal=_("Obtain oxygen by decomposing hydrogen peroxide and compare the rate with and without a catalyst."),
    scene="oxygen",
    equation='2H<sub>2</sub>O<sub>2</sub> <span class="eq-cat"><span>MnO<sub>2</sub></span>→</span> 2H<sub>2</sub>O + O<sub>2</sub>↑',
    explanation=_(
        "Manganese(IV) oxide is a catalyst: it speeds up the decomposition of hydrogen peroxide "
        "and remains unchanged at the end of the reaction."
    ),
    items=(
        Item("test_tube", _("Test tube"), "glass", "test_tube"),
        H2O2,
        MNO2,
        Item("gas_collector", _("Gas collector with water"), "glass", "collector"),
        Item(
            "kmno4",
            _("Potassium permanganate"),
            "reagent",
            "jar_violet",
            formula="KMnO₄",
            required=False,
            note=_("KMnO₄ also gives oxygen, but only when heated. This experiment studies the catalytic decomposition of H₂O₂."),
        ),
        SPIRIT_LAMP_NO_HEAT,
    ),
    steps=(
        Step("take_tube", _("Take a test tube"), _("A test tube is placed on the bench."), "place", items=("test_tube",)),
        Step(
            "add_h2o2",
            _("Select the H₂O₂ solution"),
            _("10 mL of the solution is poured into the test tube."),
            "place",
            items=("h2o2",),
            early_warning=_("Put the test tube on the bench first."),
        ),
        Step(
            "attach_collector",
            _("Attach the gas collector"),
            _("The delivery tube leads to the collector filled with water."),
            "place",
            items=("gas_collector",),
            early_warning=_("Pour the solution into the test tube first."),
        ),
        Step(
            "run_nocat",
            _("Start the reaction without a catalyst"),
            _("Only single bubbles appear: without a catalyst the decomposition is very slow."),
            "process",
            early_warning=_("Attach the gas collector first, otherwise the gas will be lost."),
        ),
        Step(
            "add_mno2",
            _("Add the MnO₂ catalyst"),
            _("Black catalyst powder is added to the solution."),
            "place",
            items=("mno2",),
            early_warning=_("First observe the reaction without a catalyst, otherwise you will have nothing to compare with."),
        ),
        Step(
            "run_cat",
            _("Start the reaction"),
            _("Gas bubbles are released intensively and oxygen collects."),
            "process",
            early_warning=_("Add the catalyst first."),
        ),
        Step(
            "observe",
            _("Observe"),
            _("A glowing splint flares up in oxygen. The rates of the two runs are compared."),
            "action",
            early_warning=_("Wait until the oxygen has been collected."),
        ),
        Step("journal", _("Record the result"), _("Fill in the observation journal."), "journal"),
        Step(
            "finish",
            _("Finish the experiment"),
            _("The results are saved and the analysis task opens."),
            "finish",
            early_warning=_("Fill in the lab journal first."),
        ),
    ),
    journal=(
        JournalField("rate_nocat", _("Average rate without a catalyst"), "number", unit=_("mL/min")),
        JournalField("rate_cat", _("Average rate with MnO₂"), "number", unit=_("mL/min")),
        JournalField("obs_splint", _("What happened to the glowing splint?")),
        JournalField(
            "role_mno2",
            _("What is the role of MnO₂?"),
            "choice",
            options=(
                Option("catalyst", _("A catalyst: speeds up the reaction and is not consumed"), correct=True),
                Option("reactant", _("A reactant: it is consumed")),
                Option("product", _("A product of the reaction")),
            ),
        ),
    ),
    questions=(
        Question(
            "consumed",
            _("Is MnO₂ consumed in the reaction?"),
            (
                Option("no", _("No, its mass stays the same at the end"), correct=True),
                Option("yes", _("Yes, it is completely consumed")),
                Option("part", _("Partly")),
            ),
        ),
        Question(
            "more_cat",
            _("What happens to the total volume of O₂ if more MnO₂ is added to the same amount of H₂O₂?"),
            (
                Option("same", _("It stays the same; only the rate changes"), correct=True),
                Option("more", _("It increases")),
                Option("less", _("It decreases")),
            ),
        ),
        Question(
            "detect",
            _("How is oxygen detected?"),
            (
                Option("splint", _("A glowing splint flares up"), correct=True),
                Option("pop", _("A burning splint goes out with a pop")),
                Option("limewater", _("Limewater turns cloudy")),
            ),
        ),
        Question("teach_catalyst", _("Suggest a way to show students that the catalyst is not consumed in the reaction.")),
    ),
    params=PARAMS,
)
