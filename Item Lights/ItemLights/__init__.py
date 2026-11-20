# Item Lights (Borderlands GOTY / GOTY Enhanced)
# Port of RedxYeti's Borderlands 2 mod "Item Lights"
# (https://github.com/RedxYeti/bl2-willow2-sdkmods/tree/main/ItemLights).
#
# How it works
# ------------
# Whenever the game spawns the sparkle particles on a pickup lying in the world, a small point
# light is built and attached to it, coloured by the item's rarity. Shadows are turned off on the
# light, since they don't render properly on it and cost a lot of performance.
#
# Quest items are picked out the same way as in Loot Radar. Ones the game is still hiding because
# their mission isn't active are checked about once a second and lit as soon as they appear.
#
# Borderlands 1 doesn't have every function the Borderlands 2 version relies on, so the rarity
# colour and the attachment each try a few ways in turn. The first light made each session writes
# a line to unrealsdk.log saying which ways worked.
from __future__ import annotations

import time
from typing import Any

import unrealsdk
from mods_base import BoolOption, SliderOption, build_mod, hook
from unrealsdk import logging
from unrealsdk.hooks import Type
from unrealsdk.unreal import BoundFunction, UObject, WeakPointer, WrappedStruct

__version__: str
__version_info__: tuple[int, ...]

MOD_NAME = "Item Lights"

# How far above the pickup the light sits.
LIGHT_HEIGHT = 15

# How often hidden quest items are checked to see whether their mission has made them appear, in
# seconds.
QUEST_CHECK_SECONDS = 1.0

# Every class that counts as "weapons and gear". Checked against the whole class hierarchy, so
# subclasses count too. Borderlands 1 calls class mods "command decks" internally.
GEAR_CLASSES = {
    "WillowWeapon",
    "WillowEquipAbleItem",
    "WillowShield",
    "WillowGrenadeMod",
    "WillowClassMod",
    "WillowCommandDeck",
    "WillowArtifact",
}


def log(msg: str) -> None:
    logging.info(f"[{MOD_NAME}] {msg}")


# ---------------------------------------------------------------------------------------------------
# Options
# ---------------------------------------------------------------------------------------------------
def on_option_change(option: Any, value: Any) -> None:
    # The option's value is only updated after this runs, so the new value is passed along.
    # Options can't be dictionary keys, so they're looked up by name.
    refresh_all({option.identifier: value})


weapons_gear_only = BoolOption(
    "Weapons and Gear Only",
    False,
    "On",
    "Off",
    description="With this enabled, only weapons and gear will have lights. Otherwise every item will have a light.",
    on_change_while_enabled=on_option_change,
)

quest_items = BoolOption(
    "Light Quest Items",
    True,
    "On",
    "Off",
    description=(
        "With this enabled, items you need for a mission always have lights, even with Weapons and Gear Only on."
        " Ones that only appear during their mission get a light once they show up."
    ),
    on_change_while_enabled=on_option_change,
)

brightness = SliderOption(
    "Light Brightness",
    5,
    1,
    15,
    1,
    True,
    description="Choose how bright you want the lights.\nDefault Value: 5",
    on_change_while_enabled=on_option_change,
)

radius = SliderOption(
    "Light Radius",
    300,
    10,
    1024,
    10,
    False,
    description="Choose how far you want the light radius to go.\nDefault Value: 300",
    on_change_while_enabled=on_option_change,
)

falloff = SliderOption(
    "Light Falloff",
    40,
    1,
    80,
    1,
    True,
    description=(
        "Choose the falloff of the light radius."
        "\nLower values make the brightness extend to the edges of the light, making the edges sharper."
        "\nDefault Value: 40"
    ),
    on_change_while_enabled=on_option_change,
)


def setting(option: Any, overrides: dict | None) -> Any:
    if overrides and option.identifier in overrides:
        return overrides[option.identifier]
    return option.value


# ---------------------------------------------------------------------------------------------------
# Rarity colour
# ---------------------------------------------------------------------------------------------------
_globals_def: WeakPointer = WeakPointer()
_reported = False
_how: dict[str, str] = {}


def get_globals_def() -> UObject | None:
    global _globals_def
    found = _globals_def()
    if found is not None:
        return found

    try:
        found = (
            unrealsdk.find_class("WillowGlobals")
            .ClassDefaultObject.GetWillowGlobals()
            .GetGlobalsDefinition()
        )
    except Exception:
        found = None

    if found is None:
        try:
            for obj in unrealsdk.find_all("GlobalsDefinition", exact=False):
                if "Default__" not in str(obj.Name):
                    found = obj
                    break
        except Exception:
            found = None

    if found is not None:
        _globals_def = WeakPointer(found)
    return found


def get_rarity_level(pickup: UObject) -> int | None:
    attempts = (
        ("WillowPickup.InventoryRarityLevel", lambda: pickup.InventoryRarityLevel),
        ("Inventory.RarityLevel", lambda: pickup.Inventory.RarityLevel),
        ("Inventory.GetRarityLevel()", lambda: pickup.Inventory.GetRarityLevel()),
    )
    for name, attempt in attempts:
        try:
            level = attempt()
        except Exception:
            continue
        if isinstance(level, int):
            _how.setdefault("rarity", name)
            return level
    _how.setdefault("rarity", "none found")
    return None


def white() -> WrappedStruct:
    return unrealsdk.make_struct("Color", R=255, G=255, B=255, A=255)


def get_rarity_color(pickup: UObject) -> WrappedStruct:
    level = get_rarity_level(pickup)
    globals_def = get_globals_def()
    if level is None or globals_def is None:
        _how.setdefault("colour", "white (no rarity or globals)")
        return white()

    try:
        colour = globals_def.GetRarityColorForLevel(level)
        _how.setdefault("colour", "GetRarityColorForLevel")
        return colour
    except Exception:
        pass

    try:
        for entry in globals_def.RarityLevelColors:
            if entry.MinLevel <= level <= entry.MaxLevel:
                _how.setdefault("colour", "RarityLevelColors")
                return entry.Color
    except Exception:
        pass

    _how.setdefault("colour", f"white (level {level} not in table)")
    return white()


# ---------------------------------------------------------------------------------------------------
# Lights
# ---------------------------------------------------------------------------------------------------
# Every light this mod has made, with the pickup it sits on, so they can be taken off again.
_lights: list[tuple[WeakPointer, WeakPointer]] = []

# Quest items the game is still keeping hidden, waiting for their mission to show them.
_waiting: list[WeakPointer] = []
_next_quest_check = 0.0


def is_quest_item(pickup: UObject) -> bool:
    """Whether the pickup holds a mission item rather than ordinary loot.

    Mission items share their class with health and ammo, so it's their definition that tells them
    apart: the game flags it with bMissionItem and presents it as a MissionObject. A few DLC ones
    lack the flag but keep the presentation, and all of them live in a mission package such as
    Z0_MissionData.ItemDefs.
    """
    try:
        definition = pickup.Inventory.DefinitionData.ItemDefinition
    except Exception:
        return False
    if definition is None:
        return False

    try:
        if definition.bMissionItem is True:
            return True
    except Exception:
        pass

    try:
        if "missionobject" in str(definition.Presentation).lower():
            return True
    except Exception:
        pass

    path = str(definition).lower()
    package = path.split("'", 1)[-1].split(".", 1)[0]
    return "mission" in package and ".itemdefs." in path


def is_gear(pickup: UObject) -> bool:
    try:
        cls = pickup.Inventory.Class
    except Exception:
        return False
    while cls is not None:
        if str(cls.Name) in GEAR_CLASSES:
            return True
        try:
            cls = cls.SuperField
        except Exception:
            return False
    return False


def is_enabled(pickup: UObject) -> bool:
    try:
        return pickup.Pickupable_IsEnabled() is True
    except Exception:
        pass
    try:
        return pickup.bHidden is not True
    except Exception:
        return True


def has_light(pickup: UObject) -> bool:
    try:
        for component in pickup.Components:
            if component is not None and component.Class.Name == "PointLightComponent":
                return True
    except Exception:
        pass
    return False


def attach(pickup: UObject, light: UObject) -> bool:
    attempts = (
        ("WorldBodyAttachComponent", lambda: pickup.WorldBodyAttachComponent(light)),
        ("AttachComponent", lambda: pickup.AttachComponent(light)),
    )
    for name, attempt in attempts:
        try:
            attempt()
        except Exception:
            continue
        _how.setdefault("attach", name)
        return True
    _how.setdefault("attach", "failed")
    return False


def set_if_present(light: UObject, name: str, value: Any) -> None:
    try:
        setattr(light, name, value)
    except Exception:
        pass


def add_light(pickup: UObject, overrides: dict | None = None) -> None:
    global _reported
    try:
        if pickup is None or pickup.Inventory is None:
            return
        if pickup.bDeleteMe is True:
            return
    except Exception:
        return

    if has_light(pickup):
        return

    if is_quest_item(pickup):
        if not setting(quest_items, overrides):
            return
        if not is_enabled(pickup):
            # Hidden until its mission is active. A light now would give its spot away, so it's
            # checked again every so often and lit once it appears.
            if not any(ptr() == pickup for ptr in _waiting):
                _waiting.append(WeakPointer(pickup))
            return
    else:
        if not is_enabled(pickup):
            return
        if setting(weapons_gear_only, overrides) and not is_gear(pickup):
            return

    try:
        light = unrealsdk.construct_object("PointLightComponent", pickup)
    except Exception as ex:
        log(f"Couldn't make a light: {ex}")
        return

    try:
        light.Brightness = setting(brightness, overrides)
        light.Radius = setting(radius, overrides)
        light.Translation.Z = LIGHT_HEIGHT
        light.LightColor = get_rarity_color(pickup)
    except Exception as ex:
        log(f"Couldn't set up a light: {ex}")
        return

    set_if_present(light, "FalloffExponent", setting(falloff, overrides) / 10)
    # Shadows don't work properly on these and cost a lot of performance.
    for name in ("CastShadows", "CastStaticShadows", "CastDynamicShadows", "bCastCompositeShadow"):
        set_if_present(light, name, False)

    if attach(pickup, light):
        _lights.append((WeakPointer(pickup), WeakPointer(light)))

    if not _reported:
        _reported = True
        log(
            f"First light made. Rarity: {_how.get('rarity')}, colour: {_how.get('colour')}, "
            f"attached with: {_how.get('attach')}"
        )


def remove_all() -> None:
    for pickup_ptr, light_ptr in _lights:
        pickup = pickup_ptr()
        light = light_ptr()
        if pickup is None or light is None:
            continue
        for detach in ("WorldBodyDetachComponent", "DetachComponent"):
            try:
                getattr(pickup, detach)(light)
                break
            except Exception:
                continue
    _lights.clear()
    _waiting.clear()


def check_waiting() -> None:
    """Lights any hidden quest items that their mission has now shown."""
    still_waiting = []
    for ptr in _waiting:
        pickup = ptr()
        if pickup is None:
            continue
        try:
            if pickup.bDeleteMe is True or pickup.Inventory is None:
                continue
        except Exception:
            continue
        if is_enabled(pickup):
            add_light(pickup)
        else:
            still_waiting.append(ptr)
    _waiting[:] = still_waiting


def all_pickups() -> list[UObject]:
    # Mission items are a subclass of WillowPickup, so subclasses are asked for as well.
    try:
        found = unrealsdk.find_all("WillowPickup", exact=False)
    except TypeError:
        found = unrealsdk.find_all("WillowPickup")

    pickups = []
    for pickup in found:
        try:
            if "Default__" in str(pickup.Name):
                continue
        except Exception:
            continue
        pickups.append(pickup)
    return pickups


def light_all(overrides: dict | None = None) -> None:
    for pickup in all_pickups():
        add_light(pickup, overrides)


def refresh_all(overrides: dict | None = None) -> None:
    """Rebuilds every light, so a changed option shows on loot already on the ground."""
    remove_all()
    light_all(overrides)


# ---------------------------------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------------------------------
@hook("WillowGame.WillowPickup:SpawnPickupParticles", Type.POST)
def on_spawn_particles(obj: UObject, _2: WrappedStruct, _3: Any, _4: BoundFunction) -> None:
    add_light(obj)


@hook("Engine.GameViewportClient:PostRender", Type.POST)
def on_render(_1: UObject, _2: WrappedStruct, _3: Any, _4: BoundFunction) -> None:
    global _next_quest_check
    if not _waiting:
        return
    now = time.monotonic()
    if now < _next_quest_check:
        return
    _next_quest_check = now + QUEST_CHECK_SECONDS
    check_waiting()


def on_enable() -> None:
    # Loot already lying around when the mod is turned on gets lit straight away.
    light_all()


def on_disable() -> None:
    remove_all()


mod = build_mod(
    options=[weapons_gear_only, quest_items, brightness, radius, falloff],
    hooks=[on_spawn_particles, on_render],
    on_enable=on_enable,
    on_disable=on_disable,
)
