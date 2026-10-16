"""Items shared by several experiments of lab work 1."""
from django.utils.translation import gettext_lazy as _

from apps.labs.engine import Item

SPIRIT_LAMP_NO_HEAT = Item(
    "spirit_lamp",
    _("Spirit lamp"),
    "device",
    "lamp",
    required=False,
    note=_("Heating is not needed here: the reaction goes at room temperature."),
)

H2O2 = Item("h2o2", _("Hydrogen peroxide solution, 3%"), "reagent", "bottle", formula="H₂O₂")
MNO2 = Item("mno2", _("Manganese(IV) oxide"), "reagent", "jar_dark", formula="MnO₂")
