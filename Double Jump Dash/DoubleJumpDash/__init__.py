"""Double Jump Dash for Borderlands GOTY / GOTY Enhanced (willow1-mod-manager).

Combines two movement features ported from Borderlands 2 SDK mods:
- Double jump, from ZetaDaemon's "Movement Tech" (see double_jump.py).
- Air dash, from juso's "BL2 Eternal" (see air_dash.py).
"""

from mods_base import GroupedOption, build_mod

from . import air_dash, double_jump


def on_enable() -> None:
    double_jump.enable()
    air_dash.enable()


def on_disable() -> None:
    double_jump.disable()
    air_dash.disable()


mod = build_mod(
    options=[
        GroupedOption("Double Jump", double_jump.OPTIONS),
        GroupedOption("Air Dash", air_dash.OPTIONS),
    ],
    keybinds=air_dash.KEYBINDS,
    hooks=[*double_jump.HOOKS, *air_dash.HOOKS],
)
