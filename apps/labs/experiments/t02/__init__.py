"""Lab work 2 (topic 2): halogens — displacement, halide ions with silver nitrate, chlorine with alkali.

All three experiments run on the generic «tubes» bench (ui/static/js/lab/experiments/tubes.js)."""
from django.utils.translation import gettext_lazy as _

from apps.labs.engine.spec import LabSpec

from . import alkali, displacement, silver

LAB = LabSpec(
    key="t02",
    topic_number=2,
    title=_("Halogens: oxidising ability and halide ions"),
    experiments=(displacement.EXPERIMENT, silver.EXPERIMENT, alkali.EXPERIMENT),
)
