"""Pandora's Workshop: live BL1 Enhanced gear editor."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

import unrealsdk
from mods_base import EInputEvent, ObjectFlags, build_mod, get_pc, keybind
from unrealsdk import logging
from unrealsdk.hooks import Block
from unrealsdk.unreal import UObject
from ui_utils import OptionBox, OptionBoxButton

from .name_parts import NAME_PART_PATHS
from .part_redirects import ALL_PART_REDIRECTS
from .physical_parts import PHYSICAL_PART_PATHS
from .unique_compatibility import BALANCE_PARTS
from .shared_grips import SHARED_GRIPS
from .native_compatibility import NATIVE_PARTS, NATIVE_EMPTY_SLOTS
from .weapon_attributes import suspend_bonuses


WEAPON_FIELDS = (
    "BalanceDefinition",
    "ManufacturerDefinition",
    "WeaponTypeDefinition",
    "ManufacturerGradeIndex",
    "BodyPartDefinition",
    "GripPartDefinition",
    "MagazinePartDefinition",
    "BarrelPartDefinition",
    "SightPartDefinition",
    "StockPartDefinition",
    "ActionPartDefinition",
    "AccessoryPartDefinition",
    "MaterialPartDefinition",
    "PrefixPartDefinition",
    "TitlePartDefinition",
)

SLOTS = (
    ("Body", "BodyPartDefinition", "BodyPartData"),
    ("Grip", "GripPartDefinition", "GripPartData"),
    ("Magazine", "MagazinePartDefinition", "MagazinePartData"),
    ("Barrel", "BarrelPartDefinition", "BarrelPartData"),
    ("Sight", "SightPartDefinition", "SightPartData"),
    ("Stock", "StockPartDefinition", "StockPartData"),
    ("Action", "ActionPartDefinition", "ActionPartData"),
    ("Accessory", "AccessoryPartDefinition", "AccessoryPartData"),
    ("Material", "MaterialPartDefinition", "MaterialPartData"),
    ("Prefix", "PrefixPartDefinition", "PrefixNameParts"),
    ("Title", "TitlePartDefinition", "TitleNameParts"),
)

FAMILY_NAMES = {
    "alien_rifle": "Eridian",
    "combat_rifle": "Combat Rifle",
    "combat_shotgun": "Combat Shotgun",
    "grenade_launcher": "Grenade Launcher",
    "machine_pistol": "Machine Pistol",
    "patrol_smg": "SMG",
    "repeater_pistol": "Repeater",
    "revolver_pistol": "Revolver",
    "rocket_launcher": "Rocket Launcher",
    "sniper_rifle": "Sniper Rifle",
    "sniper_rifle_semiauto": "Semi-Auto Sniper",
    "support_machinegun": "Support MG",
    "assault_shotgun": "Assault Shotgun",
    "scorpio": "Scorpio",
    "combat_shotgun_test_j": "Internal Test - Wave Shotgun",
    "combat_shotgun_toon": "Internal Test - Toon Shotgun",
}


@dataclass
class Session:
    weapon: UObject
    original: dict[str, Any]
    invalid_mode: bool = False
    dirty: bool = False


@dataclass(frozen=True)
class CatalogPart:
    """Safe database reference; resolved to a live UObject only on apply."""
    path: str
    class_name: str


_session: Session | None = None
_box: OptionBox | None = None
_part_catalogs: dict[str, list[UObject]] = {}

# Generated from the supplied Enhanced packages' real ObjectRedirector
# exports. This replaces the former hand-written/guessed alias table.
ENHANCED_PART_ALIASES = ALL_PART_REDIRECTS
_loaded_catalog_packages: set[str] = set()
_known_object_paths: dict[int, str] = {}
_catalog_resolution_cache: dict[tuple[str, str], UObject | None] = {}


def _pin_definition(obj: Any) -> Any:
    """Protect cached definitions, never actors, from Unreal garbage collection."""
    if isinstance(obj, UObject):
        obj.ObjectFlags |= ObjectFlags.KEEP_ALIVE
    return obj


def _load_catalog_package(path: str, *, retry: bool = False) -> None:
    """Load a definition's package before resolving its object.

    find_object only searches packages already resident in BL1E. Without this,
    the Workshop catalog changed according to the equipped weapon and loaded
    map (Dahl Raven was the clearest casualty).
    """
    package = path.split(".", 1)[0]
    key = package.lower()
    if not package or (key in _loaded_catalog_packages and not retry):
        return
    try:
        unrealsdk.load_package(package)
        _loaded_catalog_packages.add(key)
    except Exception as exc:
        logging.warning(f"Pandora's Workshop could not load package {package}: {exc}")


def _short(value: Any) -> str:
    if value is None:
        return "None"
    if isinstance(value, CatalogPart):
        return value.path
    try:
        text = str(value)
    except Exception as exc:
        logging.warning(f"Pandora's Workshop skipped an unreadable UObject wrapper: {exc}")
        return ""
    if "'" in text:
        text = text.split("'", 1)[1].rsplit("'", 1)[0]
    return text


def _leaf(value: Any) -> str:
    return _short(value).rsplit(".", 1)[-1]


def _weapon_name(weapon: UObject) -> str:
    # Equipped weapons normally have GeneratedItemName populated already,
    # while unequipped backpack weapons frequently leave it blank until the
    # inventory movie requests a card.  The human-readable accessors perform
    # that lazy resolution without rebuilding/equipping the weapon.
    for function_name in ("GetShortHumanReadableName", "GetHumanReadableName", "GetItemName"):
        try:
            value = getattr(weapon, function_name)()
            if value and not re.fullmatch(r"WillowWeapon(?:_\d+)?", str(value)):
                return str(value)
        except Exception:
            pass
    for attr in ("GeneratedItemName", "ItemName", "WeaponName"):
        try:
            value = getattr(weapon, attr)
            if value and not re.fullmatch(r"WillowWeapon(?:_\d+)?", str(value)):
                return str(value)
        except Exception:
            pass
    return _definition_name(weapon)


def _part_display_name(part: Any) -> str:
    """Best-effort readable name for a name/manufacturer/type definition."""
    if part is None:
        return ""
    for attr in ("PartName", "ItemName", "ManufacturerName", "WeaponTypeName"):
        try:
            value = getattr(part, attr)
            if value:
                return str(value)
        except Exception:
            pass
    leaf = _leaf(part)
    leaf = re.sub(r"^(?:Prefix|Title|WeaponType|Material)_?", "", leaf, flags=re.IGNORECASE)
    leaf = re.sub(r"^(?:Damage|Accuracy|FireRate|LowAccuracy|HighSpread|Tech|Quality)\d*_?", "", leaf, flags=re.IGNORECASE)
    return leaf.replace("_", " ").strip()


def _definition_name(weapon: UObject) -> str:
    """Readable fallback for backpack entries whose cached card name is blank."""
    try:
        data = weapon.DefinitionData
        manufacturer = _part_display_name(data.ManufacturerDefinition)
        prefix = _part_display_name(data.PrefixPartDefinition)
        title = _part_display_name(data.TitlePartDefinition)
        weapon_type = _part_display_name(data.WeaponTypeDefinition)
        words = [word for word in (manufacturer, prefix, title or weapon_type) if word]
        if words:
            return " ".join(words)
    except Exception:
        pass
    return _leaf(weapon)


def _notify(message: str) -> None:
    logging.info(f"Pandora's Workshop: {message}")
    try:
        pc = get_pc()
        pc.myHUD.AddTrainingText(message, "Pandora's Workshop", 2.5, (), "", False, 0, pc.PlayerReplicationInfo, True)
    except Exception:
        pass


def _snapshot(weapon: UObject) -> dict[str, Any]:
    definition = weapon.DefinitionData
    result = {}
    for field in WEAPON_FIELDS:
        try:
            result[field] = _pin_definition(getattr(definition, field))
        except Exception:
            pass
    return result


def _signed16(value: int) -> int:
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def _grade_components(weapon: UObject) -> tuple[int, int]:
    """Decode BL1's packed ManufacturerGradeIndex as (quality, level)."""
    packed = int(weapon.DefinitionData.ManufacturerGradeIndex) & 0xFFFFFFFF
    return _signed16(packed), _signed16(packed >> 16)


def _pack_grade(quality: int, level: int) -> int:
    packed = ((level & 0xFFFF) << 16) | (quality & 0xFFFF)
    return packed - 0x100000000 if packed & 0x80000000 else packed


def _restore_snapshot(session: Session) -> None:
    definition = session.weapon.DefinitionData
    for field, value in session.original.items():
        try:
            setattr(definition, field, value)
        except Exception as exc:
            logging.warning(f"Pandora's Workshop could not restore {field}: {exc}")
    _rebuild(session.weapon)


def _rebuild(weapon: UObject, checkpoint: Callable[[str], None] | None = None, *, reinitialize: bool = True, material_only: bool = False) -> None:
    if reinitialize or material_only:
        with suspend_bonuses(weapon):
            _rebuild_without_bonuses(weapon, checkpoint, reinitialize=reinitialize, material_only=material_only)
    else:
        _rebuild_without_bonuses(weapon, checkpoint, reinitialize=False)

    try:
        if checkpoint is not None:
            checkpoint("Before NotifyChangedWeapon")
        pc = get_pc()
        pc.NotifyChangedWeapon(weapon, weapon)
    except Exception as exc:
        logging.warning(f"Workshop weapon change notification failed: {exc}")
    if checkpoint is not None:
        checkpoint("Native rebuild calls completed")



def _rebuild_without_bonuses(weapon: UObject, checkpoint: Callable[[str], None] | None = None, *, reinitialize: bool = True, material_only: bool = False) -> None:
    """Ask Enhanced to regenerate a live weapon after DefinitionData changes."""
    errors = []
    initialized = not reinitialize
    try:
        if checkpoint is not None:
            checkpoint("Before owner lookup")
        query_source = weapon.Owner
        if query_source is None:
            query_source = get_pc().Pawn
        if material_only:
            if checkpoint is not None:
                checkpoint("Before removing cached weapon attribute modifiers")
            for effect in list(weapon.WeaponAttributeModifiers):
                effect.Attribute.RemoveAttributeModifier(effect.Context, effect.Modifier)
            weapon.WeaponAttributeModifiers = []
            weapon.bSelectRandomPartsOnInitialization = False
            if checkpoint is not None:
                checkpoint("Before InitializeInternal for material edit")
            weapon.InitializeInternal(False)
        elif reinitialize:
            if checkpoint is not None:
                checkpoint("Before copying WeaponDefinitionData")
            # Keep native input independent of the instance storage that the
            # initialization event replaces while it is executing.
            definition = unrealsdk.make_struct("WeaponDefinitionData", **_snapshot(weapon))
            if checkpoint is not None:
                checkpoint("Before InitializeFromDefinitionData")
            weapon.InitializeFromDefinitionData(definition, query_source)
        initialized = True
    except Exception as exc:
        errors.append(f"InitializeFromDefinitionData: {exc}")

    # Record each native boundary separately: Python exceptions cannot catch
    # a general protection fault inside these calls.
    for name, args in (
        ("GenerateHumanReadableName", ()),
        ("CalculateWeaponBaseValues", ()),
        ("ConstructInvMesh", ()),
        ("CacheWeaponCard", ()),
    ):
        if name == "CalculateWeaponBaseValues" and initialized:
            # InitializeInternal already calculates bases, then applies part
            # effects. Recalculating here resets values after those effects.
            continue
        try:
            if checkpoint is not None:
                checkpoint(f"Before {name}")
            getattr(weapon, name)(*args)
        except Exception as exc:
            errors.append(f"{name}: {exc}")

    if not initialized:
        logging.warning("Pandora's Workshop rebuild used fallback refresh; " + " | ".join(errors))
    elif errors:
        logging.info("Pandora's Workshop rebuild completed with optional refresh differences: " + " | ".join(errors))


def _current_weapon() -> UObject | None:
    pc = get_pc()
    if pc is None or pc.Pawn is None:
        return None
    pawn = pc.Pawn

    # Resolve through ordinary UObject properties only. Calling
    # WillowPlayerController.GetCurrentEquippedWeapon directly caused a native
    # GPF in BL1E even though reflection exposes it as a bound function.
    property_paths = (
        (pawn, "Weapon"),
        (pawn, "CurrentWeapon"),
        (getattr(pawn, "InvManager", None), "CurrentWeapon"),
        (getattr(pawn, "InventoryManager", None), "CurrentWeapon"),
    )
    for owner, attr in property_paths:
        if owner is None:
            continue
        try:
            weapon = getattr(owner, attr)
            if weapon is not None and "WillowWeapon" in str(weapon.Class):
                return weapon
        except Exception:
            pass

    # Last property-only fallback: an equipped weapon is owned by the local
    # pawn. Do not invoke IsActiveWeapon() here; that direct native call is not
    # safe until we establish its BL1E calling requirements.
    for weapon in unrealsdk.find_all("WillowWeapon"):
        try:
            if str(weapon).startswith("WillowGame.Default__"):
                continue
            if weapon.Owner == pawn:
                return weapon
        except Exception:
            pass
    return None


def _manufacturer_allowed(weighted: Any, manufacturer: Any) -> bool:
    try:
        restrictions = list(weighted.Manufacturers)
    except Exception:
        return True
    if not restrictions:
        return True
    for restriction in restrictions:
        try:
            allowed = restriction.Manufacturer
            if allowed is None or allowed == manufacturer:
                return True
        except Exception:
            return True
    return False


def _part_collection(weapon: UObject) -> Any:
    try:
        if weapon.PartListCollection is not None:
            return weapon.PartListCollection
    except Exception:
        pass
    definition = weapon.DefinitionData
    try:
        balance = definition.BalanceDefinition
        if balance.PartListCollection is not None:
            return balance.PartListCollection
    except Exception:
        pass
    # Do not directly invoke GetInventoryPartListCollection. Like the equipped
    # weapon getter, BL1E exposes this native function without guaranteeing the
    # calling state expected by its normal UnrealScript path.
    return None


def _weighted_slot_entries(session: Session, collection_field: str) -> list[Any]:
    """The game's weighted part entries for one weapon slot."""
    weighted_parts = []
    type_field = collection_field.replace("PartData", "Parts")
    try:
        part_list = getattr(session.weapon.DefinitionData.WeaponTypeDefinition, type_field)
        if part_list is not None:
            weighted_parts.extend(list(part_list.WeightedParts))
    except Exception:
        pass
    collection = _part_collection(session.weapon)
    if collection is not None:
        try:
            weighted_parts.extend(list(getattr(collection, collection_field).WeightedParts))
        except Exception:
            pass
    return weighted_parts


def _valid_parts(
    session: Session,
    collection_field: str,
    *,
    include_native: bool = True,
    quiet: bool = False,
) -> list[UObject]:
    manufacturer = session.weapon.DefinitionData.ManufacturerDefinition
    if collection_field.endswith("NameParts"):
        return _valid_name_parts(session, collection_field.removesuffix("NameParts"))
    weighted_parts = []

    # Ordinary weapons take their base compatibility lists directly from the
    # WeaponTypeDefinition. Balance-level collections add or replace parts for
    # uniques, DLC gear, and other special cases.
    type_field = collection_field.replace("PartData", "Parts")
    try:
        weapon_type = session.weapon.DefinitionData.WeaponTypeDefinition
        part_list = getattr(weapon_type, type_field)
        if part_list is not None:
            weighted_parts.extend(list(part_list.WeightedParts))
    except Exception as exc:
        if not quiet:
            logging.warning(f"Pandora's Workshop could not read weapon type {type_field}: {exc}")

    collection = _part_collection(session.weapon)
    if collection is not None:
        try:
            weighted_parts.extend(list(getattr(collection, collection_field).WeightedParts))
        except Exception as exc:
            if not quiet:
                logging.warning(f"Pandora's Workshop could not read overlay {collection_field}: {exc}")

    result = []
    seen = set()
    for weighted in weighted_parts:
        try:
            part = weighted.Part
            key = ENHANCED_PART_ALIASES.get(_short(part).lower(), _short(part).lower()).lower()
            if part is not None and key not in seen and _manufacturer_allowed(weighted, manufacturer):
                seen.add(key)
                result.append(part)
        except Exception:
            pass
    # Unique balances contribute explicit slot assignments absent from the
    # ordinary generation list. Respect inherited and per-entry manufacturers.
    weapon_type_path = _short(session.weapon.DefinitionData.WeaponTypeDefinition).lower()
    manufacturer_path = _short(manufacturer).lower()
    for entry in BALANCE_PARTS:
        if entry["weapon_type"] != weapon_type_path or entry["slot"] != collection_field:
            continue
        if entry["manufacturers"] and manufacturer_path not in entry["manufacturers"]:
            continue
        part = CatalogPart(entry["part"], "WeaponPartDefinition")
        identity = ENHANCED_PART_ALIASES.get(part.path.lower(), part.path.lower()).lower()
        if identity not in seen:
            seen.add(identity)
            result.append(part)
    # Supplement generation arrays only with native-accepted assignments for
    # this exact context. A unique's balance must not borrow a different
    # balance's results. These are precomputed, so opening a menu is cheap.
    balance_path = _short(getattr(session.weapon.DefinitionData, "BalanceDefinition", None)).lower()
    context = (weapon_type_path, manufacturer_path, balance_path)
    definition_field = collection_field.replace("PartData", "PartDefinition")
    if not include_native:
        native_paths = ()
    elif context in NATIVE_PARTS:
        native_paths = NATIVE_PARTS[context].get(definition_field, ())
    else:
        # Combination missing from the table (e.g. Maliwan SMGs, S&S semi-auto
        # snipers). Accept only parts every listed manufacturer of the same
        # weapon type and balance accepts; manufacturer-exclusive parts still
        # come from the game's own lists above.
        peer_sets = [
            {path.lower(): path for path in parts.get(definition_field, ())}
            for (peer_type, _peer_manufacturer, peer_balance), parts in NATIVE_PARTS.items()
            if peer_type == weapon_type_path and peer_balance == balance_path
        ]
        common = set.intersection(*(set(peer) for peer in peer_sets)) if peer_sets else set()
        native_paths = sorted(peer_sets[0][key] for key in common) if peer_sets else ()
    for path in native_paths:
        identity = ENHANCED_PART_ALIASES.get(path.lower(), path.lower()).lower()
        if identity not in seen:
            seen.add(identity)
            result.append(CatalogPart(path, "WeaponPartDefinition"))
    # Grip definitions are shared by related weapon types, with different
    # manufacturer labels in each generation list. Read the source collection
    # rather than treating one type's spawn list as the complete grip catalog.
    if collection_field == "GripPartData":
        for path, manufacturers in SHARED_GRIPS.get(weapon_type_path, {}).items():
            if manufacturers and manufacturer_path not in manufacturers:
                continue
            identity = ENHANCED_PART_ALIASES.get(path.lower(), path.lower()).lower()
            if identity not in seen:
                seen.add(identity)
                result.append(CatalogPart(path, "WeaponPartDefinition"))
    result = sorted(result, key=lambda part: _short(part).lower())
    if not quiet:
        logging.info(
            f"Pandora's Workshop valid resolver: {type_field}, "
            f"{len(weighted_parts)} weighted entries, {len(result)} selectable parts"
        )
    return result


def _valid_name_parts(session: Session, category: str) -> list[UObject]:
    """Name definitions are accepted in either name slot across weapon families.

    Native detached-definition probes accepted all 358 resolved name definitions
    in both fields for every one of 330 accepted type/manufacturer baselines.
    Do not confuse name generation preferences with save validation rules.
    """
    result = {}
    for part in _catalog("name"):
        identity = ENHANCED_PART_ALIASES.get(_short(part).lower(), _short(part).lower()).lower()
        result.setdefault(identity, part)
    current_field = "PrefixPartDefinition" if category == "Prefix" else "TitlePartDefinition"
    current = getattr(session.weapon.DefinitionData, current_field, None)
    if current is not None:
        identity = ENHANCED_PART_ALIASES.get(_short(current).lower(), _short(current).lower()).lower()
        result.setdefault(identity, current)
    return sorted(result.values(), key=lambda part: _short(part).lower())


def _catalog(kind: str = "physical") -> list[UObject]:
    if kind not in _part_catalogs:
        paths = NAME_PART_PATHS if kind == "name" else PHYSICAL_PART_PATHS
        class_name = "WeaponNamePartDefinition" if kind == "name" else "WeaponPartDefinition"
        # Collapse every cooked redirector onto its concrete destination. The
        # first path remains the searchable/displayed legacy name, while only
        # one live object is offered. This prevents duplicate Nemesis/Revenge
        # rows without losing those familiar names from search.
        unique: dict[str, str] = {}
        for path in paths:
            identity = ENHANCED_PART_ALIASES.get(path.lower(), path).lower()
            unique.setdefault(identity, path)
        _part_catalogs[kind] = [
            CatalogPart(path, class_name)
            for path in unique.values()
        ]
    return _part_catalogs[kind]


def _resolve_catalog_part(part: Any, *, quiet: bool = False) -> UObject | None:
    """Resolve a safe catalog reference at the last possible moment."""
    if not isinstance(part, CatalogPart):
        return _pin_definition(part)
    cache_key = (part.class_name, part.path.lower())
    if quiet and cache_key in _catalog_resolution_cache:
        cached = _catalog_resolution_cache[cache_key]
        return cached
    # Never reuse a live UObject wrapper for an explicit selection. The
    # supplied crash log showed silver_red's cached wrapper naming Typhoon.
    try:
        lookup_path = ENHANCED_PART_ALIASES.get(part.path.lower(), part.path)
        expected_paths = {part.path.lower(), lookup_path.lower()}
        _load_catalog_package(lookup_path)
        try:
            resolved = unrealsdk.find_object(part.class_name, lookup_path)
        except Exception:
            resolved = None
        if resolved is None:
            _load_catalog_package(lookup_path, retry=True)
            try:
                resolved = unrealsdk.find_object(part.class_name, lookup_path)
            except Exception:
                resolved = None
        if resolved is not None and _short(resolved).lower() not in expected_paths:
            logging.warning(f"Pandora's Workshop rejected mismatched lookup {part.path} -> {_short(resolved)}")
            resolved = None
        if resolved is None and lookup_path.lower() != part.path.lower():
            # A cooked redirect destination may differ between package builds.
            # Preserve the original exported name as an independent lookup.
            _load_catalog_package(part.path)
            try:
                resolved = unrealsdk.find_object(part.class_name, part.path)
            except Exception:
                resolved = None
            if resolved is not None and _short(resolved).lower() not in expected_paths:
                resolved = None
        if resolved is None:
            # Enhanced retains a small number of useful classic object names
            # as Core.ObjectRedirectors (Revenge, the DLC3 explosive alias,
            # promotional parts, and others). They are valid catalog entries,
            # but cannot be found as WeaponPartDefinition directly.
            try:
                redirector = unrealsdk.find_object("ObjectRedirector", part.path)
                if redirector is None and lookup_path.lower() != part.path.lower():
                    redirector = unrealsdk.find_object("ObjectRedirector", lookup_path)
            except Exception:
                redirector = None
            if redirector is not None:
                _pin_definition(redirector)
                destination = getattr(redirector, "DestinationObject", None)
                # Trust the actual cooked redirect, not a guessed category.
                if destination is not None:
                    resolved = destination
        if resolved is not None:
            _pin_definition(resolved)
            _catalog_resolution_cache[cache_key] = resolved
        else:
            _catalog_resolution_cache.pop(cache_key, None)
            if not quiet:
                logging.warning(
                    f"Pandora's Workshop lookup failed after package retry: "
                    f"class={part.class_name}, requested={part.path}, alias={lookup_path}"
                )
        return resolved
    except Exception as exc:
        _catalog_resolution_cache.pop(cache_key, None)
        if not quiet:
            logging.warning(f"Pandora's Workshop could not resolve {part.path}: {exc}")
        return None


def _remember_weapon_parts(weapon: UObject) -> None:
    """Merge the selected weapon's live definitions into the bounded catalog.

    The static database is intentionally bounded because a global BL1E object
    walk can native-crash.  A live weapon is safe, however, and is also the
    best authority for event/DLC/name parts which an older editor database did
    not know about.
    """
    try:
        definition = weapon.DefinitionData
    except Exception:
        return
    for label, field, _collection in SLOTS:
        try:
            part = getattr(definition, field)
        except Exception:
            continue
        if part is None:
            continue
        kind = "name" if label in ("Prefix", "Title") else "physical"
        catalog = _catalog(kind)
        key = _short(part).lower()
        identity = ENHANCED_PART_ALIASES.get(key, key).lower()
        if not key:
            continue
        existing_identities = {
            ENHANCED_PART_ALIASES.get(existing_key, existing_key).lower()
            for existing_key in (_short(existing).lower() for existing in catalog)
            if existing_key
        }
        if identity not in existing_identities:
            catalog.append(part)
            catalog.sort(key=lambda candidate: _short(candidate).lower())
            logging.info(f"Pandora's Workshop learned live {label} part {key}")


def _family(part: UObject) -> str:
    path = _short(part).lower()
    match = re.search(r"(?:^|\.)gd_weap_([^\.]+)", path)
    if not match:
        # DLC unique-part packages put the weapon family in the group name
        # rather than the package name (for example
        # ``...UniqueParts.MachinePistol.barrel4_Revenge``).
        grouped_families = (
            ("commanddecks", "Class Mod"),
            ("machinepistol", "Machine Pistol"),
            ("repeaterpistol", "Repeater Pistol"),
            ("revolverpistol", "Revolver"),
            ("combatshotgun", "Combat Shotgun"),
            ("combat_rifle", "Combat Rifle"),
            ("combatrifle", "Combat Rifle"),
            ("supportmachinegun", "Support MG"),
            ("semiautosniper", "Semi-Auto Sniper"),
            ("sniperrifle", "Sniper Rifle"),
            ("rocketlauncher", "Rocket Launcher"),
            ("eridanrifle", "Eridian Rifle"),
            ("eridian_weapons", "Eridian"),
            ("customweapons.title", "Custom Weapon"),
            ("uniqueparts.title", "Unique Weapon"),
            ("smg", "SMG"),
        )
        compact = path.replace("_", "")
        for token, label in grouped_families:
            if token.replace("_", "") in compact:
                return label
        if "customweapon" in path or "uniquepart" in path:
            return "Unique / Custom"
        if "shared" in path or "material" in path:
            return "Shared / Materials"
        return "Other"
    raw = match.group(1)
    return FAMILY_NAMES.get(raw, raw.replace("_", " ").title())


def _declared_category(part: UObject) -> str:
    path = _short(part).lower()
    if ".prefix." in path or ".prefix_" in path:
        return "Prefixes"
    if ".title." in path or ".title_" in path:
        return "Titles"
    tokens = (
        ("barrel", "Barrels"), ("mag", "Magazines"), ("grip", "Grips"),
        ("body", "Bodies"), ("sight", "Sights"), ("stock", "Stocks"),
        ("action", "Actions"), ("acc", "Accessories"),
        ("material", "Materials"),
    )
    for needle, label in tokens:
        if re.search(rf"(?:^|[._]){needle}(?:[._0-9]|$)", path):
            return label
    return "Unique / Other"


def _show_box(
    title: str,
    message: str,
    entries: list[tuple[str, str, Callable[[], None]]],
    cancel: Callable[[], None],
) -> None:
    global _box
    buttons = [OptionBoxButton(name, tip) for name, tip, _ in entries]
    actions = {id(button): entries[idx][2] for idx, button in enumerate(buttons)}
    box = OptionBox(title=title, message=message, buttons=buttons)

    def selected(_box: OptionBox, button: OptionBoxButton) -> None:
        action = actions.get(id(button))
        if action is not None:
            action()

    def cancelled(_box: OptionBox) -> None:
        cancel()

    box.on_select = selected
    box.on_cancel = cancelled
    _box = box
    box.show()


def _main_menu() -> None:
    session = _session
    if session is None:
        return
    mode = "INVALID — unrestricted catalog" if session.invalid_mode else "VALID — native compatible parts"
    # BL1E's stock option dialog draws long message text through the same
    # vertical region as its buttons. Keep this scaffold deliberately compact;
    # the full definition belongs in the purpose-built Workshop panel.
    message = f"Mode: {mode}\n\nChoose a part slot, change editing mode, or finish this session."
    entries = [
        ("Choose Part Slot", "Select which definition field to edit.", _slot_menu),
        ("Adjust Quality / Level", "Edit the two packed weapon grade values independently.", _grade_menu),
        ("Toggle Valid / Invalid", "Switch compatible filtering on or off.", _toggle_mode),
        ("Apply", "Keep all changes made during this session.", _apply),
        ("Cancel and Restore", "Restore the weapon exactly as it was when opened.", _cancel),
    ]
    _show_box("Pandora's Workshop — " + _weapon_name(session.weapon), message, entries, _cancel)


def _grade_menu() -> None:
    session = _session
    if session is None:
        return
    quality, level = _grade_components(session.weapon)
    entries = [
        (f"Quality: {quality}", "Change weapon quality without changing its stored level.", _quality_menu),
        (f"Stored level: {level}", "Change the packed base level; the inventory requirement may differ due to parts.", _level_menu),
        ("Back", "Return to Pandora's Workshop.", _main_menu),
    ]
    _show_box(
        "Weapon quality and level",
        f"Current quality: {quality}\nStored level: {level}\n\nThe inventory requirement may differ because weapon parts modify it.",
        entries,
        _main_menu,
    )


def _quality_menu() -> None:
    session = _session
    if session is None:
        return
    quality, _level = _grade_components(session.weapon)
    entries = [
        ("-1", "Decrease quality by 1.", lambda: _adjust_grade("quality", -1)),
        ("+1", "Increase quality by 1.", lambda: _adjust_grade("quality", 1)),
        ("Set 0", "Set quality to 0.", lambda: _set_grade_component("quality", 0)),
        ("Set 5", "Set quality to the usual maximum of 5.", lambda: _set_grade_component("quality", 5)),
        ("Back", "Return to quality and level.", _grade_menu),
    ]
    _show_box("Adjust quality", f"Current quality: {quality}", entries, _grade_menu)


def _level_menu() -> None:
    session = _session
    if session is None:
        return
    _quality, level = _grade_components(session.weapon)
    entries = [
        ("-10", "Decrease stored level by 10.", lambda: _adjust_grade("level", -10)),
        ("-1", "Decrease stored level by 1.", lambda: _adjust_grade("level", -1)),
        ("+1", "Increase level by 1.", lambda: _adjust_grade("level", 1)),
        ("+10", "Increase level by 10.", lambda: _adjust_grade("level", 10)),
        ("Set 0", "Set level to 0 for stock and placeholder items.", lambda: _set_grade_component("level", 0)),
        ("Set 1", "Set level to 1.", lambda: _set_grade_component("level", 1)),
        ("Set 69", "Set the packed base level to 69.", lambda: _set_grade_component("level", 69)),
        ("Set 71", "Set the packed base level to Enhanced's observed ceiling of 71.", lambda: _set_grade_component("level", 71)),
        ("Back", "Return to quality and level.", _grade_menu),
    ]
    _show_box("Adjust stored level", f"Stored level: {level}\n\nInventory requirement may differ due to part modifiers.", entries, _grade_menu)


def _adjust_grade(component: str, amount: int) -> None:
    session = _session
    if session is None:
        return
    quality, level = _grade_components(session.weapon)
    value = quality if component == "quality" else level
    _set_grade_component(component, value + amount)


def _set_grade_component(component: str, value: int) -> None:
    session = _session
    if session is None:
        return
    quality, level = _grade_components(session.weapon)
    if component == "quality":
        # Values above 5 make BL1E discard the derived level/stat display.
        quality = max(0, min(5, int(value)))
    else:
        # Enhanced stops responding above the observed packed-level ceiling.
        level = max(0, min(71, int(value)))
    session.weapon.DefinitionData.ManufacturerGradeIndex = _pack_grade(quality, level)
    session.dirty = True
    _rebuild(session.weapon)
    _notify(f"Quality {quality}; level {level}")
    _grade_menu()


def _toggle_mode() -> None:
    if _session is not None:
        _session.invalid_mode = not _session.invalid_mode
    _main_menu()


def _slot_menu() -> None:
    session = _session
    if session is None:
        return
    entries = []
    for label, definition_field, collection_field in SLOTS:
        current = _leaf(getattr(session.weapon.DefinitionData, definition_field, None))
        entries.append((label, f"Current: {current}", lambda a=label, b=definition_field, c=collection_field: _open_slot(a, b, c)))
    _show_box("Choose destination slot", "The selected part will be written into this field.", entries, _main_menu)


def _open_slot(label: str, definition_field: str, collection_field: str) -> None:
    session = _session
    if session is None:
        return
    if not session.invalid_mode:
        parts = _valid_parts(session, collection_field)
        _parts_menu(label, definition_field, parts, _slot_menu, "Native compatible parts")
        return
    kind = "name" if definition_field in ("PrefixPartDefinition", "TitlePartDefinition") else "physical"
    families = sorted({_family(part) for part in _catalog(kind)})
    entries = [
        (family, "Browse this source weapon family.", lambda f=family: _invalid_category_menu(label, definition_field, f))
        for family in families
    ]
    _show_box(f"{label} slot — source family", "Invalid mode permits cross-family placement.", entries, _slot_menu)


def _invalid_category_menu(label: str, definition_field: str, family: str) -> None:
    kind = "name" if definition_field in ("PrefixPartDefinition", "TitlePartDefinition") else "physical"
    parts = [part for part in _catalog(kind) if _family(part) == family]
    categories = sorted({_declared_category(part) for part in parts})
    entries = [
        (category, f"Browse {family} {category.lower()}.", lambda c=category: _invalid_parts(label, definition_field, family, c))
        for category in categories
    ]
    _show_box(f"{family} — source category", f"Destination field: {label}", entries, lambda: _open_slot(label, definition_field, ""))


def _invalid_parts(label: str, definition_field: str, family: str, category: str) -> None:
    kind = "name" if definition_field in ("PrefixPartDefinition", "TitlePartDefinition") else "physical"
    parts = [
        part for part in _catalog(kind)
        if _family(part) == family and _declared_category(part) == category
    ]
    _parts_menu(
        label,
        definition_field,
        parts,
        lambda: _invalid_category_menu(label, definition_field, family),
        f"{family} / {category}",
    )


def _parts_menu(
    slot_label: str,
    definition_field: str,
    parts: list[UObject],
    back: Callable[[], None],
    source: str,
) -> None:
    if not parts:
        _show_box(
            f"{slot_label} — no parts found",
            f"No selectable parts were resolved from {source}.\n\nThe SDK log contains the resolver details.",
            [("Back", "Return to the destination slot list.", back)],
            back,
        )
        return
    entries = [
        (_leaf(part), _short(part), lambda p=part: _select_part(slot_label, definition_field, p))
        for part in parts
    ]
    _show_box(f"{slot_label} — {source}", f"{len(parts)} part(s). Full path appears in the footer.", entries, back)


def _select_part(slot_label: str, definition_field: str, part: UObject) -> None:
    session = _session
    if session is None:
        return
    try:
        resolved = _resolve_catalog_part(part)
        if resolved is None:
            _notify(f"{_short(part)} is not available in this Enhanced installation.")
            return
        setattr(session.weapon.DefinitionData, definition_field, resolved)
        session.dirty = True
        _rebuild(session.weapon)
        _notify(f"{slot_label}: {_leaf(part)}")
    except Exception as exc:
        logging.error(f"Pandora's Workshop could not set {definition_field}: {exc}")
        _notify(f"Could not apply {slot_label}; see SDK log.")
    _main_menu()


def _apply() -> None:
    global _session
    session = _session
    if session is None:
        return
    _rebuild(session.weapon)
    name = _weapon_name(session.weapon)
    _session = None
    _notify(f"Applied changes to {name}.")


def _cancel() -> None:
    global _session
    session = _session
    if session is None:
        return
    _restore_snapshot(session)
    name = _weapon_name(session.weapon)
    _session = None
    _notify(f"Restored {name}.")


# This module is the consolidated editing engine used by the native Workshop
# UI.  It intentionally registers no mod and no F7 keybind of its own.


def _valid_empty_slot(session: Session, field: str) -> bool:
    definition = session.weapon.DefinitionData
    context = tuple(_short(getattr(definition, name, None)).lower() for name in
                    ("WeaponTypeDefinition", "ManufacturerDefinition", "BalanceDefinition"))
    if context in NATIVE_EMPTY_SLOTS:
        return field in NATIVE_EMPTY_SLOTS[context]

    # Combination missing from the table (for example S&S semi-auto snipers).
    # In the table, empty-slot rules depend only on weapon type and balance,
    # except Grip, which also varies by manufacturer.
    peers = [
        allowed for (weapon_type, _manufacturer, balance), allowed in NATIVE_EMPTY_SLOTS.items()
        if weapon_type == context[0] and balance == context[2]
    ]
    if peers and all(field in allowed for allowed in peers):
        return True
    if peers and field != "GripPartDefinition":
        return False

    # Otherwise use the game's own lists: empty is allowed when the game offers
    # no parts for this slot, or lists an empty entry for this manufacturer.
    collection_field = field.replace("PartDefinition", "PartData")
    manufacturer = definition.ManufacturerDefinition
    for weighted in _weighted_slot_entries(session, collection_field):
        try:
            if weighted.Part is None and _manufacturer_allowed(weighted, manufacturer):
                return True
        except Exception:
            pass
    return not _valid_parts(session, collection_field)
