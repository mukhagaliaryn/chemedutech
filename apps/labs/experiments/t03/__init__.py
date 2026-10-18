"""Lab work 3 (topic 3): oxidation of sulfur(IV) and the qualitative test for sulfate — one experiment on the
generic «tubes» bench (reactor A → absorber B → sample C, control D)."""
from django.utils.translation import gettext_lazy as _

from apps.labs.engine.spec import LabSpec

from . import sulfate

LAB = LabSpec(
    key="t03",
    topic_number=3,
    title=_("Sulfur: oxidation of SO₂ and the sulfate test"),
    experiments=(sulfate.EXPERIMENT,),
)
