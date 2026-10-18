"""The single experiment of lab work 4 (the author's instruction, data/1.4): NH₄⁺ with an alkali (ammonia detected
by indicator paper only — never sniffed) and PO₄³⁻ with silver nitrate (yellow Ag₃PO₄).

The «save result A to the journal» command of the source becomes a choice step (which gas turned the paper blue);
the whole journal with the four equations is filled at the end, as in the other labs.
"""
from django.utils.translation import gettext_lazy as _

from apps.labs.engine import ExperimentSpec, Item, JournalField, Option, Question, Step

COLOURLESS = "#eaf3f7"
PAPER_DRY = "#f3e6a8"
PAPER_ALKALINE = "#4f86c6"
AG3PO4 = "#f0c419"

PARAMS = {
    "rack_item": "rack",
    "tubes": [{"label": "A"}, {"label": "B"}],
    "ops": {
        "add_nh4cl": [{"tube": 0, "pour": COLOURLESS, "level": 0.3, "text": "NH₄Cl"}],
        "add_naoh": [{"tube": 0, "pour": COLOURLESS, "level": 0.4, "text": "NH₄Cl + NaOH"},
                     {"tube": 0, "bubbles": True, "at": 1}],
        "indicator": [{"tube": 0, "paper": PAPER_DRY}, {"tube": 0, "paper": PAPER_ALKALINE, "at": 0.8, "dur": 2.5}],
        "add_na3po4": [{"tube": 0, "bubbles": False},
                       {"tube": 1, "pour": COLOURLESS, "level": 0.3, "text": "Na₃PO₄"}],
        "add_agno3": [{"tube": 1, "pour": COLOURLESS, "level": 0.4, "text": "Na₃PO₄ + AgNO₃"},
                      {"tube": 1, "cloud": 0.85, "cloud_color": AG3PO4, "at": 0.7},
                      {"tube": 1, "precipitate": AG3PO4, "at": 1.4, "dur": 2.5}],
        "zoom": [{"tube": 1, "cloud": 0.3, "dur": 2}, {"reveal": True}],
    },
}  # fmt: skip

EXPERIMENT = ExperimentSpec(
    key="ions",
    number=1,
    title=_("Qualitative tests for ammonium and phosphate ions"),
    goal=_(
        "Detect the ammonium ion with an alkali and indicator paper, and the phosphate ion with silver nitrate; "
        "write the molecular and the short ionic equations and justify the safety decisions."
    ),
    scene="tubes",
    equation="NH<sub>4</sub><sup>+</sup> + OH<sup>−</sup> → NH<sub>3</sub>↑ + H<sub>2</sub>O",
    explanation=_(
        "An alkali turns ammonium ions into ammonia, a gas with basic properties: wet indicator paper turns blue. "
        "Nitrogen keeps the oxidation state −3 — it is an acid–base reaction, not a redox one. Phosphate ions give "
        "a yellow Ag₃PO₄ precipitate with silver ions in a model solution; in real samples the pH and other ions "
        "matter."
    ),
    extra_equations=(
        (_("Tube A"), "NH<sub>4</sub>Cl + NaOH → NH<sub>3</sub>↑ + NaCl + H<sub>2</sub>O"),
        (_("Tube B"), "Na<sub>3</sub>PO<sub>4</sub> + 3AgNO<sub>3</sub> → Ag<sub>3</sub>PO<sub>4</sub>↓ + 3NaNO<sub>3</sub>"),
        (_("Tube B, ionic"), "PO<sub>4</sub><sup>3−</sup> + 3Ag<sup>+</sup> → Ag<sub>3</sub>PO<sub>4</sub>↓"),
    ),
    items=(
        Item("rack", _("Rack with two test tubes"), "glass", "rack"),
        Item("nh4cl", _("Ammonium chloride solution"), "reagent", "bottle", formula="NH₄Cl"),
        Item("naoh", _("Sodium hydroxide solution"), "reagent", "bottle", formula="NaOH"),
        Item("indicator", _("Wet universal indicator paper"), "reagent", "paper"),
        Item("na3po4", _("Sodium phosphate solution"), "reagent", "bottle", formula="Na₃PO₄"),
        Item("agno3", _("Silver nitrate solution"), "reagent", "bottle_dark", formula="AgNO₃"),
        Item(
            "spirit_lamp",
            _("Spirit lamp"),
            "device",
            "lamp",
            required=False,
            note=_("Heating is not needed: the indicator shows the gas. Ammonia is never sniffed."),
        ),
        Item(
            "hno3",
            _("Dilute nitric acid"),
            "reagent",
            "bottle",
            formula="HNO₃",
            required=False,
            note=_("Acid would turn phosphate into HPO₄²⁻ and H₂PO₄⁻, and the Ag₃PO₄ precipitate would not form."),
        ),
    ),
    steps=(
        Step("safety", _("Accept the safety rules"),
             _("Virtual mode only: ammonia irritates the airways, silver nitrate is hazardous."), "action"),
        Step("take_rack", _("Take the rack and two test tubes"), _("Test tubes A and B are on the bench."), "place",
             items=("rack",), early_warning=_("Accept the safety rules first.")),
        Step("add_nh4cl", _("A: pour the NH₄Cl solution"), _("Tube A holds a colourless model NH₄Cl solution."),
             "place", items=("nh4cl",), early_warning=_("Put the rack with the test tubes on the bench first.")),
        Step("add_naoh", _("A: add NaOH"), _("The reaction of the ammonium ion with the base starts."), "place",
             items=("naoh",), early_warning=_("Pour the NH₄Cl solution into tube A first.")),
        Step(
            "indicator",
            _("A: hold the indicator paper over the tube"),
            _("The wet paper turns blue: an alkaline gas, ammonia, is released."),
            "process",
            items=("indicator",),
            early_warning=_("Ammonia is never sniffed: the gas is tested only with indicator paper once the reaction has started."),
            safety=True,
        ),
        Step(
            "gas_a",
            _("Which gas turned the paper blue?"),
            _("The result of tube A is recorded: NH₃ is formed."),
            "choice",
            options=(
                Option("nh3", _("Ammonia NH₃ — a gas with basic properties"), correct=True,
                       feedback=_("Right: NH₃ + H₂O ⇌ NH₄⁺ + OH⁻ makes the paper blue.")),
                Option("n2", _("Nitrogen N₂"), feedback=_("Nitrogen does not change its oxidation state here (−3) and does not colour the paper.")),
                Option("hcl", _("Hydrogen chloride HCl"), feedback=_("Hydrogen chloride is acidic: the paper would turn red.")),
            ),
            early_warning=_("Test the gas with indicator paper first."),
        ),
        Step("add_na3po4", _("B: pour the Na₃PO₄ solution"), _("Tube B holds a colourless model phosphate solution."),
             "place", items=("na3po4",), early_warning=_("Finish the test in tube A first.")),
        Step("add_agno3", _("B: add AgNO₃"), _("A yellow Ag₃PO₄ precipitate forms."), "process", items=("agno3",),
             early_warning=_("Pour the phosphate solution into tube B first.")),
        Step("zoom", _("Look at the precipitate closely"), _("The solid phase settles; the ionic scheme is shown."),
             "action", early_warning=_("Add silver nitrate first.")),
        Step("journal", _("Check the equations and save the journal"), _("Observations and equations are recorded."),
             "journal"),
        Step("finish", _("Submit the conclusion"), _("The journal and the score are saved, the analysis opens."),
             "finish", early_warning=_("Fill in the lab journal first.")),
    ),
    journal=(
        JournalField("obs_a", _("A: NH₄⁺ + OH⁻ — what was observed?")),
        JournalField("eq_a_mol", _("A: the molecular equation"), "equation", answer="NH4Cl + NaOH -> NH3 + NaCl + H2O"),
        JournalField("eq_a_ion", _("A: the short ionic equation"), "equation", answer="NH4+ + OH- -> NH3 + H2O"),
        JournalField("eq_b_mol", _("B: the molecular equation"), "equation",
                     answer="Na3PO4 + 3AgNO3 -> Ag3PO4 + 3NaNO3"),
        JournalField("eq_b_ion", _("B: the short ionic equation"), "equation", answer="PO4^3- + 3Ag+ -> Ag3PO4"),
        JournalField(
            "ppt_b",
            _("B: PO₄³⁻ + Ag⁺ — what precipitate formed?"),
            "choice",
            options=(
                Option("yellow", _("Yellow Ag₃PO₄"), correct=True),
                Option("white", _("White AgCl")),
                Option("black", _("Black Ag₂O")),
            ),
        ),
        JournalField("safety", _("Safety decision: how was the gas tested and why?")),
    ),
    questions=(
        Question(
            "gas",
            _("Which gas forms when NH₄Cl reacts with NaOH, and what are its properties?"),
            (
                Option("nh3", _("Ammonia NH₃; its solution is basic"), correct=True),
                Option("h2", _("Hydrogen H₂; it is flammable")),
                Option("cl2", _("Chlorine Cl₂; it is yellow-green")),
            ),
        ),
        Question(
            "nitrogen",
            _("Why does the oxidation state of nitrogen not change in NH₄⁺ + OH⁻?"),
            (
                Option("acid_base", _("It is −3 in both NH₄⁺ and NH₃: this is an acid–base reaction"), correct=True),
                Option("catalyst", _("Because the alkali is a catalyst")),
                Option("noble", _("Because nitrogen is inert")),
            ),
        ),
        Question(
            "ph",
            _("Why does the pH matter in the test for phosphate?"),
            (
                Option("protonated", _("In acid, protonated forms (HPO₄²⁻, H₂PO₄⁻) dominate and the precipitate does not form"), correct=True),
                Option("colour", _("The pH changes the colour of silver")),
                Option("none", _("It does not matter")),
            ),
        ),
        Question("screens", _("Which three screen views would you choose to explain this experiment to school students?")),
    ),
    params=PARAMS,
)  # fmt: skip
