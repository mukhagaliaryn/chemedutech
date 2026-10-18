"""The single experiment of lab work 3 (the author's instruction, data/1.3): SO₂ from sulfite, its oxidation by
H₂O₂ to sulfate and the BaCl₂ test with a control sample.

Fixes against the source: water is poured into absorber B before the acid is added to A (otherwise the gas would
escape — the source has it the other way round); the acidity of the SO₂ solution is shown with indicator paper;
the automatic feedback of the source (SO₃ instead of SO₂, H₂O₂ as a reducing agent, BaCl₂ too early, the colour of
BaSO₄) is built into the choice steps and warnings.
"""
from django.utils.translation import gettext_lazy as _

from apps.labs.engine import ExperimentSpec, Item, JournalField, Option, Question, Step

COLOURLESS = "#eaf3f7"
ACID_PAPER = "#e0574f"
BASO4 = "#fbfbf8"

PARAMS = {
    "rack_item": "rack",
    "tubes": [{"label": "A"}, {"label": "B"}, {"label": "C"}, {"label": "D"}],
    "ops": {
        "connect": [{"pipe": [0, 1]}],
        "water_b": [{"tube": 1, "pour": COLOURLESS, "level": 0.4, "text": "H₂O"}],
        "add_sulfite": [{"tube": 0, "pour": COLOURLESS, "level": 0.3, "text": "Na₂SO₃"}],
        "add_hcl": [
            {"tube": 0, "pour": COLOURLESS, "level": 0.38, "dur": 0.6},
            {"tube": 0, "bubbles": True, "at": 0.8},
            {"tube": 1, "bubbles": True, "at": 1.6, "dur": 3},
            {"tube": 0, "bubbles": False, "at": 4.5},
            {"tube": 1, "bubbles": False, "at": 4.6},
        ],
        "acidity": [{"tube": 1, "paper": "#f3e6a8"}, {"tube": 1, "paper": ACID_PAPER, "at": 0.6, "dur": 1.8}],
        "add_h2o2": [{"tube": 1, "paper": ""}, {"tube": 1, "pour": COLOURLESS, "level": 0.48, "text": "H₂SO₄"}],
        "transfer": [{"tube": 2, "pour": COLOURLESS, "level": 0.3, "text": "SO₄²⁻"}],
        "bacl2": [
            {"tube": 2, "pour": COLOURLESS, "level": 0.4},
            {"tube": 2, "cloud": 0.9, "cloud_color": BASO4, "at": 0.7},
            {"tube": 2, "precipitate": BASO4, "at": 1.4, "dur": 2.5},
        ],
        "control": [
            {"tube": 3, "pour": COLOURLESS, "level": 0.3, "text": "SO₃²⁻ + HCl"},
            {"tube": 3, "pour": COLOURLESS, "level": 0.4, "at": 1.2},
            {"tube": 3, "cloud": 0.25, "cloud_color": BASO4, "at": 1.8},
            {"tube": 3, "cloud": 0, "at": 3.2, "dur": 1.5},
            {"reveal": True, "at": 3.5},
        ],
    },
}

EXPERIMENT = ExperimentSpec(
    key="sulfate",
    number=1,
    title=_("Oxidation of sulfur(IV) and the qualitative test for sulfate"),
    goal=_(
        "Obtain SO₂ from sodium sulfite, oxidise it with hydrogen peroxide to sulfate (S +4 → +6) and prove the "
        "sulfate ion with barium chloride in an acidic medium, comparing with a control sample."
    ),
    scene="tubes",
    equation="Ba<sup>2+</sup> + SO<sub>4</sub><sup>2−</sup> → BaSO<sub>4</sub>↓",
    explanation=_(
        "SO₂ is sulfur(IV) oxide, an acidic oxide. Hydrogen peroxide oxidises sulfur from +4 to +6. The sulfate ion "
        "is proven by the white BaSO₄ precipitate that does not dissolve in acid; a sulfite gives no stable "
        "precipitate in an acidic medium, so a control sample is needed."
    ),
    extra_equations=(
        (_("Reactor A"), "Na<sub>2</sub>SO<sub>3</sub> + 2HCl → 2NaCl + SO<sub>2</sub>↑ + H<sub>2</sub>O"),
        (_("Absorber B"), "SO<sub>2</sub> + H<sub>2</sub>O ⇌ H<sub>2</sub>SO<sub>3</sub>; SO<sub>2</sub> + H<sub>2</sub>O<sub>2</sub> → H<sub>2</sub>SO<sub>4</sub>"),
        (_("Tube C"), "H<sub>2</sub>SO<sub>4</sub> + BaCl<sub>2</sub> → BaSO<sub>4</sub>↓ + 2HCl"),
    ),
    items=(
        Item("rack", _("Reactor A, absorber B and test tubes C, D"), "glass", "rack"),
        Item("gas_tube", _("Gas delivery tube"), "glass", "stopper"),
        Item("water", _("Distilled water"), "reagent", "bottle", formula="H₂O"),
        Item("na2so3", _("Sodium sulfite solution"), "reagent", "bottle", formula="Na₂SO₃"),
        Item("hcl", _("Hydrochloric acid"), "reagent", "bottle", formula="HCl"),
        Item("indicator", _("Universal indicator paper"), "reagent", "paper"),
        Item("h2o2", _("Hydrogen peroxide solution"), "reagent", "bottle", formula="H₂O₂"),
        Item("bacl2", _("Barium chloride solution"), "reagent", "bottle_dark", formula="BaCl₂"),
        Item(
            "naoh",
            _("Sodium hydroxide solution"),
            "reagent",
            "bottle",
            formula="NaOH",
            required=False,
            note=_("An alkali would absorb SO₂ as sulfite and spoil the test for the acidic medium. It is not needed here."),
        ),
    ),
    steps=(
        Step("safety", _("Confirm the safety notice"),
             _("Virtual mode only: SO₂ and barium compounds are toxic, nothing is mixed for real."), "action"),
        Step("take_rack", _("Select reactor A, absorber B and test tubes C, D"), _("The vessels are on the bench."),
             "place", items=("rack",), early_warning=_("Confirm the safety notice first.")),
        Step("connect", _("Connect the gas delivery system"),
             _("Reactor A is connected to absorber B with a tube: the gas path is closed."), "place",
             items=("gas_tube",), early_warning=_("Put the vessels on the bench first.")),
        Step("water_b", _("B: pour distilled water"), _("Absorber B holds water to dissolve the gas."), "place",
             items=("water",), early_warning=_("Connect A and B first.")),
        Step("add_sulfite", _("A: pour the Na₂SO₃ solution"), _("Reactor A holds a sodium sulfite solution (S +4)."),
             "place", items=("na2so3",), early_warning=_("Prepare absorber B first: the gas must have somewhere to go.")),
        Step(
            "add_hcl",
            _("A: add hydrochloric acid"),
            _("Bubbles in A: a gas is released and passes into B."),
            "process",
            items=("hcl",),
            early_warning=_("SO₂ is toxic: the acid is added only when the closed gas path and absorber B are ready."),
            safety=True,
        ),
        Step(
            "identify_gas",
            _("Which gas has passed into B?"),
            _("The gas is SO₂, sulfur(IV) oxide."),
            "choice",
            options=(
                Option("so2", "SO₂", correct=True, feedback=_("Right: sulfur keeps the oxidation state +4.")),
                Option("so3", "SO₃", feedback=_("Check the oxidation state of S in Na₂SO₃ and the formula of the gas formed.")),
                Option("h2s", "H₂S", feedback=_("Sulfur is not reduced here: it stays +4.")),
            ),
            early_warning=_("Run the reaction in A first."),
        ),
        Step("acidity", _("B: test the medium with indicator paper"),
             _("The paper turns red: the SO₂ solution is acidic — SO₂ is an acidic oxide."), "process",
             items=("indicator",), early_warning=_("Pass the gas into B first.")),
        Step("add_h2o2", _("B: add H₂O₂"), _("Sulfur(IV) is oxidised to sulfur(VI): sulfate forms in B."), "place",
             items=("h2o2",), early_warning=_("Check the medium in B first.")),
        Step(
            "h2o2_role",
            _("What is the role of H₂O₂ in this step?"),
            _("H₂O₂ is the oxidising agent."),
            "choice",
            options=(
                Option("oxidant", _("Oxidising agent"), correct=True, feedback=_("Right: it accepts the electrons.")),
                Option("reductant", _("Reducing agent"),
                       feedback=_("The oxidation state of S rose from +4 to +6. Which substance accepts the electrons?")),
                Option("catalyst", _("Catalyst"), feedback=_("H₂O₂ is used up in the reaction: it is not a catalyst.")),
            ),
            early_warning=_("Add H₂O₂ to B first."),
        ),
        Step("transfer", _("Transfer the sample into tube C"), _("Tube C holds the oxidised sample: «sample for analysis»."),
             "action", early_warning=_("Oxidise the sample in B first.")),
        Step(
            "bacl2",
            _("C: run the BaCl₂ test in an acidic medium"),
            _("A white BaSO₄ precipitate forms in C: the sulfate ion is detected."),
            "process",
            items=("bacl2",),
            early_warning=_("Turn S(+IV) into S(+VI) first and transfer the sample; then compare with the sulfate test in an acidic medium."),
        ),
        Step("control", _("Compare with the control sample"),
             _("D (sulfite, acidified, not oxidised): no stable precipitate — sulfite must not be confused with sulfate."),
             "process", early_warning=_("Run the test in tube C first.")),
        Step("journal", _("Check the equations and save the journal"), _("Observations and equations are recorded."),
             "journal"),
        Step("finish", _("Save the lab journal and finish"), _("The results are saved and the analysis task opens."),
             "finish", early_warning=_("Fill in the lab journal first.")),
    ),
    journal=(
        JournalField("eq_so2", _("Formation of SO₂ in reactor A: the equation"), "equation",
                     answer="Na2SO3 + 2HCl -> 2NaCl + SO2 + H2O"),
        JournalField("eq_ox", _("Oxidation of SO₂ by hydrogen peroxide: the equation"), "equation",
                     answer="SO2 + H2O2 -> H2SO4"),
        JournalField("eq_ba", _("The sulfate test: the short ionic equation"), "equation", answer="Ba2+ + SO4^2- -> BaSO4"),
        JournalField(
            "s_change",
            _("How does the oxidation state of sulfur change in B?"),
            "choice",
            options=(Option("up", "+4 → +6", correct=True), Option("down", "+6 → +4"), Option("zero", "0 → +4")),
        ),
        JournalField(
            "ppt",
            _("What is the BaSO₄ precipitate like?"),
            "choice",
            options=(
                Option("white", _("White, insoluble in water and dilute acid"), correct=True),
                Option("yellow", _("Yellow")),
                Option("black", _("Black")),
            ),
        ),
        JournalField("conclusion", _("Conclusion: how was the sulfate ion proven?")),
    ),
    questions=(
        Question(
            "so2_state",
            _("Why is the oxidation state of sulfur +4 in SO₂?"),
            (
                Option("calc", _("Two oxygen atoms give 2 × (−2) = −4, the molecule is neutral, so S = +4"), correct=True),
                Option("group", _("Because sulfur is in group 4")),
                Option("bonds", _("Because sulfur forms four bonds with hydrogen")),
            ),
        ),
        Question(
            "control_why",
            _("Why is the control sample in an acidic medium important?"),
            (
                Option("sulfite", _("Barium sulfite can also give a precipitate; in acid only BaSO₄ stays"), correct=True),
                Option("speed", _("It makes the reaction faster")),
                Option("colour", _("It colours the precipitate")),
            ),
        ),
        Question(
            "colour",
            _("What colour is the BaSO₄ precipitate?"),
            (Option("white", _("White"), correct=True), Option("yellow", _("Yellow")), Option("black", _("Black"))),
        ),
        Question("virtual", _("Why is this work done virtually and not with real reagents?")),
    ),
    params=PARAMS,
)  # fmt: skip
