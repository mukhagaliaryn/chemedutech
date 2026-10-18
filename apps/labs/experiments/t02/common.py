"""Items and colours shared by the experiments of lab work 2 (halogens). The scene is the generic «tubes» bench."""
from django.utils.translation import gettext_lazy as _

from apps.labs.engine import Item

RACK = Item("rack", _("Rack with test tubes"), "glass", "rack")
KCL = Item("kcl", _("Potassium chloride solution"), "reagent", "bottle", formula="KCl")
KBR = Item("kbr", _("Potassium bromide solution"), "reagent", "bottle", formula="KBr")
KI = Item("ki", _("Potassium iodide solution"), "reagent", "bottle", formula="KI")
CL2_WATER = Item("cl2", _("Chlorine water"), "reagent", "bottle_yellow", formula="Cl₂(aq)")
BR2_WATER = Item("br2", _("Bromine water"), "reagent", "bottle_brown", formula="Br₂(aq)")

# solution colours in the tubes
COLOURLESS = "#eaf3f7"
CHLORINE_WATER = "#e9f1ad"  # pale yellow-green
BROMINE_WATER = "#f1c27a"  # pale orange (the colour of bromine water itself)
IODINE = "#b5682a"  # brown: iodine formed in solution
BROMINE = "#e69a3c"  # yellow-orange: bromine formed in solution
AGCL = "#fbfbf8"  # white
AGBR = "#f1e6b4"  # pale cream
AGI = "#f1d443"  # yellow
