"""Experiment 3 — electrolysis of water (alkaline electrolyte)."""
from django.utils.translation import gettext_lazy as _

from apps.labs.engine import ExperimentSpec, Item, JournalField, Option, Question, Step

# I = 0.5 A → H₂: I/(2F)·22.4 L ≈ 0.058 mL/s, O₂ half of that.
PARAMS = {"current_a": 0.5, "faraday": 96485, "vm_ml": 22400, "minutes": 10, "time_scale": 30, "tube_ml": 50}

GAS_OPTIONS = (
    Option("h2", "H₂"),
    Option("o2", "O₂"),
    Option("cl2", "Cl₂"),
)

EXPERIMENT = ExperimentSpec(
    key="electrolysis",
    number=3,
    title=_("Electrolysis of water"),
    goal=_("Decompose water by direct current and determine the volume ratio of hydrogen and oxygen."),
    scene="electrolysis",
    equation="2H<sub>2</sub>O → 2H<sub>2</sub>↑ + O<sub>2</sub>↑",
    explanation=_(
        "Water is reduced at the cathode and hydroxide ions are oxidised at the anode. "
        "Twice as many hydrogen molecules are formed as oxygen molecules, so V(H₂) : V(O₂) = 2 : 1."
    ),
    extra_equations=(
        (_("Cathode (−), alkaline medium"), "4H<sub>2</sub>O + 4e<sup>−</sup> → 2H<sub>2</sub> + 4OH<sup>−</sup>"),
        (_("Anode (+), alkaline medium"), "4OH<sup>−</sup> → O<sub>2</sub> + 2H<sub>2</sub>O + 4e<sup>−</sup>"),
    ),
    items=(
        Item("electrolyzer", _("Electrolyzer with two gas tubes"), "device", "electrolyzer"),
        Item("dc_source", _("DC power supply"), "device", "dc"),
        Item(
            "ac_source",
            _("AC power supply"),
            "device",
            "ac",
            required=False,
            note=_("Alternating current keeps swapping the electrodes, so the gases would mix in both tubes. Electrolysis needs direct current."),
        ),
    ),
    steps=(
        Step(
            "select_electrolyzer",
            _("Select the electrolyzer"),
            _("An electrolyzer with two gas collecting tubes appears."),
            "place",
            items=("electrolyzer",),
        ),
        Step(
            "electrolyte",
            _("Select the electrolyte"),
            _("A suitable electrolyte solution is added."),
            "choice",
            options=(
                Option(
                    "naoh",
                    _("Sodium hydroxide solution, 5% (NaOH)"),
                    correct=True,
                    feedback=_("NaOH makes the solution conductive; it is water that is decomposed."),
                ),
                Option(
                    "water",
                    _("Distilled water"),
                    feedback=_("Pure water hardly conducts current: electrolysis would be extremely slow."),
                ),
                Option(
                    "nacl",
                    _("Sodium chloride solution (NaCl)"),
                    feedback=_("Chlorine, not oxygen, would be released at the anode."),
                ),
            ),
            early_warning=_("Select the electrolyzer first."),
        ),
        Step(
            "connect",
            _("Connect the electrodes"),
            _("The cathode (−) and the anode (+) are marked."),
            "action",
            early_warning=_("Fill the electrolyzer with the electrolyte first."),
        ),
        Step(
            "power_on",
            _("Switch on the DC source"),
            _("Electrolysis starts: bubbles form on both electrodes."),
            "action",
            items=("dc_source",),
            early_warning=_("Connect the electrodes first."),
        ),
        Step(
            "run_time",
            _("Run the time"),
            _("The gas volumes change; the V(t) graph is drawn."),
            "process",
            early_warning=_("Switch on the power supply first."),
        ),
        Step(
            "compare",
            _("Compare the gas volumes"),
            _("The ratio H₂ : O₂ = 2 : 1 is determined."),
            "action",
            early_warning=_("Let the electrolysis run first."),
        ),
        Step("conclusion", _("Draw a conclusion"), _("Write the electrode reactions."), "journal"),
        Step(
            "finish",
            _("Finish the experiment"),
            _("The results are saved and the analysis task opens."),
            "finish",
            early_warning=_("Fill in the lab journal first."),
        ),
    ),
    journal=(
        JournalField("v_h2", _("Volume of gas at the cathode"), "number", unit=_("mL")),
        JournalField("v_o2", _("Volume of gas at the anode"), "number", unit=_("mL")),
        JournalField("gas_cathode", _("Gas at the cathode"), "choice", options=GAS_OPTIONS),
        JournalField("gas_anode", _("Gas at the anode"), "choice", options=GAS_OPTIONS),
        JournalField("eq_cathode", _("Cathode reaction")),
        JournalField("eq_anode", _("Anode reaction")),
    ),
    questions=(
        Question(
            "ratio",
            _("Why is the volume of hydrogen twice the volume of oxygen?"),
            (
                Option(
                    "moles",
                    _("Two H₂ molecules form per O₂ molecule, and equal amounts of gases occupy equal volumes"),
                    correct=True,
                ),
                Option("light", _("Hydrogen is lighter than oxygen")),
                Option("faster", _("Hydrogen reacts faster")),
            ),
        ),
        Question(
            "cathode_process",
            _("Which process takes place at the cathode?"),
            (
                Option("red", _("Reduction"), correct=True),
                Option("ox", _("Oxidation")),
                Option("none", _("Neither")),
            ),
        ),
        Question(
            "why_naoh",
            _("Why is NaOH added to the water?"),
            (
                Option("conduct", _("To make the solution conduct current"), correct=True),
                Option("decompose", _("NaOH itself is decomposed")),
                Option("h2", _("To obtain more hydrogen from NaOH")),
            ),
        ),
        Question("teach_gases", _("How would you show the class which tube contains hydrogen and which contains oxygen?")),
    ),
    params=PARAMS,
)
