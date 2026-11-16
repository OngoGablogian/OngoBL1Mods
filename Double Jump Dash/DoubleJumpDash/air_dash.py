"""Air dash part of Double Jump Dash (Borderlands GOTY / GOTY Enhanced).

Port of the air dash from juso's BL2 mod "BL2 Eternal" (glory kills not included).

Behaviour, matching the original:
- Press the dash key while in the air and holding a movement direction to dash that way.
- A dash forces 6500 u/s horizontal speed for 0.15 s, then leaves you drifting at 200 u/s.
- Two dashes per air time; the second only once the first has finished.
- Dashes refill once the cooldown (default 1.5 s from the first dash) is over and you've
  touched the ground since dashing. Unlike the original, landing *during* the cooldown counts,
  so jumping again straight away (e.g. with Double Jump) doesn't lose your dashes.

Differences from BL2 Eternal:
- Dash has its own keyboard and controller keybinds (default: the sprint key/button). The
  controller bind is captured by the mod itself, as BL1's PC keybind screen ignores pads.
- BL2's dash sound and screen particle don't exist in BL1. Instead there's an optional camera
  shake using BL1's sprint camera animation.
- Ticking uses PlayerTick hooks instead of the coroutines library.

Adapted from the dash in juso's "BL2 Eternal" (https://github.com/juso40/bl2sdk-mods), which is
under the following license:

    MIT License

    Copyright (c) 2025

    Permission is hereby granted, free of charge, to any person obtaining a copy
    of this software and associated documentation files (the "Software"), to deal
    in the Software without restriction, including without limitation the rights
    to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the Software is
    furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in all
    copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
    SOFTWARE.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import TYPE_CHECKING, Any

import time

import unrealsdk
from mods_base import (
    BoolOption,
    EInputEvent,
    SpinnerOption,
    ObjectFlags,
    get_pc,
    hook,
    keybind,
)
from ui_utils import OptionBox, OptionBoxButton
from unrealsdk import logging
from unrealsdk.hooks import Block, Type
from unrealsdk.unreal import WeakPointer

if TYPE_CHECKING:
    from unrealsdk.unreal import BoundFunction, UObject, WrappedStruct

EPhysics = unrealsdk.find_enum("EPhysics")

# Tuning values from BL2 Eternal.
DASH_SPEED = 6500.0
DASH_DURATION = 0.15
DASH_EXIT_SPEED = 200.0
DASH_EXIT_Z = -10.0
MAX_DASHES = 2

# ---------------------------------------------------------------------------------------------
# Options
# ---------------------------------------------------------------------------------------------

# Spinners rather than decimal sliders: the mod menu sometimes shows decimal slider values with
# extra digits (0.2 as 0.200).
COOLDOWN_CHOICES = {
    "0 s": 0.0,
    "0.25 s": 0.25,
    "0.5 s": 0.5,
    "0.75 s": 0.75,
    "1.0 s": 1.0,
    "1.25 s": 1.25,
    "1.5 s": 1.5,
    "2.0 s": 2.0,
    "2.5 s": 2.5,
    "3.0 s": 3.0,
}
COOLDOWN = SpinnerOption(
    "Dash Cooldown Time",
    "1.5 s",
    list(COOLDOWN_CHOICES),
    display_name="Dash Cooldown",
    description=(
        "Time after your first dash before your dashes can refill. You also need to have"
        " touched the ground since dashing. Default 1.5 s (same as BL2 Eternal)."
    ),
)
CAMERA_SHAKE = BoolOption(
    "Dash Camera Shake",
    True,
    description="Play a short camera shake (the sprint camera animation) when dashing.",
)
CAMERA_SHAKE_LEVELS = {
    "Very Low": 0.1,
    "Low": 0.2,
    "Medium": 0.35,
    "High": 0.5,
}
CAMERA_SHAKE_STRENGTH = SpinnerOption(
    "Camera Shake Level",
    "Very Low",
    list(CAMERA_SHAKE_LEVELS),
    display_name="Camera Shake Strength",
    description="How strong the dash camera shake is. Higher can be disorienting. Default Very Low.",
)

# ---------------------------------------------------------------------------------------------
# Dash state
# ---------------------------------------------------------------------------------------------


@dataclass
class DashState:
    dashes_used: int = 0
    cooldown_end: float = 0.0
    dash_end: float = 0.0
    active: bool = False
    landed: bool = False
    dir_x: float = 0.0
    dir_y: float = 0.0


_states: dict[str, DashState] = {}


def _state(pawn: UObject) -> DashState:
    key: str = pawn._path_name()  # pyright: ignore[reportPrivateUsage]
    if (state := _states.get(key)) is None:
        state = _states[key] = DashState()
    return state


def _set_velocity(pawn: UObject, x: float, y: float, z: float) -> None:
    velocity = pawn.Velocity
    velocity.X = x
    velocity.Y = y
    velocity.Z = z


# ---------------------------------------------------------------------------------------------
# Dash effects
# ---------------------------------------------------------------------------------------------

CAMERA_ANIM_PATH = "weap_camera_animations.Sprint"

_effect_objects: dict[str, WeakPointer] = {}


def _effect_object(cls: str, path: str) -> UObject | None:
    """Finds an effect asset, and keeps it loaded so it also works on maps that don't load it."""
    if (ptr := _effect_objects.get(path)) is not None and (obj := ptr()) is not None:
        return obj
    try:
        obj = unrealsdk.find_object(cls, path)
    except ValueError:
        return None
    obj.ObjectFlags |= ObjectFlags.KEEP_ALIVE
    _effect_objects[path] = WeakPointer(obj)
    return obj


def _play_dash_effects(pc: UObject) -> None:
    if CAMERA_SHAKE.value and (anim := _effect_object("CameraAnim", CAMERA_ANIM_PATH)):
        try:
            # Optional params default to 0 in UnrealScript, so pass them all.
            # (AnimToPlay, Scale, Rate, BlendInTime, BlendOutTime, bLoop, bRandomStartTime)
            pc.PlayCameraAnim(
                anim,
                CAMERA_SHAKE_LEVELS.get(CAMERA_SHAKE_STRENGTH.value, 0.1),
                1.0,
                0.05,
                0.2,
                False,
                False,
            )
        except Exception as ex:  # noqa: BLE001
            logging.warning(f"[Double Jump Dash] camera shake failed: {ex}")


def try_dash() -> None:
    pc = get_pc(possibly_loading=True)
    if pc is None or (pawn := pc.Pawn) is None:
        return
    if pc.WorldInfo.Pauser is not None:
        return
    if pawn.Physics != EPhysics.PHYS_Falling:
        # Only dash in the air.
        return

    x: float = pawn.Acceleration.X
    y: float = pawn.Acceleration.Y
    mag = sqrt(x * x + y * y)
    if mag == 0:
        # No directional input, so no dash.
        return

    state = _state(pawn)
    now: float = pawn.WorldInfo.TimeSeconds

    if state.dashes_used == 0:
        state.cooldown_end = now + COOLDOWN_CHOICES.get(COOLDOWN.value, 1.5)
        state.landed = False
    elif state.dashes_used >= MAX_DASHES or state.active:
        return

    state.dashes_used += 1
    state.active = True
    state.dash_end = now + DASH_DURATION
    state.dir_x = x / mag * DASH_SPEED
    state.dir_y = y / mag * DASH_SPEED
    _set_velocity(pawn, state.dir_x, state.dir_y, 0)
    _play_dash_effects(pc)


# ---------------------------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------------------------


# Two separate binds so keyboard and controller can both be used. BL1's key names are case
# sensitive, e.g. L3 is "XboxTypeS_LeftThumbstick" (lowercase "stick").
@keybind(
    "Air Dash (Keyboard)",
    "LeftShift",
    description=(
        "Key that dashes while in the air. Default Left Shift, the sprint key, like BL2 Eternal."
    ),
)
def dash_key() -> None:
    try_dash()


@keybind(
    "Air Dash (Controller)",
    "XboxTypeS_LeftThumbstick",
    description=(
        "Controller button that dashes while in the air. Default L3 (left stick click), the"
        " sprint button. To change it, select this and press the button you want when the"
        " popup appears (any button except A and B)."
    ),
)
def dash_button() -> None:
    try_dash()


# ---------------------------------------------------------------------------------------------
# Controller rebinding
# ---------------------------------------------------------------------------------------------
# BL1's keybind screen only accepts keyboard/mouse keys. When the controller bind is selected
# we skip the game's "press a key" prompt and capture the next controller button ourselves,
# then hand it to the mod menu exactly as a normal rebind would.

CONTROLLER_KEY_PREFIXES = ("XboxTypeS_", "Gamepad", "Joystick")
CAPTURE_TIMEOUT = 10.0

# Friendly names for the keybinds screen, which can't name controller buttons itself.
CONTROLLER_KEY_NAMES = {
    "XboxTypeS_A": "A",
    "XboxTypeS_B": "B",
    "XboxTypeS_X": "X",
    "XboxTypeS_Y": "Y",
    "XboxTypeS_LeftShoulder": "LB",
    "XboxTypeS_RightShoulder": "RB",
    "XboxTypeS_LeftTrigger": "LT",
    "XboxTypeS_RightTrigger": "RT",
    "XboxTypeS_LeftThumbstick": "L3",
    "XboxTypeS_RightThumbstick": "R3",
    "XboxTypeS_DPad_Up": "D-Pad Up",
    "XboxTypeS_DPad_Down": "D-Pad Down",
    "XboxTypeS_DPad_Left": "D-Pad Left",
    "XboxTypeS_DPad_Right": "D-Pad Right",
    "XboxTypeS_Back": "Back",
    "XboxTypeS_Start": "Start",
}

# (keybinds frame, row index, populator, start time) while waiting for a button.
_capture: tuple[UObject, int, Any, float] | None = None


def _is_controller_key(key: str) -> bool:
    return key.startswith(CONTROLLER_KEY_PREFIXES)


def _field(args: WrappedStruct, *names: str) -> Any:
    for name in names:
        try:
            return getattr(args, name)
        except (AttributeError, ValueError):
            continue
    return None


@hook("WillowGame.WillowGFxMenuScreenFrameKeyBinds:DoBind", Type.PRE, immediately_enable=True)
def keybind_row_selected(
    obj: UObject,
    _args: WrappedStruct,
    _ret: Any,
    _func: BoundFunction,
) -> type[Block] | None:
    global _capture
    try:
        from willow1_mod_menu.options import populator_stack  # noqa: PLC0415

        idx: int = obj.Selection.Current
        populator = populator_stack[-1]
        option = populator.drawn_keybinds[idx]
    except Exception:  # noqa: BLE001 - mod menu internals changed, use the normal bind
        return None
    if option is None or option.identifier != dash_button.identifier:
        return None
    if time.monotonic() - _last_capture_time < REOPEN_GUARD:
        # The release of the button just bound leaked through to the menu - ignore it.
        return Block

    _capture = (obj, idx, populator, time.monotonic())
    _show_capture_popup(option.value)
    return Block


CANCEL_BUTTON = OptionBoxButton("Cancel")
# Ignore key releases this soon after the popup opens - they belong to the press that opened it.
POPUP_RELEASE_GRACE = 0.5
_capture_box: OptionBox | None = None
_popup_opened = 0.0
# After binding on a press, the popup is gone, so that button's release would fall through to the
# keybinds menu underneath and select the row again. Swallow it there instead.
SWALLOW_RELEASE_TIMEOUT = 2.0
REOPEN_GUARD = 0.3
# Buttons the popup itself uses (A = select the Cancel button, B = cancel), so they can't be bound.
POPUP_NAV_KEYS = ("XboxTypeS_A", "XboxTypeS_B")
_swallow_release: tuple[str, float] | None = None
_last_capture_time = -1.0


def _close_capture_popup() -> None:
    global _capture_box
    box, _capture_box = _capture_box, None
    if box is not None and box.is_showing():
        box.hide()


def _popup_closed(*_: Any) -> None:
    # Cancel button, Escape, or closed some other way.
    global _capture, _capture_box
    _capture = None
    _capture_box = None


def _popup_input(_box: OptionBox, key: str, event: EInputEvent) -> type[Block] | None:
    key = str(key)
    if event == EInputEvent.IE_Released and time.monotonic() - _popup_opened < POPUP_RELEASE_GRACE:
        return Block
    if not _is_controller_key(key):
        # Leave keyboard/mouse to the popup itself (Escape / Enter on Cancel).
        return None
    if key in POPUP_NAV_KEYS:
        if event == EInputEvent.IE_Pressed:
            # Let the popup close itself, but keep this button's release away from the keybinds
            # menu underneath, or it would select the row and reopen the popup.
            _guard_menu_after_popup(key)
        return None
    if event == EInputEvent.IE_Pressed:
        _try_capture(key, event)
    # Don't let other controller input reach the popup.
    return Block


def _guard_menu_after_popup(key: str) -> None:
    global _swallow_release, _last_capture_time
    _swallow_release = (key, time.monotonic())
    _last_capture_time = time.monotonic()


def _show_capture_popup(current: str | None) -> None:
    global _capture_box, _popup_opened
    current_name = "None" if current is None else CONTROLLER_KEY_NAMES.get(current, current)
    box = OptionBox(
        title="Air Dash (Controller)",
        message=(
            "Press the controller button you want to use for Air Dash.\n"
            "Press the current button again to clear it.\n"
            "A and B can't be used, as they control this popup.\n\n"
            f"Current button: {current_name}"
        ),
        tooltip=OptionBox.create_tooltip_string(enter_message="Cancel", esc_message="Cancel"),
        buttons=[CANCEL_BUTTON],
        on_select=_popup_closed,
        on_cancel=_popup_closed,
        on_input=_popup_input,
    )
    try:
        box.show()
    except Exception as ex:  # noqa: BLE001 - still works without the popup, just silently
        logging.warning(f"[Double Jump Dash] couldn't show rebind popup: {ex}")
        return
    _capture_box = box
    _popup_opened = time.monotonic()


@hook("WillowGame.WillowGFxMenuScreenFrameKeyBinds:Screen_Deactivate", immediately_enable=True)
def keybind_screen_closed(*_: Any) -> None:
    global _capture
    _capture = None
    _close_capture_popup()


def _try_capture(key: str | None, event: Any) -> bool:
    """Returns True if the input was used as the new controller binding."""
    global _capture, _swallow_release, _last_capture_time
    if _capture is None or key is None or event != EInputEvent.IE_Pressed:
        return False
    key = str(key)
    frame, idx, populator, started = _capture

    if _capture_box is None and time.monotonic() - started > CAPTURE_TIMEOUT:
        # Only time out when there's no popup (fallback mode).
        _capture = None
        return False
    if not _is_controller_key(key):
        if _capture_box is not None:
            # Popup handles keyboard/mouse itself.
            return False
        # Fallback mode: keyboard/mouse press cancels (e.g. Escape).
        _capture = None
        return False

    _capture = None
    _close_capture_popup()
    _swallow_release = (key, time.monotonic())
    _last_capture_time = time.monotonic()
    try:
        # Same as a normal rebind: pressing the currently bound button clears it.
        populator.on_bind_key(frame, idx, key)
        frame.ApplyPageContent()
    except Exception as ex:  # noqa: BLE001
        logging.warning(f"[Double Jump Dash] couldn't rebind controller button: {ex}")
        return True
    return True


def _swallow(key: Any, event: Any) -> bool:
    """True if this is the release of the button that was just bound."""
    global _swallow_release
    if _swallow_release is None or key is None:
        return False
    swallow_key, since = _swallow_release
    if time.monotonic() - since > SWALLOW_RELEASE_TIMEOUT:
        _swallow_release = None
        return False
    if str(key) != swallow_key:
        return False
    if event == EInputEvent.IE_Released:
        _swallow_release = None
    return True


# Menu screens get controller input through their HandleInputKey, not WillowUIInteraction.
# Hook every level that might implement it; the first one to see the press consumes it.
HANDLE_INPUT_FUNCS = (
    "WillowGame.WillowGFxMenuScreenFrameKeyBinds:HandleInputKey",
    "WillowGame.WillowGFxMenuScreen:HandleInputKey",
    "WillowGame.WillowGFxMenu:HandleInputKey",
    "WillowGame.WillowGFxMovie:HandleInputKey",
    "GearboxFramework.GearboxGFxMovie:HandleInputKey",
)


def _menu_input(
    _obj: UObject,
    args: WrappedStruct,
    _ret: Any,
    _func: BoundFunction,
) -> tuple[type[Block], bool] | None:
    key = _field(args, "ukey", "Key")
    event = _field(args, "uevent", "Event")
    if _swallow(key, event):
        return Block, True
    if _capture is None:
        return None
    if _try_capture(key, event):
        return Block, True
    return None


_menu = _menu_input
for _name in HANDLE_INPUT_FUNCS:
    _menu = hook(_name, Type.PRE, immediately_enable=True)(_menu)
menu_input_hooks = _menu
del _menu, _name


@hook("WillowGame.WillowUIInteraction:InputKey", Type.PRE, immediately_enable=True)
def capture_controller_key(
    _obj: UObject,
    args: WrappedStruct,
    _ret: Any,
    _func: BoundFunction,
) -> type[Block] | None:
    if _swallow(args.Key, args.Event):
        return Block
    if _capture is not None and _try_capture(args.Key, args.Event):
        return Block
    return None


@hook(
    "WillowGame.WillowGFxMenuScreenFrameKeyBinds:LocalizeKeyName",
    Type.PRE,
    immediately_enable=True,
)
def controller_key_name(
    _obj: UObject,
    args: WrappedStruct,
    _ret: Any,
    _func: BoundFunction,
) -> tuple[type[Block], str] | None:
    key = str(args.Key)
    if not _is_controller_key(key):
        return None
    return Block, CONTROLLER_KEY_NAMES.get(key, key.removeprefix("XboxTypeS_"))


# ---------------------------------------------------------------------------------------------
# Per-frame update
# ---------------------------------------------------------------------------------------------

# Every class level that might implement PlayerTick. Several may fire per frame when overrides
# call super; the update is time-based, so running it more than once per frame is harmless.
PLAYER_TICK_FUNCS = (
    "WillowGame.WillowPlayerController:PlayerTick",
    "GearboxFramework.GearboxPlayerController:PlayerTick",
    "GameFramework.GamePlayerController:PlayerTick",
    "Engine.PlayerController:PlayerTick",
)


def _player_tick(pc: UObject, *_: Any) -> None:
    if (pawn := pc.Pawn) is None:
        return
    key: str = pawn._path_name()  # pyright: ignore[reportPrivateUsage]
    if (state := _states.get(key)) is None:
        return
    now: float = pawn.WorldInfo.TimeSeconds

    if state.active:
        if now < state.dash_end:
            _set_velocity(pawn, state.dir_x, state.dir_y, 0)
        else:
            # Dash over - keep a little momentum in the direction we ended up moving.
            state.active = False
            vx: float = pawn.Velocity.X
            vy: float = pawn.Velocity.Y
            mag = sqrt(vx * vx + vy * vy)
            if mag > 0:
                _set_velocity(
                    pawn,
                    vx / mag * DASH_EXIT_SPEED,
                    vy / mag * DASH_EXIT_SPEED,
                    DASH_EXIT_Z,
                )

    if not state.dashes_used:
        return
    on_ground = pawn.Physics != EPhysics.PHYS_Falling
    if on_ground:
        state.landed = True
    if not state.active and now >= state.cooldown_end and state.landed:
        state.dashes_used = 0


_tick = _player_tick
for _name in PLAYER_TICK_FUNCS:
    _tick = hook(_name, Type.PRE)(_tick)
player_tick_hooks = _tick
del _tick, _name


# ---------------------------------------------------------------------------------------------
# Enable / disable
# ---------------------------------------------------------------------------------------------


def enable() -> None:
    _states.clear()


def disable() -> None:
    _states.clear()


OPTIONS = [COOLDOWN, CAMERA_SHAKE, CAMERA_SHAKE_STRENGTH]
KEYBINDS = [dash_key, dash_button]
HOOKS = [player_tick_hooks]
