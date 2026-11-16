"""Double jump part of Double Jump Dash (Borderlands GOTY / GOTY Enhanced).

Port of the double jump from ZetaDaemon's BL2 "Movement Tech" mod.

How it works
------------
The BL2 mod hooks ``WillowPlayerPawn:CanJump`` and ``PlayLanded``. Those may not exist in
Borderlands 1, so this port hooks the standard Unreal Engine 3 ``DoJump`` at every pawn class
level that could implement it (hooks on names that don't exist are simply never called).

When jump is pressed while falling and an air jump is available, the pawn is reported as
walking for the duration of ``DoJump``, so the game runs its own normal jump code (velocity,
sounds, animation). If the game still refuses the jump, the mod restores the falling state
and applies the jump velocity itself. Air jumps refill whenever the pawn lands.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import unrealsdk
from mods_base import (
    SliderOption,
    hook,
)
from unrealsdk import logging
from unrealsdk.hooks import Type

if TYPE_CHECKING:
    from unrealsdk.unreal import BoundFunction, UObject, WrappedStruct

EPhysics = unrealsdk.find_enum("EPhysics")
PLAYER_CONTROLLER_CLASS = unrealsdk.find_class("PlayerController")

# ---------------------------------------------------------------------------------------------
# Options
# ---------------------------------------------------------------------------------------------

AIR_JUMPS = SliderOption(
    "Air Jumps",
    1,
    1,
    5,
    1,
    is_integer=True,
    description="How many extra jumps you can make before touching the ground. Default 1.",
)
JUMP_HEIGHT = SliderOption(
    "Air Jump Strength",
    100,
    50,
    200,
    5,
    is_integer=True,
    description=(
        "Strength of air jumps as a percentage of a normal jump. Default 100 (same as the"
        " Movement Tech double jump)."
    ),
)

# ---------------------------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------------------------

# Seconds between two DoJump calls for the second one to count as a new key press. Some games
# call DoJump every frame while jump is held; this stops that from instantly burning the air
# jump right after leaving the ground.
FRESH_PRESS_GAP = 0.05

# Per-pawn state, keyed by pawn path name.
_jumps_used: dict[str, int] = {}
_last_jump_call: dict[str, float] = {}

# Set while we're running the game's DoJump with the physics temporarily swapped to walking.
# Holds (pawn key, path of the DoJump function that started it).
_active_air_jump: tuple[str, str] | None = None


def _key(pawn: UObject) -> str:
    return pawn._path_name()  # pyright: ignore[reportPrivateUsage]


def _refill(pawn: UObject) -> None:
    _jumps_used[_key(pawn)] = 0


def _is_player_pawn(pawn: UObject) -> bool:
    # Only players get air jumps, never AI.
    try:
        controller = pawn.Controller
    except AttributeError:
        return False
    if controller is None:
        return False
    return controller.Class._inherits(PLAYER_CONTROLLER_CLASS)  # pyright: ignore[reportPrivateUsage]


# ---------------------------------------------------------------------------------------------
# DoJump hooks
# ---------------------------------------------------------------------------------------------

# Every class level that might implement DoJump. Overrides usually call super, so several of
# these can fire for one jump - the logic below only acts in the outermost one.
DOJUMP_FUNCS = (
    "WillowGame.WillowPlayerPawn:DoJump",
    "WillowGame.WillowPawn:DoJump",
    "GearboxFramework.GearboxPawn:DoJump",
    "GameFramework.GamePawn:DoJump",
    "Engine.Pawn:DoJump",
)


def _do_jump_pre(
    pawn: UObject,
    _args: WrappedStruct,
    _ret: Any,
    func: BoundFunction,
) -> None:
    global _active_air_jump

    if _active_air_jump is not None:
        # Inner super call of an air jump we're already handling.
        return
    if not _is_player_pawn(pawn):
        return

    key = _key(pawn)
    now: float = pawn.WorldInfo.TimeSeconds
    last = _last_jump_call.get(key, -1.0)
    _last_jump_call[key] = now

    if pawn.Physics != EPhysics.PHYS_Falling:
        # Normal ground/ladder jump - make sure the air jumps are full.
        _jumps_used[key] = 0
        return

    if 0 <= now - last < FRESH_PRESS_GAP:
        # Jump still held from the previous frame, not a new press.
        return
    if _jumps_used.get(key, 0) >= AIR_JUMPS.value:
        return
    if pawn.bIsCrouched or pawn.bWantsToCrouch:
        return

    # Let the game's own jump code run by pretending we're on the ground.
    _active_air_jump = (key, func.func._path_name())  # pyright: ignore[reportPrivateUsage]
    pawn.Physics = EPhysics.PHYS_Walking


def _do_jump_post(
    pawn: UObject,
    _args: WrappedStruct,
    _ret: Any,
    func: BoundFunction,
) -> None:
    global _active_air_jump

    if _active_air_jump is None:
        return
    key, starter = _active_air_jump
    if key != _key(pawn) or starter != func.func._path_name():  # pyright: ignore[reportPrivateUsage]
        # Not the outermost DoJump call that started the air jump.
        return
    _active_air_jump = None

    if pawn.Physics == EPhysics.PHYS_Walking:
        # The game refused the jump (or something blocked it) - do it ourselves.
        pawn.Physics = EPhysics.PHYS_Falling
        pawn.Velocity.Z = pawn.JumpZ

    scale = JUMP_HEIGHT.value / 100
    if scale != 1:
        pawn.Velocity.Z = pawn.JumpZ * scale

    _jumps_used[key] = _jumps_used.get(key, 0) + 1


# Build one PRE and one POST_UNCONDITIONAL hook per candidate function. Each stacked decorator
# shares the same identifier, which the mod manager enables/disables with the mod.
_pre = _do_jump_pre
_post = _do_jump_post
for _name in DOJUMP_FUNCS:
    _pre = hook(_name, Type.PRE)(_pre)
    _post = hook(_name, Type.POST_UNCONDITIONAL)(_post)
do_jump_pre_hooks = _pre
do_jump_post_hooks = _post
del _pre, _post


# ---------------------------------------------------------------------------------------------
# Landing hooks - refill air jumps
# ---------------------------------------------------------------------------------------------

LANDED_FUNCS = (
    "WillowGame.WillowPlayerPawn:Landed",
    "WillowGame.WillowPawn:Landed",
    "GearboxFramework.GearboxPawn:Landed",
    "GameFramework.GamePawn:Landed",
    "Engine.Pawn:Landed",
)


def _landed(pawn: UObject, *_: Any) -> None:
    if _is_player_pawn(pawn):
        _refill(pawn)


_land = _landed
for _name in LANDED_FUNCS:
    _land = hook(_name, Type.POST)(_land)
landed_hooks = _land
del _land, _name


# ---------------------------------------------------------------------------------------------
# Enable / disable
# ---------------------------------------------------------------------------------------------


def _function_exists(path: str) -> bool:
    try:
        unrealsdk.find_object("Function", path)
    except ValueError:
        return False
    return True


def enable() -> None:
    global _active_air_jump
    _active_air_jump = None
    _jumps_used.clear()
    _last_jump_call.clear()

    if not any(_function_exists(f) for f in DOJUMP_FUNCS):
        logging.warning(
            "[Double Jump Dash] No DoJump function found - double jump will not work. Please report"
            " this.",
        )


def disable() -> None:
    global _active_air_jump
    _active_air_jump = None
    _jumps_used.clear()
    _last_jump_call.clear()


OPTIONS = [AIR_JUMPS, JUMP_HEIGHT]
HOOKS = [do_jump_pre_hooks, do_jump_post_hooks, landed_hooks]
