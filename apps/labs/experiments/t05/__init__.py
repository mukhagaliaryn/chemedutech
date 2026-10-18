"""Lab work 5 (topic 5): carbon and silicon compounds compared — one experiment on the generic «tubes» bench
(CO₂ source → limewater A, carbonate B, silicate C)."""
from django.utils.translation import gettext_lazy as _

from apps.labs.engine.spec import LabSpec

from . import carbon_silicon

LAB = LabSpec(
    key="t05",
    topic_number=5,
    title=_("Carbon and silicon compounds"),
    experiments=(carbon_silicon.EXPERIMENT,),
)
