"""Experiment 1 — obtaining and collecting hydrogen (Zn + HCl)."""
from django.utils.translation import gettext_lazy as _

from apps.labs.engine import ExperimentSpec, Item, JournalField, Option, Question, Step

from .common import SPIRIT_LAMP_NO_HEAT

# 0.65 g Zn = 0.01 mol → 0.01 mol H₂ = 224 mL (normal conditions), acid in excess.
PARAMS = {"zn_mass_g": 0.65, "v_max_ml": 224, "k_per_s": 0.13, "cylinder_ml": 250}

EXPERIMENT = ExperimentSpec(
    key="hydrogen",
    number=1,
    title=_("Obtaining and collecting hydrogen"),
    goal=_("Obtain hydrogen from zinc and hydrochloric acid and collect it by displacement of water."),
    scene="hydrogen",
    equation="Zn + 2HCl → ZnCl<sub>2</sub> + H<sub>2</sub>↑",
    explanation=_("Zinc gives up electrons and is oxidised, while hydrogen ions accept electrons and are reduced."),
    extra_equations=(
        (_("Oxidation"), "Zn<sup>0</sup> − 2e<sup>−</sup> → Zn<sup>2+</sup>"),
        (_("Reduction"), "2H<sup>+</sup> + 2e<sup>−</sup> → H<sub>2</sub><sup>0</sup>"),
    ),
    items=(
        Item("flask", _("Flask"), "glass", "flask"),
        Item("stopper_tube", _("Stopper with gas delivery tube"), "glass", "stopper"),
        Item("trough", _("Trough with water"), "glass", "trough"),
        Item("cylinder", _("Gas collecting cylinder"), "glass", "cylinder"),
        Item("zn", _("Zinc granules"), "reagent", "granules", formula="Zn"),
        Item("hcl", _("Hydrochloric acid, 10%"), "reagent", "bottle", formula="HCl"),
        Item(
            "cu",
            _("Copper turnings"),
            "reagent",
            "granules_cu",
            formula="Cu",
            required=False,
            note=_("Copper does not displace hydrogen from acids: it stands after hydrogen in the activity series."),
        ),
        SPIRIT_LAMP_NO_HEAT,
    ),
    steps=(
        Step("select_flask", _("Select the flask"), _("The flask appears on the bench."), "place", items=("flask",)),
        Step(
            "add_zn",
            _("Add zinc"),
            _("Zinc granules are placed in the flask."),
            "place",
            items=("zn",),
            early_warning=_("Put the flask on the bench first."),
        ),
        Step(
            "assemble",
            _("Assemble the gas delivery system"),
            _("The stopper, the tube and the water-filled gas collector are attached."),
            "place",
            items=("stopper_tube", "trough", "cylinder"),
            early_warning=_("Put zinc into the flask before closing it with the stopper."),
            hint=_("You need three items: the stopper with the tube, the trough with water and the cylinder."),
        ),
        Step(
            "add_acid",
            _("Add the acid"),
            _("The reaction starts and bubbles appear."),
            "action",
            items=("hcl",),
            early_warning=_(
                "Assemble the gas delivery system first: otherwise hydrogen escapes into the room, "
                "and a mixture of hydrogen with air is explosive."
            ),
            safety=True,
        ),
        Step(
            "collect",
            _("Collect the gas"),
            _("Hydrogen displaces water from the cylinder."),
            "process",
            early_warning=_("There is no gas to collect yet: start the reaction first."),
        ),
        Step(
            "observe",
            _("Observe the result"),
            _("The gas volume and the reaction equation are shown."),
            "action",
            early_warning=_("Wait until the gas has been collected."),
        ),
        Step("journal", _("Write to the lab journal"), _("Record your observations."), "journal"),
        Step(
            "finish",
            _("Finish the experiment"),
            _("The results are saved and the analysis task opens."),
            "finish",
            early_warning=_("Fill in the lab journal first."),
        ),
    ),
    journal=(
        JournalField("obs_flask", _("What did you observe in the flask after adding the acid?")),
        JournalField("volume", _("Volume of hydrogen collected"), "number", unit=_("mL")),
        JournalField("obs_pop", _("What happened when the gas was tested with a flame?")),
        JournalField(
            "why_water",
            _("Why can hydrogen be collected by displacing water?"),
            "choice",
            options=(
                Option("insoluble", _("It is practically insoluble in water"), correct=True),
                Option("heavy", _("It is heavier than water")),
                Option("reacts", _("It reacts with water")),
            ),
        ),
    ),
    questions=(
        Question(
            "oxidant",
            _("Which particle is the oxidising agent in the reaction Zn + 2HCl → ZnCl₂ + H₂?"),
            (
                Option("h_ion", _("H⁺ ions of the acid"), correct=True),
                Option("zn", _("Zinc atoms")),
                Option("cl", _("Cl⁻ ions")),
                Option("h2", _("H₂ molecules")),
            ),
        ),
        Question(
            "air_collect",
            _("Hydrogen can also be collected by displacing air. How should the vessel be held?"),
            (
                Option("down", _("Upside down: hydrogen is lighter than air"), correct=True),
                Option("up", _("Mouth up: hydrogen is heavier than air")),
                Option("any", _("It does not matter")),
            ),
        ),
        Question(
            "no_h2",
            _("Which metal does not displace hydrogen from hydrochloric acid?"),
            (
                Option("cu", _("Copper"), correct=True),
                Option("zn", _("Zinc")),
                Option("fe", _("Iron")),
                Option("mg", _("Magnesium")),
            ),
        ),
        Question(
            "teach_purity",
            _("How would you explain to school students why hydrogen must be tested for purity before it is ignited?"),
        ),
    ),
    params=PARAMS,
)
