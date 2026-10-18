"""Lab work 4 (topic 4): qualitative tests for ammonium and phosphate ions — one experiment on the generic
«tubes» bench (A: NH₄⁺ + OH⁻ with indicator paper, B: PO₄³⁻ + Ag⁺)."""
from django.utils.translation import gettext_lazy as _

from apps.labs.engine.spec import LabSpec

from . import ions

LAB = LabSpec(
    key="t04",
    topic_number=4,
    title=_("Nitrogen and phosphorus: ammonium and phosphate ions"),
    experiments=(ions.EXPERIMENT,),
)
