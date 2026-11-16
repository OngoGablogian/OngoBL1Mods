# Fast Travel Anywhere
# Standalone extraction of the "Open Fast Travel Menu/Respec" keybind from
# Bonk Utilities by Pyrex (https://github.com/PyrexBLJ/BL1-SDK-Mods), GPL-3.0.
from mods_base import EInputEvent, build_mod, get_pc, keybind


@keybind(
    identifier="Open Fast Travel Menu/Respec",
    key=None,
    event_filter=EInputEvent.IE_Pressed,
    description="Opens the New-U fast travel / respec station menu from anywhere",
)
def doFastTravel() -> None:
    pc = get_pc()
    if pc is None or pc.Pawn is None:
        return
    pc.PlayGfxMovieDefinition("ui_registration_station.Definitions.registration_station_def")


build_mod()
