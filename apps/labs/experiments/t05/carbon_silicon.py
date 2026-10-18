"""The single experiment of lab work 5 (the author's instruction, data/1.5): CO₂ through limewater in two modes
(turbidity, then clearing in excess), a carbonate with acid (bubbles) and a silicate with acid (a gel).

The virtual CO₂ source is drawn as the first vessel of the rack and connected to tube A with a delivery tube; the
«send CO₂» command of the source has two modes, so it is two steps (limited and excess). A prediction step is added
before the excess mode, as in the other labs.
"""
from django.utils.translation import gettext_lazy as _

from apps.labs.engine import ExperimentSpec, Item, JournalField, Option, Question, Step

COLOURLESS = "#eaf3f7"
SOURCE = "#dfe9ef"
CACO3 = "#ffffff"
GEL = "#d3e2bd"

PARAMS = {
    "rack_item": "rack",
    "tubes": [{"label": "CO₂"}, {"label": "A"}, {"label": "B"}, {"label": "C"}],
    "ops": {
        "limewater": [{"tube": 1, "pour": COLOURLESS, "level": 0.38, "text": "Ca(OH)₂"}],
        "co2_source": [{"tube": 0, "pour": SOURCE, "level": 0.35, "text": "CO₂"}, {"pipe": [0, 1]}],
        "co2_limited": [
            {"tube": 0, "bubbles": True},
            {"tube": 1, "bubbles": True, "at": 0.8},
            {"tube": 1, "cloud": 0.9, "cloud_color": CACO3, "at": 1.4, "dur": 2.5},
            {"tube": 0, "bubbles": False, "at": 4},
            {"tube": 1, "bubbles": False, "at": 4},
        ],
        "co2_excess": [
            {"tube": 0, "bubbles": True},
            {"tube": 1, "bubbles": True, "at": 0.8},
            {"tube": 1, "cloud": 0, "at": 1.6, "dur": 4},
            {"tube": 0, "bubbles": False, "at": 6},
            {"tube": 1, "bubbles": False, "at": 6},
        ],
        "carbonate": [{"tube": 2, "pour": COLOURLESS, "level": 0.3, "text": "Na₂CO₃"}],
        "carbonate_acid": [
            {"tube": 2, "pour": COLOURLESS, "level": 0.4, "text": "Na₂CO₃ + HCl"},
            {"tube": 2, "bubbles": True, "at": 0.6},
            {"tube": 2, "bubbles": False, "at": 4.5},
        ],
        "silicate": [{"tube": 3, "pour": COLOURLESS, "level": 0.3, "text": "Na₂SiO₃"}],
        "silicate_acid": [
            {"tube": 3, "pour": COLOURLESS, "level": 0.4, "text": "Na₂SiO₃ + HCl"},
            {"tube": 3, "gel": GEL, "at": 0.8, "dur": 3},
            {"tube": 3, "cloud": 0.35, "at": 1.2, "dur": 2},
        ],
        "compare": [{"reveal": True}],
    },
}

EXPERIMENT = ExperimentSpec(
    key="carbon_silicon",
    number=1,
    title=_("Comparing carbon and silicon compounds"),
    goal=_(
        "Compare the acidic properties of carbon(IV) oxide, the reactions of the carbonate ion and the reaction of a "
        "silicate with acid; explain the observations at the macro, particle and symbolic levels."
    ),
    scene="tubes",
    equation="CO<sub>2</sub> + Ca(OH)<sub>2</sub> → CaCO<sub>3</sub>↓ + H<sub>2</sub>O",
    explanation=_(
        "CO₂ makes limewater turbid (insoluble CaCO₃); in excess the precipitate dissolves as soluble Ca(HCO₃)₂. A "
        "carbonate releases CO₂ with an acid. An acidified silicate gives a gel of hydrated silicon dioxide "
        "(SiO₂·nH₂O); H₂SiO₃ is only a conventional school formula for it."
    ),
    extra_equations=(
        (_("Excess CO₂"), "CaCO<sub>3</sub> + CO<sub>2</sub> + H<sub>2</sub>O → Ca(HCO<sub>3</sub>)<sub>2</sub>"),
        (_("Tube B, ionic"), "CO<sub>3</sub><sup>2−</sup> + 2H<sup>+</sup> → CO<sub>2</sub>↑ + H<sub>2</sub>O"),
        (_("Tube C (conventional)"), "Na<sub>2</sub>SiO<sub>3</sub> + 2HCl → 2NaCl + H<sub>2</sub>SiO<sub>3</sub>↓"),
    ),
    items=(
        Item("rack", _("Rack with three test tubes"), "glass", "rack"),
        Item("limewater", _("Clear limewater"), "reagent", "bottle", formula="Ca(OH)₂"),
        Item("co2_source", _("Virtual CO₂ source with a delivery tube"), "device", "gas_source"),
        Item("na2co3", _("Sodium carbonate solution"), "reagent", "bottle", formula="Na₂CO₃"),
        Item("hcl", _("Dilute hydrochloric acid"), "reagent", "bottle", formula="HCl"),
        Item("na2sio3", _("Sodium silicate solution"), "reagent", "bottle", formula="Na₂SiO₃"),
        Item(
            "naoh",
            _("Sodium hydroxide solution"),
            "reagent",
            "bottle",
            formula="NaOH",
            required=False,
            note=_("NaOH would absorb CO₂ without a visible change: CO₂ is detected with limewater."),
        ),
    ),
    steps=(
        Step("safety", _("Start the lab: confirm the safety notice"),
             _("Virtual mode only: CO₂ can suffocate in a closed room, acids are irritants."), "action"),
        Step("take_rack", _("Take the rack and three test tubes"), _("Tubes A, B and C are on the bench."), "place",
             items=("rack",), early_warning=_("Confirm the safety notice first.")),
        Step("limewater", _("A: pour limewater"), _("Tube A holds a clear Ca(OH)₂ solution."), "place",
             items=("limewater",), early_warning=_("Put the rack with the test tubes on the bench first.")),
        Step("co2_source", _("Connect the CO₂ source"), _("The delivery tube leads into tube A."), "place",
             items=("co2_source",), early_warning=_("Pour limewater into tube A first: there must be something to detect CO₂ with.")),
        Step("co2_limited", _("Send CO₂ — stage 1"), _("Solution A turns turbid: a white CaCO₃ precipitate forms."),
             "process", early_warning=_("Connect the CO₂ source to tube A first.")),
        Step(
            "predict",
            _("Predict: what happens if CO₂ is passed further?"),
            _("The prediction is recorded."),
            "choice",
            options=(
                Option("clear", _("The turbidity disappears: soluble Ca(HCO₃)₂ forms"), correct=True,
                       feedback=_("Let us check it.")),
                Option("more", _("Even more precipitate forms"),
                       feedback=_("All the Ca(OH)₂ has already reacted; excess CO₂ reacts with CaCO₃ itself.")),
                Option("gas", _("The precipitate turns into a gas")),
            ),
            early_warning=_("Run stage 1 first."),
        ),
        Step("co2_excess", _("Send CO₂ — in excess"),
             _("The turbidity gradually disappears: soluble Ca(HCO₃)₂ goes into solution."), "process",
             early_warning=_("Make a prediction first.")),
        Step("carbonate", _("B: pour the Na₂CO₃ solution"), _("Tube B holds a colourless carbonate solution."),
             "place", items=("na2co3",), early_warning=_("Finish the experiment in tube A first.")),
        Step("carbonate_acid", _("B: add HCl"), _("Gas bubbles: CO₂ is released."), "process", items=("hcl",),
             early_warning=_("Pour the carbonate solution into tube B first.")),
        Step("silicate", _("C: pour the Na₂SiO₃ solution"), _("Tube C holds a colourless silicate solution."), "place",
             items=("na2sio3",), early_warning=_("Finish the experiment in tube B first.")),
        Step("silicate_acid", _("C: add HCl"), _("A gel-like precipitate of hydrated silicon dioxide forms."),
             "process", early_warning=_("Pour the silicate solution into tube C first.")),
        Step(
            "compare",
            _("Compare the results"),
            _("The observations of A, B and C are compared; the equations are shown."),
            "choice",
            options=(
                Option("right", _("B — CO₂ bubbles; C — a gel of hydrated SiO₂"), correct=True,
                       feedback=_("Right: the carbonate gives a gas, the silicate a gel.")),
                Option("both_gas", _("Both B and C release CO₂"),
                       feedback=_("There is no carbon in a silicate: no CO₂ can come from it.")),
                Option("none", _("Nothing happens in B and C"), feedback=_("Look at the bubbles in B and the gel in C again.")),
            ),
            early_warning=_("Carry out the experiments in all three tubes first."),
        ),
        Step("journal", _("Save the journal"), _("Observations, equations and explanations are recorded."), "journal"),
        Step("finish", _("Submit the work"), _("The answers are checked and the analysis opens."), "finish",
             early_warning=_("Fill in the lab journal first.")),
    ),
    journal=(
        JournalField("eq_a1", _("A — CO₂ + limewater: the equation"), "equation", answer="CO2 + Ca(OH)2 -> CaCO3 + H2O"),
        JournalField("eq_a2", _("A — excess CO₂: the equation"), "equation", answer="CaCO3 + CO2 + H2O -> Ca(HCO3)2"),
        JournalField("eq_b", _("B — carbonate + acid: the short ionic equation"), "equation",
                     answer="CO3^2- + 2H+ -> CO2 + H2O"),
        JournalField("eq_c", _("C — silicate + acid: the conventional equation"), "equation",
                     answer="Na2SiO3 + 2HCl -> 2NaCl + H2SiO3"),
        JournalField(
            "gel",
            _("C — what forms?"),
            "choice",
            options=(
                Option("gel", _("A gel of hydrated silicon dioxide (SiO₂·nH₂O)"), correct=True),
                Option("crystal", _("Pure crystals of H₂SiO₃")),
                Option("co2", _("CO₂ gas")),
            ),
        ),
        JournalField("conclusion", _("Conclusion: how do the carbonate and the silicate differ?")),
    ),
    questions=(
        Question(
            "turbid",
            _("Why does CO₂ first make limewater turbid and then clear?"),
            (
                Option("hco3", _("CaCO₃ forms first; in excess CO₂ it turns into soluble Ca(HCO₃)₂"), correct=True),
                Option("temp", _("The solution warms up and the precipitate melts")),
                Option("evap", _("The water evaporates")),
            ),
        ),
        Question(
            "difference",
            _("How do the observations differ when acid is added to a carbonate and to a silicate?"),
            (
                Option("right", _("The carbonate releases gas; the silicate gives a gel-like precipitate"), correct=True),
                Option("same", _("They are the same")),
                Option("reverse", _("The silicate releases gas; the carbonate gives a gel")),
            ),
        ),
        Question(
            "formula",
            _("Why is the product in tube C hard to describe by one simple formula?"),
            (
                Option("gel", _("It is a gel of hydrated and polymerised silicic acid species, SiO₂·nH₂O"), correct=True),
                Option("gas", _("It is a gas")),
                Option("unknown", _("Its elements are unknown")),
            ),
        ),
        Question("levels", _("Which three levels of representation (macro, particle, symbolic) would you link in a school lesson, and how?")),
    ),
    params=PARAMS,
)  # fmt: skip
