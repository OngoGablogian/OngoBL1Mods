import re
import time
from typing import Any

import unrealsdk
from mods_base import (
    BoolOption,
    ButtonOption,
    Game,
    SliderOption,
    build_mod,
    get_pc,
)
from mods_base import hook as mods_hook
from unrealsdk import logging
from unrealsdk.hooks import Type, add_hook, remove_hook
from unrealsdk.unreal import BoundFunction, UObject, WrappedStruct

__version_info__: tuple[int, int, int] = (1, 0, 1)
__version__: str = "1.0.1"
__author__: str = "Ongo"


def log(msg: str) -> None:
    logging.info(f"[Weapon Volume BL1E] {msg}")


# Everything the debug features find is kept in this buffer, so the whole thing can be printed to the
# console (and so into `unrealsdk.log`) in one go.
report: list[str] = []


def note(msg: str, to_console: bool = False) -> None:
    report.append(msg)
    if to_console:
        log(msg)



_errors_seen: set[str] = set()


def log_error_once(where: str, ex: BaseException) -> None:
    key = f"{where}:{type(ex).__name__}:{ex}"
    if key in _errors_seen or len(_errors_seen) > 50:
        return
    _errors_seen.add(key)
    log(f"ERROR in {where}: {type(ex).__name__}: {ex}")


# --------------------------------------------------------------------------------------------------
# Options
# --------------------------------------------------------------------------------------------------


def _slider(name: str, default: int, description: str = "") -> SliderOption:
    return SliderOption(
        name,
        default,
        0,
        100,
        5,
        True,
        description=description or f"Volume of {name.lower()} sounds, as a percentage of stock.",
    )


opt_master = _slider("Master Gun Volume", 100, "Applied on top of every per-type slider below.")
opt_pistol = _slider("Pistols / Revolvers", 100)
opt_smg = _slider("SMGs", 100)
opt_shotgun = _slider("Shotguns", 100)
opt_rifle = _slider("Assault Rifles", 100)
opt_sniper = _slider("Sniper Rifles", 100)
opt_launcher = _slider("Rocket Launchers", 100)
opt_grenade = _slider(
    "Grenades",
    100,
    "Volume of grenade bounce and explosion sounds. Not affected by the master slider.",
)
opt_shock = _slider(
    "Shock Effects",
    100,
    "Volume of shock explosion and electrocution sounds. Does not change the firing zap of some shock weapons. Not affected by the master slider.",
)

opt_own_only = BoolOption(
    "Only My Weapons",
    False,
    "Yes",
    "No",
    description="If enabled, enemy and NPC weapons are left at stock volume.",
)
opt_handling = BoolOption(
    "Affect Reload / Handling Sounds",
    False,
    "Yes",
    "No",
    description=(
        "If disabled, only firing sounds are scaled; reload, equip and similar sounds stay at"
        " stock volume."
    ),
)

# --------------------------------------------------------------------------------------------------
# Weapon classification
# --------------------------------------------------------------------------------------------------

# Checked in order, first match wins. Matched against the lowercase text of the weapon type
# definition's path and its WeaponType enum value. "sniper" has to come before "rifle".
TYPE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("sniper", ("sniper",)),
    ("launcher", ("launcher", "rocket")),
    ("smg", ("smg", "submachine", "sub_machine")),
    ("shotgun", ("shotgun",)),
    ("rifle", ("rifle", "assault", "combat")),
    ("pistol", ("pistol", "revolver")),
)

TYPE_OPTIONS: dict[str, SliderOption] = {
    "pistol": opt_pistol,
    "smg": opt_smg,
    "shotgun": opt_shotgun,
    "rifle": opt_rifle,
    "sniper": opt_sniper,
    "launcher": opt_launcher,
}

HANDLING_WORDS: tuple[str, ...] = (
    "reload",
    "equip",
    "unequip",
    "swap",
    "putaway",
    "foley",
    "dry_fire",
)
# Pawns play lots of non-gun sounds (footsteps, pickups...), so when a sound comes from the pawn
# rather than the weapon itself, only scale it if it's one of the weapon sound cues. These all live
# in packages like `Wep_Sub_Machine_Gun.Weapon_Fire.Wep_SMG_Long_Cue`.


def looks_like_weapon_cue(cue_lower: str) -> bool:
    return cue_lower.startswith("wep_") or ".weapon_fire." in cue_lower


original_volumes: dict[str, float] = {}
type_cache: dict[str, str | None] = {}
applied_logged: set[tuple[str, str]] = set()
pawn_has_weapon_attr: dict[str, bool] = {}

_weapon_class: Any = None


def is_weapon(obj: UObject) -> bool:
    global _weapon_class  # noqa: PLW0603
    if _weapon_class is None:
        _weapon_class = unrealsdk.find_class("WillowWeapon")
    return obj.Class._inherits(_weapon_class)


# Weapon sound cue packages -> weapon type. A sound's own package name is the most reliable way to
# tell what kind of gun it belongs to (e.g. the player's weapon can already have changed by the time
# an unequip sound plays).
CUE_PREFIX_TYPES: tuple[tuple[str, str], ...] = (
    ("wep_sub_machine_gun", "smg"),
    ("wep_revolver", "pistol"),
    ("wep_repeater_pistol", "pistol"),
    ("wep_pistol", "pistol"),
    ("wep_shotgun", "shotgun"),
    ("wep_assault_rifle", "rifle"),
    ("wep_sniper_rifle", "sniper"),
    ("wep_rocket_launcher", "launcher"),
)


def classify_cue(cue_lower: str) -> str | None:
    for prefix, weapon_type in CUE_PREFIX_TYPES:
        if cue_lower.startswith(prefix):
            return weapon_type
    return None


def match_keywords(text: str) -> str | None:
    for weapon_type, words in TYPE_KEYWORDS:
        if any(word in text for word in words):
            return weapon_type
    return None


def classify_weapon(weapon: UObject) -> str | None:
    """Returns one of the keys of TYPE_OPTIONS for this weapon, or None if unknown."""
    try:
        definition_data = weapon.DefinitionData
    except (AttributeError, ValueError):
        return None

    # Try the weapon type definition first, then fall back to other definitions which also carry
    # the weapon's type in their names (e.g. `gd_weap_sniper_rifle.Body.body4`)
    for field in ("WeaponTypeDefinition", "BalanceDefinition", "BodyPartDefinition"):
        try:
            definition = getattr(definition_data, field)
        except (AttributeError, ValueError):
            continue
        if definition is None:
            continue

        key = definition._path_name()
        if key not in type_cache:
            type_cache[key] = match_keywords(key.lower())
        if type_cache[key] is not None:
            return type_cache[key]
    return None


def is_local_players_weapon(weapon: UObject) -> bool:
    try:
        pawn = get_pc().Pawn
        return pawn is not None and weapon.Instigator == pawn
    except (AttributeError, ValueError):
        return False


def resolve_weapon(obj: UObject) -> tuple[UObject | None, bool]:
    """
    Works out which weapon a sound belongs to.

    Returns:
        The weapon (or None), and whether the sound came from the pawn holding it rather than the
        weapon itself.
    """
    if is_weapon(obj):
        return obj, False

    class_name = obj.Class.Name
    if pawn_has_weapon_attr.get(class_name) is False:
        return None, False
    try:
        weapon = obj.Weapon
    except (AttributeError, ValueError):
        pawn_has_weapon_attr[class_name] = False
        return None, False
    pawn_has_weapon_attr[class_name] = True
    if weapon is not None and is_weapon(weapon):
        return weapon, True
    return None, False


# --------------------------------------------------------------------------------------------------
# Main hook
# --------------------------------------------------------------------------------------------------


# Words which mark a sound cue as being the shock (electric) effect
SHOCK_WORDS: tuple[str, ...] = (
    "shock", "electr", "zap", "tesla", "lightning", "_emp_", "_emp.", ".emp_", "elec_",
)
# Sounds from these packages may be shock effects. Weapons, impacts and elemental effects only,
# so that ambient scenery (e.g. electric fences) is left alone
SHOCK_PACKAGES: tuple[str, ...] = ("wep_", "efx_", "elemental", "weapon", "gore_")


def is_grenade_cue(cue_lower: str) -> bool:
    return cue_lower.startswith("wep_grenade")


def is_shock_cue(cue_lower: str) -> bool:
    if not any(word in cue_lower for word in SHOCK_WORDS):
        return False
    return any(pkg in cue_lower for pkg in SHOCK_PACKAGES)


def effect_for_cue(cue_lower: str) -> tuple[str, SliderOption] | None:
    """Returns the label and slider for sounds which have a slider of their own, if this is one."""
    if is_grenade_cue(cue_lower):
        return "grenade", opt_grenade
    if is_shock_cue(cue_lower):
        return "shock", opt_shock
    return None


def scale_effect_cue(cue: UObject, cue_path: str, label: str, option: SliderOption) -> None:
    """Applies an effect's slider to its sound cue, relative to the cue's original volume."""
    if cue_path not in original_volumes:
        original_volumes[cue_path] = cue.VolumeMultiplier
    scale = option.value / 100
    cue.VolumeMultiplier = original_volumes[cue_path] * scale
    if (label, cue_path) not in applied_logged and len(applied_logged) < 200:
        applied_logged.add((label, cue_path))
        note(f"scaling {label} sound {cue_path} by {scale:.2f}", to_console=True)


last_shock_scan = 0.0


def scale_all_shock_cues(force: bool = False) -> None:
    """
    Scales every loaded shock cue up front.

    Some shock sounds are started by the engine itself (e.g. from particle effects) and never go
    through the script functions we hook, so we also set their volume ahead of time. New cues are
    picked up by rescanning at most every few seconds.
    """
    global last_shock_scan  # noqa: PLW0603
    now = time.monotonic()
    if not force and now - last_shock_scan < 5:
        return
    last_shock_scan = now
    try:
        for cue in unrealsdk.find_all("SoundCue", exact=False):
            cue_path = cue._path_name()
            cue_lower = cue_path.lower()
            if is_shock_cue(cue_lower) and not is_grenade_cue(cue_lower):
                scale_effect_cue(cue, cue_path, "shock", opt_shock)
    except Exception as ex:  # noqa: BLE001
        log_error_once("scale_all_shock_cues", ex)


def scale_effect_component(component: UObject) -> None:
    try:
        scale_all_shock_cues()
        cue = component.SoundCue
        if cue is None:
            return
        cue_path = cue._path_name()
        effect = effect_for_cue(cue_path.lower())
        if effect is not None:
            scale_effect_cue(cue, cue_path, *effect)
    except Exception as ex:  # noqa: BLE001
        log_error_once("scale_effect_component", ex)


@mods_hook("Engine.AudioComponent:Play")
def audio_component_play(
    obj: UObject,
    _args: WrappedStruct,
    _ret: Any,
    _func: BoundFunction,
) -> None:
    scale_effect_component(obj)


@mods_hook("Engine.AudioComponent:FadeIn")
def audio_component_fade_in(
    obj: UObject,
    _args: WrappedStruct,
    _ret: Any,
    _func: BoundFunction,
) -> None:
    scale_effect_component(obj)


@mods_hook("Engine.Actor:PlaySound")
def play_sound(
    obj: UObject,
    args: WrappedStruct,
    _ret: Any,
    _func: BoundFunction,
) -> None:
    try:
        scale_all_shock_cues()
        cue = args.InSoundCue
        if cue is None:
            return

        cue_path = cue._path_name()
        cue_lower = cue_path.lower()
        effect = effect_for_cue(cue_lower)
        if effect is not None:
            scale_effect_cue(cue, cue_path, *effect)
            return

        weapon, from_pawn = resolve_weapon(obj)
        if weapon is None:
            return

        if from_pawn and not looks_like_weapon_cue(cue_lower):
            return

        weapon_type = classify_cue(cue_lower) or classify_weapon(weapon)
        if weapon_type is None:
            return
        if opt_own_only.value and not is_local_players_weapon(weapon):
            return

        if not opt_handling.value and any(word in cue_lower for word in HANDLING_WORDS):
            scale = 1.0
        else:
            scale = (opt_master.value / 100) * (TYPE_OPTIONS[weapon_type].value / 100)

        if cue_path not in original_volumes:
            original_volumes[cue_path] = cue.VolumeMultiplier
        cue.VolumeMultiplier = original_volumes[cue_path] * scale

        if (weapon_type, cue_path) not in applied_logged and len(applied_logged) < 200:
            applied_logged.add((weapon_type, cue_path))
            note(f"scaling {weapon_type} sound {cue_path} by {scale:.2f}", to_console=True)
    except Exception as ex:  # noqa: BLE001
        log_error_once("play_sound", ex)


def scale_effect_args(args: WrappedStruct) -> None:
    try:
        scale_all_shock_cues()
        for cue in sound_cues_in(args):
            cue_path = cue._path_name()
            effect = effect_for_cue(cue_path.lower())
            if effect is not None:
                scale_effect_cue(cue, cue_path, *effect)
    except Exception as ex:  # noqa: BLE001
        log_error_once("scale_effect_args", ex)


@mods_hook("Engine.Actor:CreateAudioComponent")
def create_audio_component(
    _obj: UObject,
    args: WrappedStruct,
    _ret: Any,
    _func: BoundFunction,
) -> None:
    scale_effect_args(args)


@mods_hook("Engine.Weapon:WeaponPlaySound")
def weapon_play_sound(
    _obj: UObject,
    args: WrappedStruct,
    _ret: Any,
    _func: BoundFunction,
) -> None:
    scale_effect_args(args)



# --------------------------------------------------------------------------------------------------
# Debugging aids
# --------------------------------------------------------------------------------------------------

# Candidate functions which might be involved in playing gun sounds. When debug logging is on, we
# record every distinct (function, object class, sound) we see, so we can find out what Enhanced
# actually uses.
PROBE_FUNCTIONS: tuple[str, ...] = (
    "Engine.Actor:PlaySound",
    "Engine.Actor:CreateAudioComponent",
    "Engine.Pawn:WeaponFired",
    "Engine.Weapon:PlayFiringSound",
    "Engine.Weapon:WeaponPlaySound",
    "WillowGame.WillowWeapon:PlayFiringSound",
    "Engine.AudioComponent:Play",
    "Engine.AudioComponent:FadeIn",
)
PROBE_IDENTIFIER = "gun_volume_probe"
probe_seen: set[tuple[str, str, str]] = set()
probe_counts: dict[str, int] = {}
active_probes: list[str] = []


NOISE_WORDS: tuple[str, ...] = (
    "ui_", "user_interface", "footstep", "foley", "pickup", "vo_", "ambient", "amb_", "portal",
    "interface", "casing", "mission", "item_interaction", "player_notifications", "music",
)


def sound_cues_in(args: WrappedStruct) -> list[UObject]:
    """Finds every SoundCue passed as an argument, whatever the argument is called."""
    cues: list[UObject] = []
    try:
        for field in args._type._fields():  # type: ignore[attr-defined]
            value = getattr(args, field.Name, None)
            if value is not None and hasattr(value, "_path_name") and value.Class.Name == "SoundCue":
                cues.append(value)
    except Exception:  # noqa: BLE001
        try:
            cue = args.InSoundCue
            if cue is not None:
                cues.append(cue)
        except (AttributeError, ValueError):
            pass
    return cues


def make_probe(path: str):  # noqa: ANN202
    def probe(obj: UObject, args: WrappedStruct, _ret: Any, _func: BoundFunction) -> None:
        probe_counts[path] = probe_counts.get(path, 0) + 1
        if len(probe_seen) > 700:
            return
        try:
            holder = "-"
            weapon, _ = resolve_weapon(obj)
            if weapon is not None:
                holder = f"{weapon.Class.Name}/{classify_weapon(weapon)}"

            cue_texts = [c._path_name() for c in sound_cues_in(args)]
            if not cue_texts:
                try:
                    cue_texts = [obj.SoundCue._path_name()]
                except (AttributeError, ValueError):
                    cue_texts = ["-"]

            for cue_text in cue_texts:
                lowered = cue_text.lower()
                if any(word in lowered for word in NOISE_WORDS):
                    continue
                key = (path, obj.Class.Name, cue_text)
                if key in probe_seen:
                    continue
                probe_seen.add(key)
                note(f"probe {path} on {obj.Class.Name} (weapon: {holder}) sound: {cue_text}")
        except Exception as ex:  # noqa: BLE001
            log_error_once(f"probe {path}", ex)

    return probe


def set_probes(enabled: bool) -> None:
    for path in active_probes:
        remove_hook(path, Type.PRE, PROBE_IDENTIFIER)
    active_probes.clear()

    if not enabled:
        return
    for path in PROBE_FUNCTIONS:
        try:
            add_hook(path, Type.PRE, PROBE_IDENTIFIER, make_probe(path))
            active_probes.append(path)
        except Exception as ex:  # noqa: BLE001
            note(f"could not probe {path}: {ex}")
    log(
        f"debug logging on - watching {len(active_probes)} functions. Fire some weapons, then press"
        f" 'Debug: Print Full Report'.",
    )


opt_debug = BoolOption(
    "Log Weapon Sounds",
    False,
    "Yes",
    "No",
    description=(
        "Debug: records which functions/sounds are used when weapons make noise. Turn on, fire a"
        " few different weapons, then press 'Debug: Print Full Report'. The report goes to the"
        " console and unrealsdk.log."
    ),
    on_change_while_enabled=lambda _opt, value: set_probes(value),
)

SOUNDISH = re.compile(r"sound|audio|snd|fmod|fire|shot|sfx|noise|volume", re.IGNORECASE)
DEFINITION_FIELDS: tuple[str, ...] = (
    "WeaponTypeDefinition",
    "BalanceDefinition",
    "ManufacturerDefinition",
    "BodyPartDefinition",
    "GripPartDefinition",
    "BarrelPartDefinition",
    "SightPartDefinition",
    "StockPartDefinition",
    "ElementalPartDefinition",
    "Accessory1PartDefinition",
    "Accessory2PartDefinition",
    "MaterialPartDefinition",
)


def describe(value: Any) -> str:
    try:
        items = list(value)
    except TypeError:
        items = [value]
    return ", ".join(i._path_name() if hasattr(i, "_path_name") else str(i) for i in items)


def dump_sound_props(label: str, obj: UObject) -> None:
    """Records every sound-ish *property* (not function) on an object, with its value."""
    seen: set[str] = set()
    for field in obj.Class._fields():
        name = field.Name
        if name in seen or not SOUNDISH.search(name):
            continue
        if not field.Class.Name.endswith("Property"):
            continue
        seen.add(name)
        try:
            text = describe(getattr(obj, name))
        except Exception as ex:  # noqa: BLE001
            text = f"<unreadable: {ex}>"
        note(f"{label}.{name} = {text}")


def scan_class(class_name: str) -> None:
    """Records every sound-ish field name on a class, once each."""
    seen: set[str] = set()
    for field in unrealsdk.find_class(class_name)._fields():
        if field.Name in seen or not SOUNDISH.search(field.Name):
            continue
        seen.add(field.Name)
        note(f"scan {class_name}: {field.Name} ({field.Class.Name})")


def build_report() -> None:
    note("---- Weapon Volume BL1E full report ----")
    note(f"version {__version__}, game {Game.get_current().name}")

    for path, count in probe_counts.items():
        note(f"probe totals: {path} called {count} times")
    if not active_probes:
        note("probes are OFF - turn on 'Log Weapon Sounds' and fire weapons for probe data")

    try:
        scan_class("WillowWeapon")
    except Exception as ex:  # noqa: BLE001
        note(f"scan WillowWeapon failed: {ex}")

    try:
        pawn = get_pc().Pawn
        weapon = pawn.Weapon if pawn is not None else None
        if weapon is None:
            note("no weapon held (or not in game), skipping held weapon dump")
            return

        note(f"held weapon {weapon._path_name()} (class {weapon.Class.Name})")
        note(f"detected type: {classify_weapon(weapon)}")
        dump_sound_props("weapon", weapon)

        definition_data = weapon.DefinitionData
        for name in DEFINITION_FIELDS:
            try:
                definition = getattr(definition_data, name)
            except (AttributeError, ValueError):
                continue
            if definition is None:
                continue
            note(f"{name}: {definition._path_name()} (class {definition.Class.Name})")
            if name == "WeaponTypeDefinition":
                note(f"  WeaponType = {getattr(definition, 'WeaponType', '?')}")
            dump_sound_props(f"  {name}", definition)
    except Exception as ex:  # noqa: BLE001
        note(f"held weapon dump failed: {type(ex).__name__}: {ex}")


def print_full_report(_: ButtonOption) -> None:
    """Prints everything gathered so far to the console, which also writes it to unrealsdk.log."""
    try:
        report.append("")  # Separate from any older run
        build_report()
        lines = list(report)
        report.clear()

        for line in lines:
            log(line)
        log(f"---- end of report ({len(lines)} lines) - see unrealsdk.log ----")
    except Exception as ex:  # noqa: BLE001
        log_error_once("print_full_report", ex)


# --------------------------------------------------------------------------------------------------
# Lifecycle
# --------------------------------------------------------------------------------------------------


def restore_stock_volumes() -> None:
    """Puts every SoundCue we touched back to its original VolumeMultiplier."""
    for cue_path, volume in original_volumes.items():
        try:
            unrealsdk.find_object("SoundCue", cue_path).VolumeMultiplier = volume
        except (ValueError, AttributeError):
            pass  # Not loaded any more


def on_enable() -> None:
    log(f"v{__version__} loaded for {Game.get_current().name}")
    set_probes(opt_debug.value)
    scale_all_shock_cues(force=True)


def on_disable() -> None:
    set_probes(False)
    restore_stock_volumes()


def reset_sliders(_: ButtonOption) -> None:
    for option in (opt_master, opt_grenade, opt_shock, *TYPE_OPTIONS.values()):
        option.value = 100


mod = build_mod(
    name="Weapon Volume BL1E",
    author=__author__,
    version=__version__,
    options=[
        opt_master,
        opt_pistol,
        opt_smg,
        opt_shotgun,
        opt_rifle,
        opt_sniper,
        opt_launcher,
        opt_grenade,
        opt_shock,
        opt_own_only,
        opt_handling,
        opt_debug,
        ButtonOption("Debug: Print Full Report", on_press=print_full_report),
        ButtonOption("Reset All To 100%", on_press=reset_sliders),
    ],
    supported_games=Game.BL1E,
    on_enable=on_enable,
    on_disable=on_disable,
)
