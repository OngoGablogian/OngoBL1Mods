"""
SDU Guaranteed - Borderlands 1 GOTY / GOTY Enhanced (willow1-mod-manager)

Makes Backpack SDU mission rewards (Claptrap Rescue missions) guaranteed on every
playthrough instead of sometimes rolling a grenade mod.

Based on "SDU Guaranteed" by Miner Of Worlds (MOW531), GPL-3.0.

How it works: the Claptrap reward rolls through an InventoryBalanceDefinition
(e.g. gd_itemgrades.StorageDeckUpgrades.ItemGrade_SDU_InventorySlots). Its
Manufacturers/Grades are replaced with a single grade that always produces a
Backpack SDU at any game stage. Every backpack-SDU balance that is loaded gets
patched, so DLC claptraps (including any DLC-specific balance such as one used by
Lockdown Palace) are covered as soon as their package is in memory.
"""

from __future__ import annotations

import argparse
from typing import Any

import unrealsdk
from unrealsdk import logging
from unrealsdk.hooks import Type
from unrealsdk.unreal import BoundFunction, UObject, WrappedStruct

from mods_base import build_mod, command, hook

# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #

BALANCE_CLASS = "InventoryBalanceDefinition"

# Balances we know about. Each is force-loaded (if the package exists) and patched.
KNOWN_BALANCES: tuple[str, ...] = (
    "gd_itemgrades.StorageDeckUpgrades.ItemGrade_SDU_InventorySlots",
    "dlc1_gd_itemgrades.StorageDeckUpgrades.dlc1_ItemGrade_SDU_InventorySlots",
    "DLC4_Itemgrades.StorageDeckUpgrades.ItemGrade_SDU_InventorySlots",
)

# Any other loaded balance whose name contains this is also treated as a backpack
# SDU balance (catches DLC balances not listed above, e.g. Knoxx / Lockdown Palace).
BALANCE_NAME_MATCH = "sdu_inventoryslots"

SDU_ITEM = "gd_StorageDeckUpgrade.INV_InventorySpace.INV_InventorySpace"
FALLBACK_MANUFACTURER = "gd_manufacturers.Manufacturers.Dahl"

MIN_STAGE = 1
MAX_STAGE = 999

# path name -> list of standalone copies of the original Manufacturers entries
_originals: dict[str, list[WrappedStruct]] = {}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _find(cls: str, path: str, load: bool = True) -> UObject | None:
    """Find an object, optionally loading its package first. Never raises."""
    if load:
        try:
            unrealsdk.load_package(path.split(".", 1)[0])
        except Exception:  # noqa: BLE001 - package may not exist (DLC not owned)
            pass
    try:
        return unrealsdk.find_object(cls, path)
    except Exception:  # noqa: BLE001
        return None


def _copy_struct(src: WrappedStruct) -> WrappedStruct:
    """Make a standalone copy of a struct (arrays/sub-structs copied by value)."""
    dst = unrealsdk.make_struct(src._type.Name)  # noqa: SLF001
    for prop in src._type._properties():  # noqa: SLF001
        try:
            setattr(dst, prop.Name, getattr(src, prop.Name))
        except Exception:  # noqa: BLE001 - e.g. unusual fixed arrays; leave default
            pass
    return dst


def _sdu_balances() -> list[UObject]:
    """All backpack-SDU balance definitions currently in memory (deduplicated)."""
    found: dict[str, UObject] = {}

    for path in KNOWN_BALANCES:
        bal = _find(BALANCE_CLASS, path)
        if bal is not None:
            found[bal._path_name()] = bal  # noqa: SLF001

    try:
        for bal in unrealsdk.find_all(BALANCE_CLASS, exact=False):
            name = bal.Name.lower()
            if name.startswith("default__"):
                continue
            if BALANCE_NAME_MATCH in name:
                found.setdefault(bal._path_name(), bal)  # noqa: SLF001
    except Exception:  # noqa: BLE001
        pass

    return list(found.values())


def _is_patched(bal: UObject, sdu: UObject) -> bool:
    try:
        mfrs = bal.Manufacturers
        if len(mfrs) != 1 or len(mfrs[0].Grades) != 1:
            return False
        grade = mfrs[0].Grades[0]
        return (
            grade.GradeModifiers.CustomInventoryDefinition == sdu
            and grade.GameStageRequirement.MinGameStage == MIN_STAGE
            and grade.GameStageRequirement.MaxGameStage == MAX_STAGE
            and grade.MinSpawnProbabilityModifier.BaseValueConstant == 1
            and grade.MaxSpawnProbabilityModifier.BaseValueConstant == 1
        )
    except Exception:  # noqa: BLE001
        return False


def _patch_one(bal: UObject, sdu: UObject) -> bool:
    """Patch a single balance. Returns True if it changed something."""
    if _is_patched(bal, sdu):
        return False

    path = bal._path_name()  # noqa: SLF001

    # This is a freshly (re)loaded, unpatched object: remember its original values.
    try:
        _originals[path] = [_copy_struct(m) for m in bal.Manufacturers]
    except Exception as ex:  # noqa: BLE001
        logging.warning(f"[SDU Guaranteed] Couldn't back up {path}: {ex}")

    # Keep the balance's own manufacturer if it has one (Dahl base, Hyperion DLC4...).
    manufacturer = None
    try:
        if len(bal.Manufacturers) > 0:
            manufacturer = bal.Manufacturers[0].Manufacturer
    except Exception:  # noqa: BLE001
        pass
    if manufacturer is None:
        manufacturer = _find("ManufacturerDefinition", FALLBACK_MANUFACTURER)

    bal.Manufacturers = [
        unrealsdk.make_struct(
            "InventoryManufacturerBalanceData",
            Manufacturer=manufacturer,
            Grades=[
                unrealsdk.make_struct(
                    "InventoryGameStageGradeWeightData",
                    GradeModifiers=unrealsdk.make_struct(
                        "InventoryGradeModifierData",
                        ExpLevel=1,
                        CustomInventoryDefinition=sdu,
                    ),
                ),
            ],
        ),
    ]

    grade = bal.Manufacturers[0].Grades[0]
    grade.GameStageRequirement.MinGameStage = MIN_STAGE
    grade.GameStageRequirement.MaxGameStage = MAX_STAGE
    grade.MinSpawnProbabilityModifier.BaseValueConstant = 1
    grade.MinSpawnProbabilityModifier.BaseValueScaleConstant = 1
    grade.MaxSpawnProbabilityModifier.BaseValueConstant = 1
    grade.MaxSpawnProbabilityModifier.BaseValueScaleConstant = 1
    return True


def apply_patch() -> None:
    sdu = _find("ItemDefinition", SDU_ITEM)
    if sdu is None:
        logging.warning(f"[SDU Guaranteed] Couldn't find {SDU_ITEM}; nothing patched.")
        return

    for bal in _sdu_balances():
        try:
            if _patch_one(bal, sdu):
                logging.dev_warning(f"[SDU Guaranteed] Patched {bal._path_name()}")  # noqa: SLF001
        except Exception as ex:  # noqa: BLE001
            logging.warning(f"[SDU Guaranteed] Failed to patch {bal._path_name()}: {ex}")  # noqa: SLF001


def restore_patch() -> None:
    for path, saved in _originals.items():
        bal = _find(BALANCE_CLASS, path, load=False)
        if bal is None:
            continue  # package already unloaded - it'll come back from disk unpatched
        try:
            bal.Manufacturers = saved
        except Exception as ex:  # noqa: BLE001
            logging.warning(f"[SDU Guaranteed] Failed to restore {path}: {ex}")


# --------------------------------------------------------------------------- #
# Hooks / lifecycle
# --------------------------------------------------------------------------- #


@hook("Engine.WorldInfo:PostBeginPlay", Type.POST)
def on_world_begin_play(
    _obj: UObject,
    _args: WrappedStruct,
    _ret: Any,
    _func: BoundFunction,
) -> None:
    # Packages are reloaded from disk on map changes, which undoes the patch.
    # Re-check on every world start; already-patched balances are skipped, so this
    # is cheap and doesn't depend on how many times the event fires per load.
    apply_patch()


def on_enable() -> None:
    apply_patch()


def on_disable() -> None:
    restore_patch()


@command("sdu_guaranteed_status", description="List backpack SDU balances and whether they're patched.")
def sdu_status(_args: argparse.Namespace) -> None:
    sdu = _find("ItemDefinition", SDU_ITEM)
    balances = _sdu_balances()
    if sdu is None or not balances:
        print("[SDU Guaranteed] No backpack SDU balances found.")
        return
    for bal in balances:
        state = "patched" if _is_patched(bal, sdu) else "NOT patched"
        print(f"[SDU Guaranteed] {bal._path_name()}: {state}")  # noqa: SLF001


# --------------------------------------------------------------------------- #

__version__: str
__version_info__: tuple[int, ...]

build_mod(
    hooks=[on_world_begin_play],
    commands=[sdu_status],
    on_enable=on_enable,
    on_disable=on_disable,
)
