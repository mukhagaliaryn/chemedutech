"""Experiment 3 — chlorine with cold dilute and hot concentrated alkali (disproportionation).

Listed in the journal of the author's instruction (data/1.2) without its commands; written from the lecture
(§4.4), practice task 6 and the test (questions 4–5). Simulation only: chlorine is toxic.
"""
from django.utils.translation import gettext_lazy as _

from apps.labs.engine import ExperimentSpec, Item, JournalField, Option, Question, Step

from .common import CHLORINE_WATER, CL2_WATER, COLOURLESS, KI, RACK

PARAMS = {
    "rack_item": "rack",
    "tubes": [{"label": "A"}, {"label": "B"}],
    "ops": {
        "add_cold": [{"tube": 0, "pour": COLOURLESS, "level": 0.3, "text": "NaOH 2%"}],
        "add_hot": [{"tube": 1, "pour": COLOURLESS, "level": 0.3, "text": "NaOH 30%"}],
        "heat": [{"tube": 1, "heat": True, "dur": 3}, {"tube": 1, "bubbles": True, "at": 2, "dur": 1}],
        "add_cl2": [
            {"tube": 0, "pour": CHLORINE_WATER, "level": 0.42, "dur": 0.6},
            {"tube": 1, "pour": CHLORINE_WATER, "level": 0.42, "at": 0.3, "dur": 0.6},
            {"tube": 0, "color": COLOURLESS, "at": 1.4, "dur": 3},
            {"tube": 1, "color": COLOURLESS, "at": 1.4, "dur": 2},
        ],
        "observe": [{"tube": 1, "heat": False, "bubbles": False}, {"reveal": True}],
    },
}

EXPERIMENT = ExperimentSpec(
    key="chlorine_alkali",
    number=3,
    title=_("Chlorine with cold and hot alkali"),
    goal=_(
        "Compare the products of chlorine with cold dilute and hot concentrated sodium hydroxide and explain "
        "why both reactions are disproportionation."
    ),
    scene="tubes",
    equation="Cl<sub>2</sub> + 2NaOH → NaCl + NaClO + H<sub>2</sub>O",
    explanation=_(
        "In both tubes chlorine (0) is at the same time reduced to chloride (−1) and oxidised: to hypochlorite (+1) "
        "in cold dilute alkali and to chlorate (+5) in hot concentrated alkali. This is disproportionation; the "
        "conditions decide the product."
    ),
    extra_equations=(
        (_("Tube B, hot"), '3Cl<sub>2</sub> + 6NaOH <span class="eq-cat"><span>t°</span>→</span> 5NaCl + NaClO<sub>3</sub> + 3H<sub>2</sub>O'),
    ),
    items=(
        RACK,
        Item("naoh_dil", _("Sodium hydroxide solution, 2% (cold)"), "reagent", "bottle", formula="NaOH"),
        Item("naoh_conc", _("Sodium hydroxide solution, 30%"), "reagent", "bottle", formula="NaOH"),
        Item("water_bath", _("Hot water bath"), "device", "water_bath"),
        CL2_WATER,
        Item(
            "ki_extra",
            KI.name,
            "reagent",
            "bottle",
            formula="KI",
            required=False,
            note=_("Iodide is not needed here: this experiment studies chlorine and an alkali."),
        ),
    ),
    steps=(
        Step("take_rack", _("Take the rack and two test tubes"), _("Test tubes A and B are on the bench."), "place",
             items=("rack",)),
        Step("add_cold", _("A: pour cold dilute NaOH"), _("Tube A holds a cold 2% NaOH solution."), "place",
             items=("naoh_dil",), early_warning=_("Put the rack with the test tubes on the bench first.")),
        Step("add_hot", _("B: pour concentrated NaOH"), _("Tube B holds a 30% NaOH solution."), "place",
             items=("naoh_conc",), early_warning=_("Pour the solution into tube A first.")),
        Step(
            "heat",
            _("B: warm the tube in a hot water bath"),
            _("Tube B is hot (about 80 °C)."),
            "process",
            items=("water_bath",),
            early_warning=_("Pour concentrated NaOH into tube B first."),
        ),
        Step(
            "predict",
            _("Predict the salts formed in A and B"),
            _("The prediction is recorded."),
            "choice",
            options=(
                Option("right", _("A: NaCl and NaClO; B: NaCl and NaClO₃"), correct=True, feedback=_("Let us check it.")),
                Option("same", _("The same salts in both tubes"),
                       feedback=_("Temperature and concentration change the product of the oxidation of chlorine.")),
                Option("reverse", _("A: NaCl and NaClO₃; B: NaCl and NaClO"),
                       feedback=_("The higher oxidation state (+5) is reached on heating, not in the cold.")),
            ),
            early_warning=_("Prepare both tubes first."),
        ),
        Step(
            "add_cl2",
            _("Add chlorine water to both tubes"),
            _("The yellow-green colour of chlorine disappears in both tubes: chlorine has reacted with the alkali."),
            "process",
            items=("cl2",),
            early_warning=_("Chlorine water is toxic: it is added only when both tubes are ready (here — virtually)."),
            safety=True,
        ),
        Step("observe", _("Observe the result"), _("The equations for the cold and the hot alkali are shown."), "action",
             early_warning=_("Add chlorine water first.")),
        Step("journal", _("Save the lab journal"), _("Observations and equations are recorded."), "journal"),
        Step("finish", _("Finish the experiment"), _("The results are saved and the analysis task opens."), "finish",
             early_warning=_("Fill in the lab journal first.")),
    ),
    journal=(
        JournalField("obs", _("What happened to the colour of chlorine water in A and B?")),
        JournalField("eq_cold", _("Tube A (cold dilute NaOH): the equation"), "equation",
                     answer="Cl2 + 2NaOH -> NaCl + NaClO + H2O"),
        JournalField("eq_hot", _("Tube B (hot concentrated NaOH): the equation"), "equation",
                     answer="3Cl2 + 6NaOH -> 5NaCl + NaClO3 + 3H2O"),
        JournalField(
            "type",
            _("What type of redox reaction is it?"),
            "choice",
            options=(
                Option("disp", _("Disproportionation"), correct=True),
                Option("inter", _("Intermolecular redox reaction")),
                Option("neutral", _("Neutralisation")),
            ),
        ),
    ),
    questions=(
        Question(
            "ox_state",
            _("What is the oxidation state of chlorine in NaClO₃?"),
            (Option("p5", "+5", correct=True), Option("p1", "+1"), Option("m1", "−1"), Option("p7", "+7")),
        ),
        Question(
            "both",
            _("Why is chlorine both the oxidising and the reducing agent in these reactions?"),
            (
                Option("disp", _("Some chlorine atoms gain electrons (→ −1) and others lose them (→ +1 or +5)"),
                       correct=True),
                Option("sodium", _("Sodium changes its oxidation state")),
                Option("water", _("Water is the reducing agent")),
            ),
        ),
        Question(
            "use",
            _("Which product of the cold reaction is used for disinfection?"),
            (Option("naclo", _("Sodium hypochlorite NaClO"), correct=True), Option("nacl", _("Sodium chloride NaCl")),
             Option("naclo3", _("Sodium chlorate NaClO₃"))),
        ),
        Question("teach", _("Why should this experiment be shown to school students as a simulation?")),
    ),
    params=PARAMS,
)  # fmt: skip
