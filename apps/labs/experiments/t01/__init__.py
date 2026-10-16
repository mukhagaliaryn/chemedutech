"""Lab work 1 (topic 1): hydrogen and oxygen — obtaining, collecting, electrolysis, catalysis."""
from django.utils.translation import gettext_lazy as _

from apps.labs.engine.spec import LabSpec

from . import electrolysis, hydrogen, oxygen, rate

LAB = LabSpec(
    key="t01",
    topic_number=1,
    title=_("Hydrogen and oxygen: obtaining and properties"),
    experiments=(hydrogen.EXPERIMENT, oxygen.EXPERIMENT, electrolysis.EXPERIMENT, rate.EXPERIMENT),
)
