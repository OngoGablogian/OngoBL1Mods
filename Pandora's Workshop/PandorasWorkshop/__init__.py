"""Pandora's Workshop: consolidated native in-game gear editor."""

from __future__ import annotations

import json
import html
import math
import re
import time
import zlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import unrealsdk
from mods_base import ButtonOption, EInputEvent, NestedOption, ObjectFlags, SliderOption, get_pc, hook, keybind, build_mod
from unrealsdk import logging
from unrealsdk.hooks import Block, Type
from unrealsdk.unreal import BoundFunction, UObject, WrappedStruct
from willow1_mod_menu.options import create_nested_options_menu, draw_custom_menu
from willow1_mod_menu import options as menu_options
from willow1_mod_menu.util import find_focused_item
from ui_utils import TrainingBox
from ui_utils.clipboard import clipboard_copy, clipboard_paste

from . import core, native_item_card_fix
from .item_parts import ITEM_NAME_PART_PATHS, ITEM_PART_PATHS
from .part_metadata import PART_METADATA


try:
    _item_card_fix_status = native_item_card_fix.install()
except Exception as exc:
    logging.error(f"Pandora's Workshop: item-card crash protection unavailable: {exc}")

_pending_open = False
_opening = False
_active_pause_menu: UObject | None = None
_workshop_root_screen: UObject | None = None
_equipped_header: ButtonOption | None = None
_pending_requip: UObject | None = None
_pending_requip_ticks = 0
_pending_requip_stage = 0
_pending_requip_previous: UObject | None = None
_pending_requip_slot = 0
_pending_requip_backpack: UObject | None = None
_pending_requip_readied: UObject | None = None
_pending_duplicate_source: UObject | None = None
_pending_duplicate_result: UObject | None = None
_search_state: tuple[str, str, list[UObject], str, bool | str | None] | None = None
_search_query = ""
_copied_part: UObject | None = None
_comparison_part: UObject | None = None
_active_part_destination: tuple[str, str, list[UObject]] | None = None
_active_preview_part: UObject | None = None
_control_down = False
_pending_menu_close: UObject | None = None
_pending_menu_close_ticks = 0
_pending_discard_confirmation_ticks = 0
_suppress_escape_until_release = False
_suppress_search_accept_until_release = False
_pending_discard_after_release = False
_pending_layout_ticks = 0
_layout_signature = None
_layout_markers_pending = False
_pending_card_open_ticks = 0
_item_target: UObject | None = None
_item_original: dict[str, Any] = {}
_item_catalogs: dict[str, list[UObject]] = {}
_active_item_destination: tuple[str, str, list[UObject]] | None = None
_slot_options: dict[str, list[tuple[str, Any]]] = {}
_item_slot_options: dict[str, list[tuple[str, Any]]] = {}
_part_buttons: dict[str, list[tuple[UObject, ButtonOption]]] = {}
_preview_options: dict[str, list[tuple[UObject, ButtonOption]]] = {}
_global_search_options: list[tuple[UObject, ButtonOption]] = []
_grade_header: NestedOption | None = None
_grade_sliders: dict[str, SliderOption] = {}
_definition_options: dict[str, list[tuple[str, ButtonOption]]] = {}
_item_selector_rows: dict[str, ButtonOption] = {}
_item_selected_row: ButtonOption | None = None
_item_grade_rows: dict[str, SliderOption] = {}
_item_definition_options: dict[str, list[tuple[str, ButtonOption]]] = {}
_definition_choice_options: dict[str, list[tuple[UObject, ButtonOption]]] = {}
_item_definition_choice_options: dict[str, list[tuple[UObject, ButtonOption]]] = {}
_workshop_card_active = False
_workshop_card_requested = False
_workshop_card_movie: UObject | None = None
_workshop_card_mesh: UObject | None = None
_workshop_thumbnail: UObject | None = None
_workshop_thumbnail_manager: UObject | None = None
_workshop_mesh_original_flags: int | None = None
_workshop_card_saved_look: UObject | None = None
_workshop_card_saved_comparison: tuple[Any, Any] | None = None
_workshop_card_original_flags: int | None = None
_card_startup_ticks = 0
_card_modal_hidden = False


WORKSHOP_VERSION = "1.1.0"
CARD_PREVIEW_ENABLED = True
DEBUG_LOGGING = False
_part_change_busy = False
_last_part_change_time = 0.0
_pending_part_change: tuple[Any, ...] | None = None
NATIVE_CARD_ROOTS = ("inventory", "_root.inventory")
# Enhanced's visible Friends box is the pause SWF's partyMC clip.  Keep the
# older aliases as harmless fallbacks for alternate aspect/platform movies.
FRIENDS_ROOTS = (
    "partyMC", "_level0.partyMC", "menu.partyMC",
    "friends", "_level0.friends", "menu.friends",
)


SLOT_CATEGORY = {
    "Body": "Bodies", "Grip": "Grips", "Magazine": "Magazines",
    "Barrel": "Barrels", "Sight": "Sights", "Stock": "Stocks",
    "Action": "Actions", "Accessory": "Accessories",
    "Material": "Materials", "Prefix": "Prefixes", "Title": "Titles",
}

ITEM_FIELDS = (
    "ItemDefinition", "BalanceDefinition", "ManufacturerDefinition",
    "ManufacturerGradeIndex", "BodyItemPartDefinition",
    "LeftSideItemPartDefinition", "RightSideItemPartDefinition",
    "MaterialItemPartDefinition", "PrefixItemNamePartDefinition",
    "TitleItemNamePartDefinition",
)

ITEM_SLOTS = (
    ("Body", "BodyItemPartDefinition", "BodyParts", "BodyPartData"),
    ("Left Side", "LeftSideItemPartDefinition", "LeftSideParts", "LeftSidePartData"),
    ("Right Side", "RightSideItemPartDefinition", "RightSideParts", "RightSidePartData"),
    ("Material", "MaterialItemPartDefinition", "MaterialParts", "MaterialPartData"),
    ("Prefix", "PrefixItemNamePartDefinition", "PrefixList", ""),
    ("Title", "TitleItemNamePartDefinition", "TitleList", ""),
)

FRIENDLY_STATS = {
    "WeaponDamage": "Damage",
    "WeaponDamageNormalized": "Normalized Damage",
    "WeaponFireRate": "Rate of Fire",
    "PlayerCriticalHitBonus": "Critical-hit Damage",
    "WeaponReloadSpeed": "Reload Speed",
    "WeaponSpread": "Spread",
    "AccuracyMaxValue": "Maximum Spread",
    "AccuracyMinValue": "Minimum Spread",
    "AccuracyCurrentValue": "Current Accuracy",
    "AccuracyOnIdleRegenerationRate": "Accuracy Recovery",
    "AccuracyActiveRegenerationRate": "Active Accuracy Recovery",
    "WeaponPerShotAccuracyImpulse": "Shot Bloom",
    "WeaponClipSize": "Magazine Capacity",
    "WeaponProjectilesPerShot": "Projectiles per Shot",
    "WeaponAutomaticBurstCount": "Automatic Burst Count",
    "WeaponShotCost": "Ammo Cost per Shot",
    "WeaponKnockback": "Knockback",
    "WeaponProjectileSpeedMultiplier": "Projectile Speed",
    "WeaponEquipTime": "Equip Time",
    "WeaponPutDownTime": "Put-down Time",
    "WeaponZoomEndFOV": "Magnification",
    "WeaponMeleeDamage": "Weapon Melee Damage",
    "InstigatedMeleeDamageModifier": "Melee Damage",
    "PercentChanceInstigatedBulletDmgIgnoresShields": "Chance to Ignore Shields",
    "MeleeHealthStealPercent": "Melee Health Steal",
    "PlayerCurrentWeaponAmmoRegenerationMultiplier": "Ammo Regeneration",
    "FootSpeed": "Movement Speed",
    "TotalEncumbrance": "Encumbrance",
    "WeaponLevel": "Weapon Level",
    "ShieldMaxValue": "Shield Capacity",
    "ShieldOnIdleRegenerationDelay": "Recharge Delay",
    "ShieldOnIdleRegenerationRate": "Recharge Rate",
}


def _friendly_stat(name: str) -> str:
    return FRIENDLY_STATS.get(name, re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name))


def _number(value: float) -> str:
    rendered = f"{value:.2f}".rstrip("0").rstrip(".")
    return "+" + rendered if value > 0 else rendered


def _same_object(left: UObject | None, right: UObject | None) -> bool:
    """Compare Unreal objects by canonical path, not transient Python wrapper identity."""
    if left is None or right is None:
        return left is None and right is None
    try:
        left_path = core._short(left).lower()
        right_path = core._short(right).lower()
        left_path = core.ENHANCED_PART_ALIASES.get(left_path, left_path).lower()
        right_path = core.ENHANCED_PART_ALIASES.get(right_path, right_path).lower()
        return left_path == right_path
    except Exception:
        return left == right


def _format_effect(raw: str, part_path: str = "") -> str:
    """Translate Willow's modifier pipeline terms into player-facing text."""
    context = ""
    for prefix in ("While Zoomed/External: ", "While Zoomed: ", "External: "):
        if raw.startswith(prefix):
            context = "While Zoomed: " if prefix.startswith("While Zoomed") else ""
            raw = raw[len(prefix):]
            break
    dynamic = raw.endswith(" [dynamic]")
    if dynamic:
        raw = raw.removesuffix(" [dynamic]")
    match = re.fullmatch(r"Modify (.+?) by (.*?) \((PreAdd|PostAdd|Scale)\)", raw)
    if match is None:
        return context + raw
    stat, raw_value, operation = match.groups()
    label = _friendly_stat(stat)
    if not raw_value.strip():
        return f"{context}{label}: Level-scaled value"
    try:
        value = float(raw_value)
    except ValueError:
        return f"{context}{label}: {raw_value}"
    if value == 0:
        if stat == "WeaponClipSize":
            return f"{context}{label}: Base capacity unchanged"
        return f"{context}{label}: No change"
    if operation == "Scale" and stat in {"WeaponZoomEndFOV", "FootSpeed"}:
        # Negative scale contributions use a reciprocal, not negative speed.
        factor = 1.0 + value if value >= 0 else 1.0 / (1.0 - value)
        if stat == "WeaponZoomEndFOV":
            return f"{context}Magnification: {1.0 / factor:.2f}x (part alone)"
        return f"{context}{_number((factor - 1.0) * 100)}% Movement Speed"
    path = part_path.lower()
    # Enhanced stores WeaponFireRate in FireInterval: smaller is faster.
    # A scaled interval must be inverted to express rounds-per-second change.
    if stat == "WeaponFireRate":
        if operation == "Scale" and 1.0 + value > 0:
            rate_change = (1.0 / (1.0 + value) - 1.0) * 100.0
            note = "faster" if rate_change > 0 else "slower"
            return f"{context}{label}: {_number(rate_change)}% ({note}; interval modifier alone){' (dynamic)' if dynamic else ''}"
        rendered_interval = _number(value * 100) + "%" if operation == "Scale" else _number(value) + " s"
        note = "faster firing" if value < 0 else "slower firing"
        return f"{context}Shot Interval: {rendered_interval} ({note})"
    inverse_speed = stat == "WeaponReloadSpeed"
    display_value = -value if inverse_speed else value
    if "barrel4_jakobs_skullmasher" in path and stat == "WeaponDamage":
        display_value = abs(value)
    rendered = _number(display_value * 100) + "%" if operation == "Scale" else _number(display_value)
    note = ""
    if stat in {"WeaponSpread", "AccuracyMaxValue", "AccuracyMinValue", "WeaponPerShotAccuracyImpulse"}:
        # These modify spread/bloom, not the accuracy percentage on the card.
        # Values below -100% are contributions to a combined modifier, not a
        # promise of negative final spread or more than perfect accuracy.
        factor = 1.0 + value if value >= 0 else 1.0 / (1.0 - value)
        display = (factor - 1.0) * 100 if operation == "Scale" else value
        direction = "Reduction" if display < 0 else "Increase"
        amount = _number(abs(display)).lstrip("+") + ("%" if operation == "Scale" else "")
        return f"{context}{amount} {label} {direction}{' (dynamic)' if dynamic else ''}"
    elif stat in {"WeaponEquipTime", "WeaponPutDownTime", "TotalEncumbrance"}:
        note = " (slower)" if value > 0 else " (faster)" if value < 0 else ""
    elif stat == "ShieldOnIdleRegenerationDelay":
        note = " (slower recharge)" if value > 0 else " (faster recharge)" if value < 0 else ""
    elif stat == "ShieldOnIdleRegenerationRate":
        note = " (faster recharge)" if value > 0 else " (slower recharge)" if value < 0 else ""
    elif stat in {"WeaponFireRate", "WeaponReloadSpeed"}:
        note = " (faster)" if display_value > 0 else " (slower)" if display_value < 0 else ""
    return f"{context}{label}: {rendered}{note}{' (dynamic)' if dynamic else ''}"


def _format_basic(raw: str) -> str:
    key, separator, value = raw.partition("=")
    if not separator:
        return raw
    if key == "CashValueModifier":
        return f"Cash Value: x{value}"
    if key == "TechLevelIncrease":
        return f"Elemental Tech Level: {value if value.startswith('-') else '+' + value.lstrip('+')}"
    if key == "PartNumberAddend":
        return f"Part Number Addend: {value if value.startswith('-') else '+' + value.lstrip('+')}"
    if key == "PartType":
        value = value.split(".")[-1].removeprefix("WP_").removeprefix("IP_")
        return "Part Type: " + value.replace("_", " ").title()
    return f"{_friendly_stat(key)}: {value}"


def _format_item_effect(raw: str, part_path: str = "") -> str:
    """Render item effects compactly without exposing engine-only prefixes."""
    normalized = raw
    for prefix in ("While Zoomed/External: ", "While Zoomed: ", "External: "):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
            break
    missing_value = re.fullmatch(
        r"Modify (.+?) by\s*\((PreAdd|PostAdd|Scale)\)", normalized
    )
    if missing_value is not None:
        stat, operation = missing_value.groups()
        label = _friendly_stat(stat)
        wording = "Level-scaled multiplier" if operation == "Scale" else "Level-scaled bonus"
        return f"{label}: {wording}"
    rendered = _format_effect(raw, part_path)
    for prefix in ("While Zoomed/External: ", "While Zoomed: ", "External: "):
        if rendered.startswith(prefix):
            rendered = rendered[len(prefix):]
            break
    return rendered.replace("dynamic formula", "level-scaled modifier").replace(" (dynamic)", "")


def _button(label: str, tip: str, action: Any) -> ButtonOption:
    # Descriptions become separate selectable "(...)" rows in this renderer.
    return ButtonOption(label, on_press=lambda _option: action())


def _detail_button(text: str, title: str) -> ButtonOption:
    """Keep previews to one clean row; a click reveals any clipped full text."""
    label = text if len(text) <= 44 else text[:41].rstrip() + "..."
    detail = text
    if "%" in text or "Magnification:" in text:
        detail += "\n\nEffect of this part alone. Other parts and bonuses can change the final result."
    return _button(label, "", lambda: TrainingBox(title=title, message=detail).show())


def _part_display_name(part: UObject) -> str:
    """Use the unambiguous database leaf, never a tiny naming contribution."""
    return core._leaf(part)


def _overview_part_name(part: UObject | None) -> str:
    """Identify generic leaves such as mag5/body5 by their source family."""
    if part is None:
        return "None"
    leaf = core._leaf(part)
    family = core._family(part)
    if family and family not in ("Unknown", "Shared / Materials"):
        return f"{family} - {leaf}"
    return leaf


def _part_row_label(part: UObject, current: bool = False) -> str:
    """Fit marked part names inside Enhanced's fixed-width highlighted row."""
    # Selection rows need the unique database leaf.  Several materials expose
    # deliberately tiny PartName values such as ``-A`` and ``-B``; those are
    # useful on an item card, but ambiguous in a part browser.
    name = core._leaf(part)
    prefix = "[CURRENT] " if current else ""
    # The selected-row mask fails unusually once the label reaches its limit:
    # Bone Shredder displayed only the marker instead of clipping normally.
    available = 38 - len(prefix)
    if len(name) > available:
        name = name[: max(1, available - 3)].rstrip() + "..."
    return prefix + name


def _search_result_label(part: UObject) -> str:
    """Fit the two useful identifiers inside Enhanced's narrow menu row."""
    current = False
    if core._session is not None:
        current = any(
            _same_object(part, getattr(core._session.weapon.DefinitionData, field, None))
            for _label, field, _collection in core.SLOTS
        )
    if _item_target is not None:
        current = current or any(
            _same_object(part, getattr(_item_target.DefinitionData, field, None))
            for field in ITEM_FIELDS
        )
    leaf = core._leaf(part)
    # The stock selection highlight clips a long CURRENT label before its
    # distinguishing leaf.  Once marked current the destination weapon family
    # is already known, so spend the row width on the exact part name.
    if current:
        return f"[CURRENT] {leaf}"
    return _search_result_base_label(part)


def _search_result_base_label(part: UObject) -> str:
    """Return a stable unmarked search label for native-row matching."""
    # Full package paths all clip before the distinguishing leaf in the stock
    # pause SWF. Family + leaf preserves both the weapon type and exact part.
    leaf = core._leaf(part)
    family = core._family(part)
    category = core._declared_category(part)
    if "shared" in family.lower() or category in ("Prefixes", "Titles"):
        family = {"Materials": "Material", "Prefixes": "Prefix", "Titles": "Title"}.get(category, family)
    if family == "Material":
        return leaf
    return f"{family}: {leaf}"


def _global_search_button(part: UObject, complete: bool, *, preview: bool = False) -> ButtonOption:
    option = _button(
        _search_result_label(part),
        "",
        lambda: (
            _open_global_result(part, complete)
            if preview
            else _choose_search_destination(part, complete)
        ),
    )
    _global_search_options.append((part, option))
    return option


def _refresh_global_search_options() -> None:
    for part, option in _global_search_options:
        option.display_name = _search_result_label(part)


def _native_row_limit() -> int:
    """Cover the full active list, including rows beyond the old 80-row cap."""
    counts = [len(_global_search_options)]
    for destination in (_active_part_destination, _active_item_destination):
        if destination is not None:
            counts.append(len(destination[2]))
    return max(80, max(counts) + 16)


def _refresh_native_labeled_row(previous: str, rendered: str) -> None:
    """Update a row already drawn by the pause Scaleform movie."""
    menu = _active_pause_menu
    if menu is None:
        return
    try:
        focused = find_focused_item(menu)
        match = re.match(r"^(.*\.item)\d+$", focused)
        if match is None:
            return
        base = match.group(1)
        for index in range(_native_row_limit()):
            path = f"{base}{index}.mLabel.text"
            current = str(menu.GetVariableString(path))
            if current == previous:
                menu.SetVariableString(path, rendered)
    except Exception as exc:
        logging.info(f"Pandora's Workshop could not refresh native row: {exc}")


def _is_internal_test_part(part: UObject) -> bool:
    """Internal Gearbox prototype families belong only in Pandora's Box."""
    path = core._short(part).lower()
    return (
        "gd_weap_combat_shotgun_test_j." in path
        or "gd_weap_combat_shotgun_toon." in path
    )


def _weapon_preview_basics(part: UObject, basics: tuple[str, ...]) -> list[str]:
    """Replace the redundant WP enum with the source weapon family."""
    rendered = [f"Weapon Type: {core._family(part)}"]
    rendered.extend(_format_basic(line) for line in basics if not line.startswith("PartType="))
    return rendered


def _apply_part(
    slot_label: str,
    field: str,
    part: UObject,
    visible_parts: list[UObject],
    full_labels: bool = False,
) -> None:
    """Leave Scaleform input before applying the latest requested edit."""
    global _pending_part_change
    if core._session is not None:
        _pending_part_change = (core._session, slot_label, field, part, visible_parts, full_labels)


def _apply_part_now(
    slot_label: str,
    field: str,
    part: UObject,
    visible_parts: list[UObject],
    full_labels: bool = False,
) -> None:
    """Apply a part without reopening the legacy OptionBox UI."""
    global _part_change_busy, _last_part_change_time, _pending_part_change
    session = core._session
    if session is None:
        return
    if _part_change_busy or time.monotonic() - _last_part_change_time < 0.15:
        _pending_part_change = (session, slot_label, field, part, visible_parts, full_labels)
        return
    _pending_part_change = None
    _part_change_busy = True
    try:
        resolved = core._resolve_catalog_part(part)
        if resolved is None:
            core._notify(f"Could not resolve {core._short(part)} right now; see SDK log.")
            return
        if core._short(resolved).lower() == "gd_weap_shared_materialparts.manufacturermaterials.material_corraza_1":
            core._notify("Corraza material is blocked: it caused a native weapon initialization crash.")
            return
        _record_part_change(field, part, resolved, "Before weapon rebuild")
        setattr(session.weapon.DefinitionData, field, resolved)
        session.dirty = True
        core._rebuild(
            session.weapon,
            lambda phase: _record_part_change(field, part, resolved, phase),
            reinitialize=True,
            material_only=field == "MaterialPartDefinition",
        )
        _record_part_change(field, part, resolved, "Weapon rebuild completed")
        _refresh_option_models(field)
        _refresh_global_search_options()
        _refresh_visible_part_rows(field, visible_parts, full_labels)
        _refresh_equipped_header()
        _refresh_workshop_card()
        core._notify(f"{slot_label}: {core._leaf(part)}")
        _record_part_change(field, part, resolved, "Change completed")
    except Exception as exc:
        logging.error(f"Pandora's Workshop UI could not set {field}: {exc}")
        core._notify(f"Could not apply {slot_label}; see SDK log.")
    finally:
        _part_change_busy = False
        _last_part_change_time = time.monotonic()


def _record_part_change(field: str, part: Any, resolved: Any, phase: str) -> None:
    """Keep one bounded crash breadcrumb before entering native rebuild code."""
    if not DEBUG_LOGGING:
        return
    try:
        folder = Path.home() / "PandorasWorkshop"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "last_part_change.txt").write_text(
            f"Workshop {WORKSHOP_VERSION}\nPhase: {phase}\nSlot: {field}\n"
            f"Catalog: {core._short(part)}\nResolved: {core._short(resolved)}\n"
            f"Weapon: {core._short(core._session.weapon) if core._session is not None else 'None'}\n"
            f"Owner: {core._short(core._session.weapon.Owner) if core._session is not None else 'None'}\n",
            encoding="utf-8",
        )
    except Exception as exc:
        logging.info(f"Pandora's Workshop could not write crash breadcrumb: {exc}")


def _clear_weapon_slot(slot_label: str, field: str, visible_parts: list[UObject]) -> None:
    """Blank the active definition field without deleting any inventory item."""
    session = core._session
    if session is None or not field:
        return
    if not _weapon_slot_may_be_empty(session, field):
        core._notify(f"Delete blocked: {slot_label} cannot be empty on this weapon.")
        return
    try:
        setattr(session.weapon.DefinitionData, field, None)
        session.dirty = True
        core._rebuild(session.weapon)
        _refresh_option_models(field)
        _refresh_global_search_options()
        _refresh_visible_part_rows(field, visible_parts)
        _refresh_equipped_header()
        _refresh_workshop_card()
        core._notify(f"{slot_label} cleared.")
    except Exception as exc:
        logging.error(f"Pandora's Workshop could not clear {field}: {exc}")
        core._notify(f"Could not clear {slot_label}; see SDK log.")


def _part_button(slot_label: str, field: str, part: UObject, visible_parts: list[UObject]) -> ButtonOption:
    current = getattr(core._session.weapon.DefinitionData, field, None)
    option = _button(
        _part_row_label(part, _same_object(part, current)),
        "",
        lambda: _apply_part(slot_label, field, part, visible_parts),
    )
    _part_buttons.setdefault(field, []).append((part, option))
    return option


def _metadata_for(
    part: UObject,
    context: UObject | None = None,
) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    """Return live Enhanced data, with WillowTree retained only as fallback."""
    path = core._short(part)
    direct = PART_METADATA.get(path)
    slogan, fallback_basics, fallback_effects = direct or ("", (), ())
    if isinstance(part, core.CatalogPart):
        live_basics, live_effects = (), ()
    else:
        live_basics, live_effects = _live_part_data(
            part, fallback_basics, fallback_effects, context
        )
    basics = live_basics or fallback_basics
    effects = live_effects or fallback_effects
    # PartName is the internal item-card naming contribution. It is useful to
    # the game when assembling the weapon's final name, but it is redundant in
    # every Workshop part preview because the selected object is already shown
    # in the preview header. Never leak it as a selectable metadata row.
    basics = tuple(line for line in basics if not line.startswith("PartName="))
    if slogan:
        return slogan, basics, effects

    # Name-part rows must only use their own descriptor.  The association
    # below exists for physical unique parts (for example Revolution's
    # magazine), and allowing it to run for titles made every nearby SMG title
    # match the structural token "Title" and inherit Wildcat's slogan.
    if ".title." in path.lower() or ".prefix." in path.lower():
        return "", basics, effects

    # A number of unique physical parts use the same identifying word as a
    # title definition which owns the red-text descriptor (Revolution is the
    # canonical example). Associate those records without hard-coding guns.
    leaf_tokens = {
        token.lower() for token in re.split(r"[^A-Za-z0-9]+", core._leaf(part))
        if len(token) >= 4 and token.lower() not in {"barrel", "material", "unique", "sight", "title", "prefix"}
    }
    if leaf_tokens:
        family = path.rsplit(".", 2)[0].lower()
        for candidate, record in PART_METADATA.items():
            if not record[0] or ".title." not in candidate.lower():
                continue
            candidate_tokens = {
                token.lower() for token in re.split(r"[^A-Za-z0-9]+", candidate)
                if len(token) >= 4
            }
            if family.split(".", 1)[0] == candidate.lower().split(".", 1)[0] and leaf_tokens & candidate_tokens:
                return record[0], basics, effects
    return "", basics, effects


def _fallback_basic(attribute: str, fallback_basics: tuple[str, ...]) -> str | None:
    prefix = attribute + "="
    return next((line for line in fallback_basics if line.startswith(prefix)), None)


def _live_basic_line(attribute: str, value: Any, fallback_basics: tuple[str, ...]) -> str | None:
    """Render scalar properties and reject UE initialization structs as fixed values."""
    if attribute == "PartType":
        enum_name = getattr(value, "name", None)
        if enum_name:
            return f"{attribute}={enum_name}"
        # BL1E exposes this enum as an integer on some SDK builds. Prefer the
        # named value from the database to an opaque (and misleading) zero.
        return _fallback_basic(attribute, fallback_basics)
    if isinstance(value, (str, int, float, bool)):
        return f"{attribute}={value}"
    # CashValueModifier and Rarity are AttributeInitializationData structs in
    # Enhanced. Their displayed BaseValueConstant is not necessarily their
    # evaluated value; use the known record rather than dumping the struct.
    return _fallback_basic(attribute, fallback_basics)


def _live_part_data(
    part: UObject,
    fallback_basics: tuple[str, ...],
    fallback_effects: tuple[str, ...],
    context: UObject | None = None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Read the authoritative WeaponPartDefinition fields from Enhanced."""
    basics: list[str] = []
    path = core._short(part).lower()
    is_name_part = ".prefix." in path or ".prefix_" in path or ".title." in path or ".title_" in path
    attributes = ("CashValueModifier", "Rarity") if is_name_part else (
        "PartName", "CashValueModifier", "TechLevelIncrease", "PartNumberAddend", "Rarity", "PartType"
    )
    for attribute in attributes:
        try:
            value = getattr(part, attribute)
        except Exception:
            continue
        if value is None or value == "":
            continue
        line = _live_basic_line(attribute, value, fallback_basics)
        if line is not None and line not in basics:
            basics.append(line)

    effects: list[str] = []
    groups = (
        ("WeaponAttributeEffects", ""),
        ("ItemAttributeEffects", ""),
        ("ExternalAttributeEffects", "External: "),
        ("ZoomWeaponAttributeEffects", "While Zoomed: "),
        ("ZoomExternalAttributeEffects", "While Zoomed/External: "),
    )
    for property_name, prefix in groups:
        try:
            entries = list(getattr(part, property_name))
        except Exception:
            continue
        for effect in entries:
            line = _live_effect_line(effect, fallback_effects, context)
            if line:
                effects.append(prefix + line)
    return tuple(basics), tuple(effects)


def _evaluate_initialization(data: Any, context: UObject | None) -> float | None:
    """Ask Enhanced to evaluate an AttributeInitializationData formula."""
    if context is None:
        return None
    try:
        try:
            klass = unrealsdk.find_class("Engine.AttributeInitializationDefinition")
        except Exception:
            klass = unrealsdk.find_class("AttributeInitializationDefinition")
        evaluator = getattr(klass, "ClassDefaultObject", None)
        if evaluator is None:
            return None
        return float(evaluator.EvaluateInitializationData(data, context))
    except Exception as exc:
        logging.info(f"Pandora's Workshop could not evaluate an item formula: {exc}")
        return None


def _live_effect_line(
    effect: Any,
    fallback_effects: tuple[str, ...],
    context: UObject | None = None,
) -> str:
    try:
        attribute = core._leaf(effect.AttributeToModify)
        operation_value = effect.ModifierType
        operation_text = getattr(operation_value, "name", str(operation_value)).split(".")[-1]
        operation = operation_text.removeprefix("MT_")
        if operation.isdigit():
            operation = {"0": "Scale", "1": "PreAdd", "2": "PostAdd"}.get(operation, operation)
        modifier = effect.BaseModifierValue
        constant = float(modifier.BaseValueConstant)
        scale = float(getattr(modifier, "BaseValueScaleConstant", 1.0))
        source_attribute = getattr(modifier, "BaseValueAttribute", None)
        initializer = getattr(modifier, "InitializationDefinition", None)
        if source_attribute is None and initializer is None:
            return f"Modify {attribute} by {constant * scale:g} ({operation})"

        evaluated = _evaluate_initialization(modifier, context)
        if evaluated is not None:
            return f"Modify {attribute} by {evaluated:g} ({operation})"

        # Dynamic formulas can depend on level, manufacturer, or INI-backed
        # random ranges.  Reuse WillowTree's evaluated line only when it
        # describes this exact attribute/operation; never invent a number.
        needle = f"Modify {attribute} by "
        for fallback in fallback_effects:
            if fallback.startswith(needle) and fallback.endswith(f"({operation})"):
                return fallback + " [dynamic]"
        return f"Modify {attribute} by dynamic formula ({operation})"
    except Exception as exc:
        logging.info(f"Pandora's Workshop could not decode one live part effect: {exc}")
        return ""


def _open_part_preview(
    slot_label: str,
    field: str,
    part: UObject,
    visible_parts: list[UObject],
    full_labels: bool = False,
) -> None:
    """Build preview content only when opened, preventing stale title metadata rows."""
    global _active_preview_part
    _active_preview_part = part
    _refresh_workshop_card()
    live_part = core._resolve_catalog_part(part, quiet=True) or part
    context = None if core._session is None else core._session.weapon
    slogan, basics, effects = _metadata_for(live_part, context)
    detail_title = _part_display_name(part)
    details: list[Any] = [
        _button(
            "Apply This Part", "",
            lambda: _apply_part(slot_label, field, part, visible_parts, full_labels),
        ),
        _button("Copy This Part", "", lambda: _copy_part(part)),
        _button("Set as Comparison Part", "", lambda: _set_comparison_part(part)),
    ]
    if _comparison_part is not None and not _same_object(part, _comparison_part):
        details.append(_button(
            f"Compare with {core._leaf(_comparison_part)}",
            "",
            lambda: _open_part_comparison(part, _comparison_part),
        ))
    if slogan:
        details.append(_detail_button(f'"{slogan}"', detail_title))
    for rendered in _weapon_preview_basics(part, basics):
        details.append(_detail_button(rendered, detail_title))
    for line in effects:
        rendered = _format_effect(line, core._short(part))
        details.append(_detail_button(rendered, detail_title))
    if len(details) == 1:
        details.append(_button("No WillowTree metadata is available for this part.", "", lambda: None))
    _open_nested(detail_title, details)


def _copy_part(part: UObject | None) -> None:
    global _copied_part
    if part is None:
        core._notify("There is no part in this slot to copy.")
        return
    _copied_part = part
    core._notify(f"Copied part: {core._leaf(part)}")


WEAPON_SLOT_COLLECTIONS = {field: collection for _label, field, collection in core.SLOTS}
# Native validation accepted an empty prefix/title for every one of the 330
# type/manufacturer/balance combinations in native_compatibility.py.
ALWAYS_EMPTY_OK_WEAPON_FIELDS = ("PrefixPartDefinition", "TitlePartDefinition")


def _weapon_part_is_valid(session: Any, field: str, part: Any) -> bool:
    """True when the part appears in this slot's Valid list for the weapon."""
    collection = WEAPON_SLOT_COLLECTIONS.get(field)
    if collection is None or part is None:
        return False
    return any(_same_object(part, candidate) for candidate in core._valid_parts(session, collection))


def _weapon_slot_may_be_empty(session: Any, field: str) -> bool:
    """True when the game accepts this slot empty for this weapon."""
    return field in ALWAYS_EMPTY_OK_WEAPON_FIELDS or core._valid_empty_slot(session, field)


def _paste_part(slot_label: str, field: str, visible_parts: list[UObject]) -> None:
    if _copied_part is None:
        core._notify("Copy a part first.")
        return
    session = core._session
    if session is None:
        return
    if not _weapon_part_is_valid(session, field, _copied_part):
        core._notify(f"Paste blocked: {core._leaf(_copied_part)} is not a Valid {slot_label} part for this weapon.")
        return
    _apply_part(slot_label, field, _copied_part, visible_parts)


def _set_comparison_part(part: UObject) -> None:
    global _comparison_part
    _comparison_part = part
    core._notify(f"Comparison part: {core._leaf(part)}")


def _comparison_values(part: UObject) -> dict[str, str]:
    slogan, basics, effects = _metadata_for(part)
    values: dict[str, str] = {}
    if slogan:
        values["Descriptor"] = slogan
    for raw in basics:
        rendered = _format_basic(raw)
        key, separator, value = rendered.partition(":")
        values[key] = value.strip() if separator else rendered
    for raw in effects:
        rendered = _format_effect(raw, core._short(part))
        key, separator, value = rendered.partition(":")
        values[key] = value.strip() if separator else rendered
    return values


def _open_part_comparison(left: UObject, right: UObject) -> None:
    left_values = _comparison_values(left)
    right_values = _comparison_values(right)
    keys = list(dict.fromkeys((*left_values.keys(), *right_values.keys())))
    children: list[Any] = [
        _detail_button(f"A: {core._leaf(left)}", "Comparison"),
        _detail_button(f"B: {core._leaf(right)}", "Comparison"),
    ]
    for key in keys:
        children.append(_detail_button(
            f"{key}: {left_values.get(key, '—')}  |  {right_values.get(key, '—')}",
            "Part Comparison",
        ))
    _open_nested("PART COMPARISON - A | B", children)


def _part_preview(slot_label: str, field: str, part: UObject, visible_parts: list[UObject]) -> ButtonOption:
    current = core._session is not None and _same_object(
        part,
        getattr(core._session.weapon.DefinitionData, field, None),
    )
    option = _button(
        _part_row_label(part, current),
        "",
        lambda: _open_part_preview(slot_label, field, part, visible_parts),
    )
    _preview_options.setdefault(field, []).append((part, option))
    return option


def _refresh_option_models(field: str) -> None:
    if core._session is None:
        return
    current = getattr(core._session.weapon.DefinitionData, field, None)
    current_leaf = _overview_part_name(current)
    for label, option in _slot_options.get(field, []):
        previous = option.display_name
        option.display_name = f"{label}: {current_leaf}"
        _refresh_native_labeled_row(previous, option.display_name)
    for part, option in _part_buttons.get(field, []):
        option.display_name = _part_row_label(part, _same_object(part, current))
    for part, option in _preview_options.get(field, []):
        option.display_name = _part_row_label(part, _same_object(part, current))


def _refresh_equipped_header() -> None:
    if core._session is None or _equipped_header is None:
        return
    _equipped_header.display_name = f"Selected Weapon: {core._weapon_name(core._session.weapon)}"


def _refresh_visible_part_rows(
    field: str,
    visible_parts: list[UObject],
    full_labels: bool = False,
) -> None:
    """Move the [CURRENT] marker in the list which is presently visible."""
    if _active_pause_menu is None or core._session is None:
        return
    focused = find_focused_item(_active_pause_menu)
    match = re.match(r"^(.*\.item)\d+$", focused)
    if match is None:
        return
    base = match.group(1)
    current = getattr(core._session.weapon.DefinitionData, field, None)
    # Match what is actually drawn instead of relying on fixed row positions.
    # Search and Preview can now move independently without shifting CURRENT
    # markers onto the wrong part.
    for index in range(max(_native_row_limit(), len(visible_parts) + 16)):
        path = f"{base}{index}.mLabel.text"
        shown = str(_active_pause_menu.GetVariableString(path))
        if not shown:
            continue
        for part in visible_parts:
            candidates = {
                core._leaf(part),
                _part_row_label(part, False),
                _part_row_label(part, True),
                _search_result_base_label(part),
                f"[CURRENT] {core._leaf(part)}",
            }
            if shown in candidates:
                _active_pause_menu.SetVariableString(
                    path,
                    _search_result_label(part)
                    if full_labels
                    else _part_row_label(part, _same_object(part, current)),
                )
                break


def _part_children(
    slot_label: str,
    field: str,
    parts: list[UObject],
    *,
    include_search: bool = True,
    full_labels: bool = False,
) -> list[Any]:
    global _active_part_destination, _active_item_destination, _active_preview_part
    _active_part_destination = (slot_label, field, parts)
    _active_item_destination = None
    _active_preview_part = None
    children: list[Any] = []
    current = None if core._session is None else getattr(core._session.weapon.DefinitionData, field, None)
    if include_search:
        children.append(_button(
            "Search Parts",
            "Type a search phrase, then press Enter.",
            lambda: _begin_search(slot_label, field, parts),
        ))
    children.append(
        NestedOption(
            "Preview Parts and Modifiers",
            [
                _button(
                    _search_result_label(part) if full_labels else _part_row_label(part, _same_object(part, current)),
                    "",
                    lambda part=part: _open_part_preview(
                        slot_label, field, part, parts, full_labels
                    ),
                )
                for part in parts
            ],
            description="",
        )
    )
    children.extend(
        [
            _button(
                _search_result_label(part) if full_labels else _part_row_label(part, _same_object(part, current)),
                "",
                lambda part=part: _apply_part(slot_label, field, part, parts, full_labels),
            )
            for part in parts
        ]
    )
    return children


def _begin_search(
    slot_label: str,
    field: str,
    source: list[UObject],
    complete: bool | str | None = None,
) -> None:
    global _search_state, _search_query
    if _active_pause_menu is None:
        return
    focused = find_focused_item(_active_pause_menu)
    _search_state = (slot_label, field, source, focused, complete)
    _search_query = ""
    _active_pause_menu.SetVariableString(f"{focused}.mLabel.text", "Search: _")
    core._notify("Type to search. Enter accepts; Escape cancels.")


def _show_search_results(
    slot_label: str,
    field: str,
    source: list[UObject],
    query: str,
    complete: bool | str | None = None,
) -> None:
    _global_search_options.clear()
    query = query.strip().lower()
    if not query:
        core._notify("Search cancelled: no text entered.")
        return
    matches = []
    category_query = {
        "body": "Bodies", "bodies": "Bodies",
        "grip": "Grips", "grips": "Grips",
        "mag": "Magazines", "magazine": "Magazines", "magazines": "Magazines",
        "barrel": "Barrels", "barrels": "Barrels",
        "sight": "Sights", "sights": "Sights",
        "stock": "Stocks", "stocks": "Stocks",
        "action": "Actions", "actions": "Actions",
        "accessory": "Accessories", "accessories": "Accessories",
        "material": "Materials", "materials": "Materials",
        "prefix": "Prefixes", "prefixes": "Prefixes",
        "title": "Titles", "titles": "Titles",
    }.get(query)
    for part in source:
        slogan, basics, effects = _metadata_for(part)
        searchable = " ".join((core._short(part), slogan, *basics, *effects)).lower()
        if (
            (category_query is not None and core._declared_category(part) == category_query)
            or (category_query is None and query in searchable)
        ):
            matches.append(part)
    if not matches:
        core._notify(f'No parts matched "{query}".')
        return
    if _active_pause_menu is not None:
        if complete == "item":
            children = _item_part_children(slot_label, field, matches)
        elif complete is not None:
            children = [
                NestedOption(
                    "Preview Parts and Modifiers",
                    [
                        _global_search_button(part, bool(complete), preview=True)
                        for part in matches
                    ],
                    description="",
                ),
                *[
                    _global_search_button(part, bool(complete))
                    for part in matches
                ],
            ]
        else:
            children = _part_children(slot_label, field, matches, include_search=False, full_labels=True)
        _open_nested(f'Search: "{query}" ({len(matches)})', children)


_KEY_CHARS = {
    "SpaceBar": " ", "Hyphen": "-", "Underscore": "_", "Period": ".",
    "Zero": "0", "One": "1", "Two": "2", "Three": "3", "Four": "4",
    "Five": "5", "Six": "6", "Seven": "7", "Eight": "8", "Nine": "9",
}


def _focused_label(menu: UObject) -> str:
    try:
        focused = find_focused_item(menu)
        return str(menu.GetVariableString(f"{focused}.mLabel.text"))
    except Exception:
        return ""


def _focused_slot_context(menu: UObject) -> tuple[str, str, str] | None:
    """Resolve a highlighted overview row to its actual definition field."""
    focused_label = _focused_label(menu)
    if not focused_label:
        return None
    for field, options in _slot_options.items():
        for label, option in options:
            if focused_label == option.display_name:
                return "weapon", label, field
    for field, options in _item_slot_options.items():
        for label, option in options:
            if focused_label == option.display_name:
                return "item", label, field
    return None


def _highlighted_part(menu: UObject, parts: list[UObject]) -> UObject | None:
    """Return the precise part under the cursor in a list/search screen."""
    focused_label = _focused_label(menu)
    if not focused_label:
        return None
    current = None
    if core._session is not None:
        for _label, field, _collection in core.SLOTS:
            try:
                candidate = getattr(core._session.weapon.DefinitionData, field, None)
                if any(_same_object(candidate, part) for part in parts):
                    current = candidate
                    break
            except Exception:
                pass
    for part in parts:
        labels = {
            _part_row_label(part, False),
            _part_row_label(part, _same_object(part, current)),
            _search_result_label(part),
        }
        if focused_label in labels:
            return part
    return None


def _cursor_on_part_row(menu: UObject, parts: list[UObject]) -> bool:
    """True when the highlighted row is one of these parts (CURRENT or not).

    The part-list context survives navigating back to other screens, so
    shortcuts that act on that list must check the cursor is really on it.
    """
    focused_label = _focused_label(menu)
    if not focused_label:
        return False
    return any(
        focused_label in (_part_row_label(part, False), _part_row_label(part, True), _search_result_label(part))
        for part in parts
    )


@hook("WillowGame.WillowGFxMenuPause:HandleInputKey", hook_type=Type.PRE)
def _search_input(
    obj: UObject,
    args: WrappedStruct,
    _ret: Any,
    _func: BoundFunction,
) -> tuple[type[Block], bool] | None:
    global _search_state, _search_query, _control_down, _pending_discard_confirmation_ticks
    global _suppress_escape_until_release, _pending_discard_after_release
    global _suppress_search_accept_until_release
    if obj != _active_pause_menu:
        return None
    key = str(args.ukey)
    if key in ("Enter", "XboxTypeS_A") and _suppress_search_accept_until_release:
        if args.uevent == EInputEvent.IE_Released:
            _suppress_search_accept_until_release = False
        return Block, True
    if key in ("Escape", "XboxTypeS_B") and _suppress_escape_until_release:
        if args.uevent == EInputEvent.IE_Released:
            _suppress_escape_until_release = False
            if _pending_discard_after_release:
                # The opening key has now completely left the pause movie.
                # Wait several UI ticks before creating the confirmation so
                # neither the press nor release can dismiss the new OptionBox.
                _pending_discard_after_release = False
                _pending_discard_confirmation_ticks = 6
        return Block, True
    if key in ("LeftControl", "RightControl", "LeftCtrl", "RightCtrl"):
        _control_down = args.uevent not in (EInputEvent.IE_Released,)
        return None
    if _search_state is None:
        if (
            args.uevent == EInputEvent.IE_Pressed
            and key in ("Escape", "XboxTypeS_B")
            and _workshop_root_screen is not None
        ):
            try:
                at_root = bool(obj.ScreenStack) and obj.ScreenStack[-1] == _workshop_root_screen
            except Exception:
                at_root = False
            if at_root:
                # Defer creation until this key event has completely left the
                # Scaleform input stack. Otherwise the opening Escape also
                # reaches the new screen and instantly closes it.
                _pending_discard_after_release = True
                _suppress_escape_until_release = True
                return Block, True
        if args.uevent == EInputEvent.IE_Pressed:
            if _control_down and key.lower() == "c":
                highlighted = _highlighted_part(obj, [part for part, _option in _global_search_options])
                if highlighted is not None:
                    _copy_part(highlighted)
                    return Block, True
            slot_context = _focused_slot_context(obj)
            if slot_context is not None:
                kind, label, field = slot_context
                if kind == "weapon" and core._session is not None:
                    current = getattr(core._session.weapon.DefinitionData, field, None)
                    if key == "Delete" and not _control_down:
                        _clear_weapon_slot(label, field, [])
                        return Block, True
                    if _control_down and key.lower() == "c":
                        _copy_part(current)
                        return Block, True
                    if _control_down and key.lower() == "v":
                        _paste_part(label, field, [])
                        return Block, True
                if kind == "item" and _item_target is not None:
                    current = getattr(_item_target.DefinitionData, field, None)
                    if key == "Delete" and not _control_down:
                        _clear_item_slot(label, field)
                        return Block, True
                    if _control_down and key.lower() == "c":
                        _copy_part(current)
                        return Block, True
                    if _control_down and key.lower() == "v":
                        _paste_item_part(label, field, [])
                        return Block, True
        if args.uevent == EInputEvent.IE_Pressed and _active_item_destination is not None:
            label, field, parts = _active_item_destination
            if _control_down and key.lower() == "c":
                highlighted = _highlighted_part(obj, parts)
                current = None if _item_target is None else getattr(_item_target.DefinitionData, field, None)
                _copy_part(highlighted or _active_preview_part or current)
                return Block, True
            if _control_down and key.lower() == "v" and _cursor_on_part_row(obj, parts):
                _paste_item_part(label, field, parts)
                return Block, True
        if args.uevent == EInputEvent.IE_Pressed and _active_part_destination is not None:
            slot_label, field, parts = _active_part_destination
            if key == "Delete" and not _control_down:
                # Delete is deliberately scoped to an actual highlighted part
                # row.  The destination context survives while navigating
                # back, and must never clear a slot from the Workshop root.
                try:
                    focused = find_focused_item(obj)
                    focused_label = str(obj.GetVariableString(f"{focused}.mLabel.text"))
                    row_labels = {
                        _part_row_label(part, False) for part in parts
                    } | {
                        _part_row_label(part, True) for part in parts
                    } | {
                        _search_result_label(part) for part in parts
                    }
                except Exception:
                    focused_label, row_labels = "", set()
                if focused_label in row_labels:
                    _clear_weapon_slot(slot_label, field, parts)
                    return Block, True
            if _control_down and key.lower() == "c":
                highlighted = _highlighted_part(obj, parts)
                current = None if core._session is None else getattr(core._session.weapon.DefinitionData, field, None)
                _copy_part(highlighted or _active_preview_part or current)
                return Block, True
            if _control_down and key.lower() == "v" and _cursor_on_part_row(obj, parts):
                _paste_part(slot_label, field, parts)
                return Block, True
        return None
    if args.uevent not in (EInputEvent.IE_Pressed, EInputEvent.IE_Repeat):
        return Block, True

    if key in ("Enter", "XboxTypeS_A"):
        slot_label, field, source, _focused, complete = _search_state
        query = _search_query
        _search_state = None
        _search_query = ""
        _suppress_search_accept_until_release = True
        _show_search_results(slot_label, field, source, query, complete)
        return Block, True
    if key in ("Escape", "XboxTypeS_B"):
        _slot_label, _field, _source, focused, _complete = _search_state
        _search_state = None
        _search_query = ""
        obj.SetVariableString(f"{focused}.mLabel.text", "Search These Parts" if _complete == "item" else "Search Parts")
        return Block, True
    if key in ("BackSpace", "Delete"):
        _search_query = _search_query[:-1]
    else:
        char = _KEY_CHARS.get(key)
        if char is None and len(key) == 1 and key.isalnum():
            char = key.lower()
        if char is not None and len(_search_query) < 48:
            _search_query += char
    focused = _search_state[3]
    obj.SetVariableString(f"{focused}.mLabel.text", f"Search: {_search_query}_")
    return Block, True


def _open_nested(title: str, children: list[Any]) -> None:
    global _pending_layout_ticks
    if _active_pause_menu is not None:
        create_nested_options_menu(_active_pause_menu, NestedOption(title, children, description=""))
        _expand_workshop_rows(_active_pause_menu)
        _pending_layout_ticks = 2


def _fit_workshop_label(menu: UObject, path: str, width: float, scale: float = 100.0) -> None:
    """Keep database identifiers on one visible line, including after focus changes."""
    menu.SetVariableBool(path + ".wordWrap", False)
    menu.SetVariableBool(path + ".multiline", False)
    menu.SetVariableString(path + ".autoSize", "none")
    menu.SetVariableNumber(path + "._xscale", 100.0)
    menu.SetVariableNumber(path + "._width", width)
    menu.SetVariableNumber(path + ".hscroll", 0)
    menu.SetVariableNumber(path + ".scroll", 1)
    text_width = float(menu.GetVariableNumber(path + ".textWidth")) + 6.0
    natural_width = width * 100.0 / scale
    field_width = max(natural_width, text_width) if math.isfinite(text_width) else natural_width
    menu.SetVariableNumber(path + "._width", field_width)
    menu.SetVariableNumber(path + "._xscale", 100.0 * width / field_width)
    menu.SetVariableNumber(path + "._yscale", scale)


def _fit_workshop_header(menu: UObject) -> None:
    """Use the authored header geometry and an explicit font, never stretch text."""
    path = "_level0.title"
    title = str(menu.GetVariableString(path + ".text")).strip()
    if not title:
        return
    # pause.xml DefineEditText 111: 455px, WillowHead 18px, centered,
    # placed at (186.35, 70.3), scale 95%. Reduce the font itself.
    menu.SetVariableNumber(path + "._xscale", 100.0)
    menu.SetVariableNumber(path + "._yscale", 100.0)
    menu.SetVariableNumber(path + "._width", 455.0)
    menu.SetVariableNumber(path + "._xscale", 95.0)
    menu.SetVariableNumber(path + "._yscale", 95.0)
    menu.SetVariableNumber(path + "._x", 186.35)
    menu.SetVariableNumber(path + "._y", 70.3)
    menu.SetVariableBool(path + ".wordWrap", False)
    menu.SetVariableBool(path + ".multiline", False)
    menu.SetVariableString(path + ".autoSize", "none")
    size = 16 if title.casefold().startswith("select inventory weapon") else 15
    escaped = html.escape(title)
    def apply(font_size: int) -> None:
        menu.SetVariableString(path + ".htmlText", f'<p align="center"><font face="$WillowHead" size="{font_size}" color="#081c33">{escaped}</font></p>')
    apply(size)
    measured = float(menu.GetVariableNumber(path + ".textWidth"))
    if math.isfinite(measured) and measured > 435.0:
        apply(max(8, int(size * 435.0 / measured)))


def _expand_workshop_rows(menu: UObject) -> None:
    """Reclaim the stock pause movie's unused controller-icon column."""
    try:
        focused = find_focused_item(menu)
        match = re.match(r"^(.*\.item)\d+$", focused)
        if match is None:
            return
        base = match.group(1)
        title = str(menu.GetVariableString("_level0.title.text")).strip().casefold()
        row_scale = 85.0
        if title:
            _fit_workshop_header(menu)
        # ListControl creates every catalog row, but only a handful are visible.
        # Size the viewport neighborhood, not hundreds of off-screen parts.
        focused_index = int(focused[len(base):])
        for index in range(max(0, focused_index - 12), focused_index + 13):
            item = f"{base}{index}"
            label = str(menu.GetVariableString(f"{item}.mLabel.text"))
            if not label:
                continue
            _fit_workshop_label(menu, f"{item}.mLabel", 600.0 if _workshop_card_active and getattr(_workshop_card_movie, "bReadyToDisplay", False) else 930.0, row_scale)
            if menu.GetVariableString(f"{item}.mValueLabel.text"):
                menu.SetVariableNumber(f"{item}.mValueLabel._xscale", row_scale)
                menu.SetVariableNumber(f"{item}.mValueLabel._yscale", row_scale)
            menu.SetVariableBool(f"{item}.controllerIcon._visible", False)
            menu.SetVariableBool(f"{item}.emptyIcon._visible", False)
    except Exception as exc:
        logging.info(f"Pandora's Workshop could not expand native rows: {exc}")


def _refresh_visible_current_markers(menu: UObject) -> None:
    """Refresh CURRENT markers after returning from a preview/detail page."""
    if core._session is None and _item_target is None:
        return
    try:
        focused = find_focused_item(menu)
        match = re.match(r"^(.*\.item)\d+$", focused)
        if match is None:
            return
        base = match.group(1)
        if _active_part_destination is not None:
            _label, field, parts = _active_part_destination
            current = getattr(core._session.weapon.DefinitionData, field, None)
            for index in range(_native_row_limit()):
                path = f"{base}{index}.mLabel.text"
                shown = str(menu.GetVariableString(path))
                plain = shown.removeprefix("[CURRENT] ")
                for part in parts:
                    leaf = core._leaf(part)
                    family_label = _search_result_base_label(part)
                    if plain in (leaf, _part_row_label(part, False), family_label):
                        is_current = _same_object(part, current)
                        menu.SetVariableString(
                            path,
                            (f"[CURRENT] {leaf}" if is_current else family_label)
                            if ":" in plain else _part_row_label(part, is_current),
                        )
                        break
        if _active_item_destination is not None and _item_target is not None:
            _label, field, parts = _active_item_destination
            current = getattr(_item_target.DefinitionData, field, None)
            for index in range(_native_row_limit()):
                path = f"{base}{index}.mLabel.text"
                shown = str(menu.GetVariableString(path))
                plain = shown.removeprefix("[CURRENT] ")
                for part in parts:
                    leaf = core._leaf(part)
                    if plain in (leaf, _part_row_label(part, False), _search_result_base_label(part)):
                        menu.SetVariableString(path, _part_row_label(part, _same_object(part, current)))
                        break
        # Global search results can target any slot, so use their own
        # all-slot CURRENT resolver rather than the last destination field.
        for index in range(_native_row_limit()):
            path = f"{base}{index}.mLabel.text"
            shown = str(menu.GetVariableString(path))
            plain = shown.removeprefix("[CURRENT] ")
            for part, _option in _global_search_options:
                leaf = core._leaf(part)
                if plain in (leaf, _search_result_base_label(part)):
                    menu.SetVariableString(path, _search_result_label(part))
                    break
    except Exception as exc:
        logging.info(f"Pandora's Workshop could not refresh CURRENT markers: {exc}")


def _open_valid_slot(label: str, field: str, collection: str) -> None:
    session = core._session
    parts = [] if session is None else core._valid_parts(session, collection)
    children = _part_children(label, field, parts, include_search=False) if parts else []
    if not children:
        children = [_button("No compatible parts found", "", lambda: None)]
    _open_nested(label, children)


def _valid_slot(label: str, field: str, collection: str) -> ButtonOption:
    session = core._session
    current = "None" if session is None else _overview_part_name(getattr(session.weapon.DefinitionData, field, None))
    option = _button(f"{label}: {current}", "", lambda: _open_valid_slot(label, field, collection))
    _slot_options.setdefault(field, []).append((label, option))
    return option


def _freedom_catalog(field: str, complete: bool) -> list[UObject]:
    if complete:
        # Every family is unrestricted, but Unreal still enforces the actual
        # property class: name slots accept every name part and physical slots
        # accept every physical part. Crossing that class boundary only throws
        # a type error and makes apparently selectable rows do nothing.
        kind = "name" if field in ("PrefixPartDefinition", "TitlePartDefinition") else "physical"
        unique = {core._short(part).lower(): part for part in core._catalog(kind)}
        return sorted(unique.values(), key=lambda part: core._short(part).lower())
    kind = "name" if field in ("PrefixPartDefinition", "TitlePartDefinition") else "physical"
    return [part for part in core._catalog(kind) if not _is_internal_test_part(part)]


def _open_invalid_category(label: str, field: str, family: str, category: str, complete: bool) -> None:
    parts = [
        part for part in _freedom_catalog(field, complete)
        if core._family(part) == family and core._declared_category(part) == category
        and core._resolve_catalog_part(part, quiet=True) is not None
    ]
    _open_nested(category, _part_children(label, field, parts))


def _open_invalid_family(label: str, field: str, family: str, complete: bool = False) -> None:
    family_parts = [part for part in _freedom_catalog(field, complete) if core._family(part) == family]
    categories = sorted({core._declared_category(part) for part in family_parts})
    if not complete:
        categories = [category for category in categories if category == SLOT_CATEGORY[label]]
    _open_nested(
        family,
        [
            _button(
                category,
                "",
                lambda category=category: _open_invalid_category(label, field, family, category, complete),
            )
            for category in categories
        ],
    )


def _open_invalid_slot(label: str, field: str, complete: bool = False) -> None:
    catalog = _freedom_catalog(field, complete)
    searchable = catalog if complete else [
        part for part in catalog if core._declared_category(part) == SLOT_CATEGORY[label]
    ]
    families = sorted({core._family(part) for part in catalog})
    _open_nested(
        label,
        [
            _button(
                "Search Entire Catalog",
                "Search every part available for this destination slot.",
                lambda: _begin_search(label, field, searchable),
            ),
            *[
                _button(
                    family,
                    "",
                    lambda family=family: _open_invalid_family(label, field, family, complete),
                )
                for family in families
            ],
        ],
    )


def _invalid_slot(label: str, field: str, complete: bool = False) -> ButtonOption:
    session = core._session
    current = "None" if session is None else _overview_part_name(getattr(session.weapon.DefinitionData, field, None))
    option = _button(f"{label}: {current}", "", lambda: _open_invalid_slot(label, field, complete))
    _slot_options.setdefault(field, []).append((label, option))
    return option


def _open_mode_search(complete: bool) -> None:
    """Search first, then choose the result's destination."""
    source = [*core._catalog("physical"), *core._catalog("name")]
    if not complete:
        source = [part for part in source if not _is_internal_test_part(part)]
    unique = {core._short(part).lower(): part for part in source}
    _begin_search("Global", "", sorted(unique.values(), key=lambda part: core._short(part).lower()), complete)


def _open_global_result(part: UObject, complete: bool) -> None:
    slogan, basics, effects = _metadata_for(part)
    children: list[Any] = [
        _button("Choose Destination Slot", "", lambda: _choose_search_destination(part, complete)),
        _button("Copy This Part", "", lambda: _copy_part(part)),
        _button("Set as Comparison Part", "", lambda: _set_comparison_part(part)),
    ]
    if _comparison_part is not None and not _same_object(part, _comparison_part):
        children.append(_button(
            f"Compare with {core._leaf(_comparison_part)}", "",
            lambda: _open_part_comparison(part, _comparison_part),
        ))
    if slogan:
        children.append(_detail_button(f'"{slogan}"', _part_display_name(part)))
    children.extend(_detail_button(line, _part_display_name(part)) for line in _weapon_preview_basics(part, basics))
    children.extend(_detail_button(_format_effect(line, core._short(part)), _part_display_name(part)) for line in effects)
    _open_nested(core._leaf(part), children)


def _choose_search_destination(part: UObject, complete: bool) -> None:
    category = core._declared_category(part)
    slots = list(core.SLOTS) if complete else [
        slot for slot in core.SLOTS if SLOT_CATEGORY[slot[0]] == category
    ]
    if not slots:
        core._notify(f"{core._leaf(part)} has no matching Invalid-mode destination; use Pandora's Box.")
        return
    children: list[Any] = []
    for label, field, _collection in slots:
        option = _button(
            f"{label}: {_overview_part_name(getattr(core._session.weapon.DefinitionData, field, None))}",
            "",
            lambda label=label, field=field: _apply_part(label, field, part, [part]),
        )
        _slot_options.setdefault(field, []).append((label, option))
        children.append(option)
    _open_nested("Choose Destination Slot", children)


def _definition_objects(field: str) -> list[UObject]:
    session = core._session
    if session is None:
        return []
    current = getattr(session.weapon.DefinitionData, field, None)
    if current is None:
        return []
    try:
        class_name = current.Class.Name
        return sorted(
            [obj for obj in unrealsdk.find_all(class_name) if not str(obj).startswith(f"{class_name}'WillowGame.Default__")],
            key=lambda obj: core._short(obj).lower(),
        )
    except Exception as exc:
        logging.warning(f"Pandora's Workshop could not index {field}: {exc}")
        return []


def _apply_definition(label: str, field: str, definition: UObject) -> None:
    session = core._session
    if session is None:
        return
    try:
        setattr(session.weapon.DefinitionData, field, definition)
        session.dirty = True
        core._rebuild(session.weapon)
        rendered = _short_definition(field, definition)
        for row_label, option in _definition_options.get(field, []):
            previous = option.display_name
            option.display_name = f"{row_label}: {rendered}"
            _refresh_native_labeled_row(previous, option.display_name)
        for obj, option in _definition_choice_options.get(field, []):
            option.display_name = ("[CURRENT] " if _same_object(obj, definition) else "") + core._leaf(obj)
        _refresh_equipped_header()
        _refresh_workshop_card()
        core._notify(f"{label}: {core._leaf(definition)}")
    except Exception as exc:
        logging.error(f"Pandora's Workshop could not set {field}: {exc}")


def _open_definition_menu(label: str, field: str) -> None:
    objects = _definition_objects(field)
    current = None if core._session is None else getattr(core._session.weapon.DefinitionData, field, None)
    choices: list[ButtonOption] = []
    _definition_choice_options[field] = []
    for obj in objects:
        option = _button(
            ("[CURRENT] " if _same_object(obj, current) else "") + core._leaf(obj),
            core._short(obj),
            lambda o=obj: _apply_definition(label, field, o),
        )
        choices.append(option)
        _definition_choice_options[field].append((obj, option))
    _open_nested(
        label,
        choices or [_button("No Definitions Found", "No live objects were resolved.", lambda: None)],
    )


def _definition_menu(label: str, field: str) -> ButtonOption:
    current = "None" if core._session is None else _short_definition(field, getattr(core._session.weapon.DefinitionData, field, None))
    option = _button(f"{label}: {current}", "", lambda: _open_definition_menu(label, field))
    _definition_options.setdefault(field, []).append((label, option))
    return option


def _short_definition(field: str, value: UObject | None) -> str:
    if value is None:
        return "None"
    leaf = core._leaf(value)
    prefixes = {
        "BalanceDefinition": ("ItemGrade_Weapon_", "ItemGrade_"),
        "ManufacturerDefinition": (),
        "WeaponTypeDefinition": ("WeaponType_",),
    }
    for prefix in prefixes.get(field, ()):
        if leaf.startswith(prefix):
            leaf = leaf[len(prefix):]
            break
    return leaf.replace("PatrolSMG", "SMG").replace("SupportMachineGun", "Support MG").replace("_", " ")


def _manager_inventory_members(managers: list[UObject] | set[UObject]) -> set[str]:
    """Collect objects still linked into the live inventory manager.

    Sold inventory UObjects can remain alive with their old Owner until map
    cleanup.  Ownership alone therefore cannot distinguish a backpack item
    from a sold object.
    """
    found: set[str] = set()
    queue: list[UObject] = []
    for manager in managers:
        for attr in (
            "InventoryChain", "BackpackInventoryList", "InventoryList",
            "Backpack", "ReadiedInventory",
        ):
            try:
                value = getattr(manager, attr)
            except Exception:
                continue
            if value is None:
                continue
            try:
                queue.extend(item for item in list(value) if item is not None)
            except Exception:
                queue.append(value)
    seen: set[str] = set()
    while queue and len(seen) < 1000:
        item = queue.pop()
        key = str(item)
        if key in seen:
            continue
        seen.add(key)
        found.add(key)
        for attr in ("Inventory", "NextInventory", "NextInventoryItem", "Next"):
            try:
                nxt = getattr(item, attr)
                if nxt is not None:
                    queue.append(nxt)
            except Exception:
                pass
    return found


def _inventory_weapons() -> list[UObject]:
    pc = get_pc()
    pawn = getattr(pc, "Pawn", None)
    managers = [
        getattr(pawn, "InvManager", None),
        getattr(pawn, "InventoryManager", None),
    ]
    managers = [manager for manager in managers if manager is not None]
    live_members = _manager_inventory_members(managers)
    result: list[UObject] = []
    for weapon in unrealsdk.find_all("WillowWeapon"):
        try:
            if str(weapon).startswith("WillowGame.Default__"):
                continue
            # BL1E keeps several empty WillowWeapon_N placeholders alive for
            # the quick-select cells. They have no usable definition/name and
            # appeared as fake inventory entries in the initial test build.
            data = weapon.DefinitionData
            if (
                getattr(data, "BalanceDefinition", None) is None
                or getattr(data, "WeaponTypeDefinition", None) is None
            ):
                continue
            owner = weapon.Owner
            if (live_members and str(weapon) in live_members) or (not live_members and (owner == pawn or owner in managers)):
                result.append(weapon)
        except Exception:
            pass
    current = core._current_weapon()
    if current is not None and current not in result:
        result.append(current)
    return sorted(result, key=lambda weapon: core._weapon_name(weapon).lower())


def _item_name(item: UObject) -> str:
    for function_name in ("GetShortHumanReadableName", "GetHumanReadableName", "GetItemName"):
        try:
            value = getattr(item, function_name)()
            if value:
                return str(value)
        except Exception:
            pass
    try:
        data = item.DefinitionData
        words = [
            _part_display_name(getattr(data, "PrefixItemNamePartDefinition", None)),
            _part_display_name(getattr(data, "TitleItemNamePartDefinition", None)),
        ]
        rendered = " ".join(word for word in words if word and word != "None")
        if rendered:
            return rendered
        return core._leaf(data.ItemDefinition).replace("_", " ")
    except Exception:
        return core._leaf(item)


def _inventory_items() -> list[UObject]:
    pc = get_pc()
    pawn = getattr(pc, "Pawn", None)
    managers = {
        manager for manager in (
            getattr(pawn, "InvManager", None),
            getattr(pawn, "InventoryManager", None),
        ) if manager is not None
    }
    result: list[UObject] = []
    live_members = _manager_inventory_members(managers)

    def supported(item: UObject) -> bool:
        try:
            definition_path = core._short(item.DefinitionData.ItemDefinition).lower()
            return any(
                token in definition_path
                for token in ("gd_shields.", "gd_tunercuffs.", "gd_commanddecks.")
            )
        except Exception:
            return False

    # Shields, grenade mods, and class mods are native subclasses.  A direct
    # GetItemList call is not exposed with a compatible Python signature in
    # this SDK build, so scan the live subclasses and filter by owner instead.
    for item in unrealsdk.find_all("WillowItem", exact=False):
        try:
            if str(item).startswith("WillowGame.Default__"):
                continue
            if not supported(item):
                continue
            owned = str(item) in live_members if live_members else (item.Owner == pawn or item.Owner in managers)
            equipped = bool(item.bReadied) and (item.Owner == pawn or item.Owner in managers)
            if (owned or equipped) and item not in result:
                result.append(item)
        except Exception:
            pass
    return sorted(result, key=lambda item: _item_name(item).lower())


def _item_snapshot(item: UObject) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field in ITEM_FIELDS:
        try:
            result[field] = getattr(item.DefinitionData, field)
        except Exception:
            pass
    return result


def _reset_item_effect_state(item: UObject) -> None:
    item.RemoveAllAttributeSlotEffects()
    item.RemoveAllPartExternalAttributeEffects()
    item.RemoveAllItemAttributeEffects()
    # Native initialization populates the slots supplied by the new parts.
    # Keep slot names but clear the previous activation and computed values.
    for slot in item.AttributeSlots:
        slot.bActivated = False
        slot.AttributeToModify = None
        slot.ConstraintAttribute = None
        slot.EffectGrade = 0
        slot.ComputedModifierValue = 0.0
    item.ItemCardModifierStats = []
    item.UIStatModifiers = []


def _refresh_grenade_card_data(item: UObject) -> None:
    """Replace grenade presentation data installed by creation behaviors."""
    data = item.DefinitionData
    if not core._short(data.ItemDefinition).lower().startswith("gd_tunercuffs."):
        return
    for name in ("FlashTechFrame", "RainGrenadeIcon"):
        item.RemoveInstanceData(name)
    for field in ITEM_FIELDS:
        part = getattr(data, field, None)
        behaviors = getattr(getattr(part, "Behaviors", None), "OnCreate", ())
        for behavior in behaviors:
            if behavior.Class.Name != "Behavior_AddInstanceData":
                continue
            if int(behavior.Context.BehaviorContext) != 0:
                continue
            for datum in behavior.InstanceData:
                if str(datum.Name) in ("FlashTechFrame", "RainGrenadeIcon"):
                    item.SetInstanceData(datum, False)


def _replace_item_definition(item: UObject, changes: dict[str, Any]) -> None:
    """Remove the old effect set before changing any definition fields."""
    previous = _item_snapshot(item)
    desired = dict(previous)
    desired.update(changes)
    definition = unrealsdk.make_struct("ItemDefinitionData", **desired)
    source = item.Owner or get_pc().Pawn
    equipped = bool(item.bReadied)
    if equipped:
        item.ItemUnequipped(False)
    try:
        _reset_item_effect_state(item)
        item.InitializeFromDefinitionData(definition, source, False)
        _refresh_grenade_card_data(item)
        item.GenerateHumanReadableName()
        item.CacheItemCard()
        item.ConstructInvMesh()
    except Exception:
        # Restore the previous definition before returning control to the menu.
        _reset_item_effect_state(item)
        item.InitializeFromDefinitionData(
            unrealsdk.make_struct("ItemDefinitionData", **previous), source, False)
        _refresh_grenade_card_data(item)
        item.CacheItemCard()
        raise
    finally:
        if equipped:
            item.ItemEquipped()


def _rebuild_item(item: UObject) -> None:
    _replace_item_definition(item, {})


def _item_catalog(kind: str) -> list[UObject]:
    if kind in _item_catalogs:
        return _item_catalogs[kind]
    class_name = "ItemNamePartDefinition" if kind == "name" else "ItemPartDefinition"
    paths = ITEM_NAME_PART_PATHS if kind == "name" else ITEM_PART_PATHS
    unique: dict[str, str] = {}
    for path in paths:
        identity = core.ENHANCED_PART_ALIASES.get(path.lower(), path).lower()
        unique.setdefault(identity, path)
    parts = [core.CatalogPart(path, class_name) for path in unique.values()]
    _item_catalogs[kind] = sorted(parts, key=lambda part: core._short(part).lower())
    return _item_catalogs[kind]


def _entry_part(entry: Any) -> UObject | None:
    try:
        return entry.Part
    except Exception:
        return entry if isinstance(entry, UObject) else None


def _item_slot_entries(target: Any, definition_list: str, overlay_list: str) -> tuple[list[Any], bool]:
    """Collect the game's weighted part entries for one item slot.

    Returns the entries and whether names are supplied by the physical parts.
    """
    data = target.DefinitionData
    entries: list[Any] = []
    try:
        source = getattr(data.ItemDefinition, definition_list)
        entries.extend(list(source.WeightedParts if hasattr(source, "WeightedParts") else source))
    except Exception as exc:
        logging.info(f"Pandora's Workshop item definition list {definition_list}: {exc}")
    if overlay_list:
        balance = getattr(data, "BalanceDefinition", None)
        collections = [getattr(target, "PartListCollection", None)]
        visited = set()
        while balance is not None and core._short(balance) not in visited:
            visited.add(core._short(balance))
            collections.append(getattr(balance, "PartListCollection", None))
            balance = getattr(balance, "BaseDefinition", None)
        for collection in collections:
            source = getattr(collection, overlay_list, None)
            if source is not None:
                entries.extend(getattr(source, "WeightedParts", ()))
    try:
        class_name = target.Class.Name
    except Exception:
        class_name = ""
    part_supplied_name = definition_list in ("PrefixList", "TitleList") and (
        core._short(data.ItemDefinition).lower().startswith(("gd_shields.", "gd_tunercuffs."))
        or class_name == "WillowShield"
    )
    if definition_list in ("PrefixList", "TitleList"):
        # The item definition supplies the generic name. Each compatible
        # body, side or manufacturer material can supply additional names
        # (shields, grenades, and DLC command/loyalty class mods all do).
        for _, slot_field, slot_list, slot_overlay in ITEM_SLOTS:
            if not slot_overlay:
                continue
            for physical in _item_valid_parts(slot_field, slot_list, slot_overlay, include_current=False, target=target):
                entries.extend(getattr(physical, definition_list, ()))
    return entries, part_supplied_name


def _item_slot_allows_empty(field: str, definition_list: str, overlay_list: str, target: Any = None) -> bool:
    """An item slot may be empty only if the game's own list allows it.

    That is, the slot has no part list at all, or its list includes an empty
    entry for this manufacturer.
    """
    target = _item_target if target is None else target
    if target is None:
        return False
    entries, _ = _item_slot_entries(target, definition_list, overlay_list)
    if not entries:
        return True
    manufacturer = getattr(target.DefinitionData, "ManufacturerDefinition", None)
    for entry in entries:
        if _entry_part(entry) is not None:
            continue
        try:
            if core._manufacturer_allowed(entry, manufacturer):
                return True
        except Exception:
            return True
    return False


def _item_valid_parts(
    field: str,
    definition_list: str,
    overlay_list: str,
    *,
    include_current: bool = True,
    target: Any = None,
) -> list[UObject]:
    target = _item_target if target is None else target
    if target is None:
        return []
    data = target.DefinitionData
    manufacturer = getattr(data, "ManufacturerDefinition", None)
    entries, part_supplied_name = _item_slot_entries(target, definition_list, overlay_list)
    result: list[UObject] = []
    seen: set[str] = set()
    for entry in entries:
        part = _entry_part(entry)
        if part is None:
            continue
        try:
            if not core._manufacturer_allowed(entry, manufacturer):
                continue
        except Exception:
            pass
        key = core._short(part).lower()
        if key not in seen:
            seen.add(key)
            result.append(part)
    # Grenade names are compatible across manufacturers. Spawn lists choose
    # a matching name for the material, but do not describe the full editor
    # name catalog. Behavior remains defined by the physical parts.
    if definition_list in ("PrefixList", "TitleList") and core._short(data.ItemDefinition).lower().startswith("gd_tunercuffs."):
        name_group = "prefix" if definition_list == "PrefixList" else "title"
        for part in _item_catalog("name"):
            path = core._short(part).lower()
            if path.startswith(f"gd_tunercuffs.{name_group}.") and path not in seen:
                seen.add(path)
                result.append(part)
    # Command Decks share body and name definitions by character class.
    # The selected archetype's spawn list only contains its own body and prefix.
    body = core._short(getattr(data, "BodyItemPartDefinition", None)).lower()
    match = re.fullmatch(r"(?:dlc3_)?gd_commanddecks\.body_(brick|lilith|mordecai|roland)\.[^.]+", body)
    if match:
        character = match.group(1)
        markers = {
            "BodyItemPartDefinition": f"body_{character}.",
            "PrefixItemNamePartDefinition": f"prefix.prefix_{character}_",
            "TitleItemNamePartDefinition": f"title.title_comdeck{character}",
        }
        marker = markers.get(field)
        if marker:
            kind = "physical" if field == "BodyItemPartDefinition" else "name"
            for part in _item_catalog(kind):
                path = core._short(part).lower()
                package, _, local = path.partition(".")
                if package not in ("gd_commanddecks", "dlc3_gd_commanddecks"):
                    continue
                matches = local == marker if kind == "name" and field == "TitleItemNamePartDefinition" else local.startswith(marker)
                if matches and path not in seen:
                    seen.add(path)
                    result.append(part)
    # DLC command and loyalty decks name themselves after the character and
    # manufacturer in their body, e.g. Body_Command.Lilith_Hyperion_Specter ->
    # Prefix_Command_Lilith_Specter, Body_Loyalty.Loyalty_Lilith_Dahl ->
    # Prefix_Loyalty_Dahl_Professional + Title_DahlLoyaltyDeck.
    deck = re.fullmatch(r"(?:dlc3_)?gd_commanddecks\.body_(command|loyalty)\.([a-z0-9_]+)", body)
    if deck and field in ("PrefixItemNamePartDefinition", "TitleItemNamePartDefinition"):
        characters = {"brick", "lilith", "mordecai", "roland"}
        tokens = deck.group(2).split("_")
        if deck.group(1) == "loyalty":
            tokens = tokens[1:]  # drop the leading "loyalty"
        character = next((token for token in tokens if token in characters), None)
        if character is None:
            # e.g. Loyalty_Gearbox on Item_LoyaltyDeck_Lilith
            item_leaf = core._leaf(getattr(data, "ItemDefinition", None)).lower()
            character = next((name for name in characters if item_leaf.endswith("_" + name)), None)
        others = [token for token in tokens if token not in characters and token != "all"]
        manufacturer_token = others[0] if others else None
        kind_prefix = field == "PrefixItemNamePartDefinition"

        def deck_name_ok(local: str) -> bool:
            if deck.group(1) == "command":
                if not kind_prefix:
                    # DLC command decks reuse the base game's class mod titles.
                    return local == "title.title_comdeck" or bool(
                        character and local == f"title.title_comdeck{character}")
                return any(local.startswith(f"prefix.prefix_command_{token}_")
                           for token in (character, manufacturer_token) if token)
            if manufacturer_token is None:
                return False
            if not kind_prefix:
                return local in (f"title.title_{manufacturer_token}loyaltydeck", "title.title_loyaltydeck")
            if not (local.startswith(f"prefix.prefix_loyalty_{manufacturer_token}")
                    or (character and local.startswith(f"prefix.prefix_loyalty_{character}_{manufacturer_token}"))):
                return False
            # Character-specific loyalty names only fit that character's deck.
            named = {token for token in local.split(".")[-1].split("_") if token in characters}
            return not named or named == {character}

        for part in _item_catalog("name"):
            path = core._short(part).lower()
            package, _, local = path.partition(".")
            if package in ("gd_commanddecks", "dlc3_gd_commanddecks") and path not in seen and deck_name_ok(local):
                seen.add(path)
                result.append(part)
    if include_current and not part_supplied_name:
        current = getattr(data, field, None)
        if current is not None and core._short(current).lower() not in seen:
            result.append(current)
    return sorted(result, key=lambda part: core._short(part).lower())


def _item_part_family(part: UObject) -> str:
    package = core._short(part).split(".", 1)[0]
    labels = {
        "gd_shields": "Shields",
        "gd_tunercuffs": "Grenade Mods",
        "gd_CommandDecks": "Class Mods",
        "dlc3_gd_CommandDecks": "DLC3 Class Mods",
        "dlc3_gd_item_UniqueParts": "DLC3 Unique Items",
        "gd_ElementalUpgrade": "Artifacts",
        "gd_StorageDeckUpgrade": "Storage Upgrades",
    }
    return labels.get(package, package.replace("_", " ").title())


def _item_part_category(part: UObject) -> str:
    path = core._short(part).lower()
    for token, label in (
        (".body", "Bodies"), (".leftside", "Left Sides"),
        (".rightside", "Right Sides"), (".material", "Materials"),
        (".prefix", "Prefixes"), (".title", "Titles"),
    ):
        if token in path:
            return label
    return "Other"


def _select_weapon(weapon: UObject) -> None:
    _confirm_selection_change(lambda: _activate_weapon(weapon))


def _activate_weapon(weapon: UObject) -> None:
    global _item_target, _item_original
    _clear_card_preview()
    _item_target = None
    _item_original = {}
    core._session = core.Session(weapon=weapon, original=core._snapshot(weapon))
    core._remember_weapon_parts(weapon)
    if _active_pause_menu is not None:
        _return_to_workshop_root()
    _refresh_workshop_card()
    core._notify(f"Selected {core._weapon_name(weapon)}")


def _return_to_workshop_root() -> None:
    """Close selection pages and redraw the existing Workshop root."""
    menu = _active_pause_menu
    if menu is None or _workshop_root_screen not in menu.ScreenStack:
        raise RuntimeError("Workshop root screen is unavailable")
    while menu.ScreenStack[-1] != _workshop_root_screen:
        screen = menu.ScreenStack.pop()
        screen.Screen_Deactivate()
        if menu_options.nested_selection_stack:
            menu_options.nested_selection_stack.pop()
    menu_options.reactivate_upper_screen.disable()
    root = _root_options()
    populator = menu_options.populator_stack[-1]
    populator.title = root.display_name
    populator.options = root.children
    menu.ActivateTopPage(0)
    draw_custom_menu(menu)


def _has_unsaved_changes() -> bool:
    """Compare current definitions and pending sliders against the last save."""
    global _pending_part_change
    pending = _pending_part_change
    _pending_part_change = None
    if pending is not None and pending[0] is core._session:
        _apply_part_now(*pending[1:])
    session = core._session
    weapon_changed = session is not None and core._snapshot(session.weapon) != session.original
    if session is not None:
        session.dirty = weapon_changed
    item_changed = _item_target is not None and (
        _item_snapshot(_item_target) != _item_original
        or bool(_item_grade_rows and core._grade_components(_item_target) != (
            int(_item_grade_rows["Quality"].value), int(_item_grade_rows["Level"].value)))
    )
    return bool(weapon_changed or item_changed)


def _confirm_selection_change(action: Any) -> None:
    global _card_modal_hidden
    if not _has_unsaved_changes():
        action()
        return

    def resolve(save: bool) -> None:
        try:
            if _item_target is not None:
                if save:
                    if not _save_item_changes():
                        _resume_workshop_card()
                        return
                else:
                    _discard_item_changes()
            session = core._session
            if session is not None and session.dirty:
                if save:
                    core._rebuild(session.weapon)
                else:
                    core._restore_snapshot(session)
                session.original = core._snapshot(session.weapon)
                session.dirty = False
            _resume_workshop_card()
            action()
        except Exception as exc:
            _resume_workshop_card()
            core._notify(f"Could not switch selection: {exc}")

    _card_modal_hidden = True
    try:
        core._show_box("SWITCH SELECTION", "", [
            ("SAVE CHANGES AND SWITCH", '<p align="center">Keep current edits and select the new item.</p>', lambda: resolve(True)),
            ("REVERT CHANGES AND SWITCH", '<p align="center">Undo current unsaved edits and select the new item.</p>', lambda: resolve(False)),
            ("KEEP EDITING", '<p align="center">Keep the current selection and continue editing.</p>', _resume_workshop_card),
        ], _resume_workshop_card)
    except Exception:
        _resume_workshop_card()
        raise


def _weapon_selector() -> NestedOption:
    rows = []
    for weapon in _inventory_weapons():
        slot = int(getattr(weapon, "QuickSelectSlot", 0) or 0) if weapon.bReadied else 0
        slotted = 1 <= slot <= 4
        name = core._weapon_name(weapon)
        label = f"[SLOT {slot}] {name}" if slotted else name
        rows.append((slot if slotted else 5, _button(label, str(weapon), lambda w=weapon: _select_weapon(w)), weapon))
    rows.sort(key=lambda row: row[0])
    _weapon_selector_entries[:] = [(button, weapon) for _, button, weapon in rows]
    return NestedOption(
        f"Select Inventory Weapon ({len(rows)})",
        [button for _, button, _weapon in rows]
        or [_button("No Inventory Weapons Found", "Equip a weapon and try again.", lambda: None)],
        description="",
    )


def _apply_item_part(label: str, field: str, part: UObject, visible: list[UObject]) -> None:
    if _item_target is None:
        return
    try:
        resolved = core._resolve_catalog_part(part)
        if resolved is None:
            core._notify(f"Could not resolve {core._short(part)} right now; see SDK log.")
            return
        _replace_item_definition(_item_target, {field: resolved})
        for row_label, option in _item_slot_options.get(field, []):
            previous = option.display_name
            option.display_name = f"{row_label}: {_overview_part_name(resolved)}"
            _refresh_native_labeled_row(previous, option.display_name)
        _refresh_global_search_options()
        _refresh_visible_item_rows(field, visible)
        _refresh_workshop_card()
        core._notify(f"{label}: {core._leaf(part)}")
    except Exception as exc:
        logging.error(f"Pandora's Workshop could not set item field {field}: {exc}")
        core._notify(f"Could not apply {label}; see SDK log.")


def _refresh_visible_item_rows(field: str, visible_parts: list[UObject]) -> None:
    """Move the item list's CURRENT marker without rebuilding its menu."""
    if _active_pause_menu is None or _item_target is None:
        return
    try:
        focused = find_focused_item(_active_pause_menu)
        match = re.match(r"^(.*\.item)\d+$", focused)
        if match is None:
            return
        base = match.group(1)
        current = getattr(_item_target.DefinitionData, field, None)
        for index in range(max(_native_row_limit(), len(visible_parts) + 16)):
            path = f"{base}{index}.mLabel.text"
            shown = str(_active_pause_menu.GetVariableString(path))
            if not shown:
                continue
            plain = shown.removeprefix("[CURRENT] ")
            for candidate in visible_parts:
                if plain in (
                    core._leaf(candidate),
                    _part_row_label(candidate, False),
                    _search_result_base_label(candidate),
                ):
                    _active_pause_menu.SetVariableString(
                        path,
                        _part_row_label(candidate, _same_object(candidate, current)),
                    )
                    break
    except Exception as exc:
        logging.info(f"Pandora's Workshop could not refresh item CURRENT markers: {exc}")


ITEM_SLOT_LISTS = {field: (definition_list, overlay_list) for _label, field, definition_list, overlay_list in ITEM_SLOTS}


def _item_part_is_valid(field: str, part: Any, target: Any = None) -> bool:
    """True when the part appears in this slot's Valid list for the item."""
    lists = ITEM_SLOT_LISTS.get(field)
    if lists is None or part is None:
        return False
    valid = _item_valid_parts(field, *lists, include_current=False, target=target)
    return any(_same_object(part, candidate) for candidate in valid)


def _clear_item_slot(label: str, field: str) -> None:
    if _item_target is None:
        return
    lists = ITEM_SLOT_LISTS.get(field)
    if lists is None or not _item_slot_allows_empty(field, *lists):
        core._notify(f"Delete blocked: {label} cannot be empty on this item.")
        return
    try:
        _replace_item_definition(_item_target, {field: None})
        for row_label, option in _item_slot_options.get(field, []):
            previous = option.display_name
            option.display_name = f"{row_label}: None"
            _refresh_native_labeled_row(previous, option.display_name)
        _refresh_workshop_card()
        core._notify(f"{label} cleared.")
    except Exception as exc:
        logging.error(f"Pandora's Workshop could not clear item field {field}: {exc}")
        core._notify(f"Could not clear {label}; see SDK log.")


def _paste_item_part(label: str, field: str, visible: list[UObject]) -> None:
    if _copied_part is None:
        core._notify("Copy a part first.")
        return
    if _item_target is None:
        return
    if not _item_part_is_valid(field, _copied_part):
        core._notify(f"Paste blocked: {core._leaf(_copied_part)} is not a Valid {label} part for this item.")
        return
    _apply_item_part(label, field, _copied_part, visible)


def _open_item_part_preview(label: str, field: str, part: UObject, visible: list[UObject]) -> None:
    global _active_preview_part
    _active_preview_part = part
    _refresh_workshop_card()
    live_part = core._resolve_catalog_part(part, quiet=True) or part
    slogan, basics, effects = _metadata_for(live_part, _item_target)
    title = _part_display_name(part)
    children: list[Any] = [
        _button("Apply This Part", "", lambda: _apply_item_part(label, field, part, visible)),
        _button("Copy This Part", "", lambda: _copy_part(part)),
        _button("Set as Comparison Part", "", lambda: _set_comparison_part(part)),
    ]
    if _comparison_part is not None and not _same_object(part, _comparison_part):
        children.append(_button(
            f"Compare with {core._leaf(_comparison_part)}", "",
            lambda: _open_part_comparison(part, _comparison_part),
        ))
    if slogan:
        children.append(_detail_button(f'"{slogan}"', title))
    children.extend(
        _detail_button(_format_basic(line), title)
        for line in basics
        if not line.startswith(("PartNumberAddend=", "PartType="))
    )
    children.extend(_detail_button(_format_item_effect(line, core._short(part)), title) for line in effects)
    if len(children) == 3:
        children.append(_button("No modifier metadata found", "", lambda: None))
    _open_nested(title, children)


def _item_part_children(label: str, field: str, parts: list[UObject]) -> list[Any]:
    global _active_item_destination, _active_part_destination, _active_preview_part
    _active_item_destination = (label, field, parts)
    _active_part_destination = None
    _active_preview_part = None
    current = None if _item_target is None else getattr(_item_target.DefinitionData, field, None)
    children: list[Any] = [
        _button("Search These Parts", "", lambda: _begin_search(label, field, parts, "item")),
        NestedOption(
            "Preview Parts and Modifiers",
            [
                _button(
                    _part_row_label(part, _same_object(part, current)), "",
                    lambda part=part: _open_item_part_preview(label, field, part, parts),
                )
                for part in parts
            ],
            description="",
        ),
    ]
    children.extend(
        _button(
            _part_row_label(part, _same_object(part, current)), "",
            lambda part=part: _apply_item_part(label, field, part, parts),
        )
        for part in parts
    )
    return children


def _open_item_slot(
    label: str,
    field: str,
    definition_list: str,
    overlay_list: str,
    mode: str,
) -> None:
    kind = "name" if field in ("PrefixItemNamePartDefinition", "TitleItemNamePartDefinition") else "physical"
    category = {
        "Body": "Bodies", "Left Side": "Left Sides", "Right Side": "Right Sides",
        "Material": "Materials", "Prefix": "Prefixes", "Title": "Titles",
    }[label]
    if mode == "valid":
        parts = _item_valid_parts(field, definition_list, overlay_list)
    else:
        catalog = _item_catalog(kind)
        parts = catalog if mode == "box" else [
            part for part in catalog if _item_part_category(part) == category
        ]
    children = _item_part_children(label, field, parts) if parts else [
        _button("No Parts Found", "", lambda: None)
    ]
    _open_nested(f"{label} - {mode.upper()}", children)


def _item_definition_objects(field: str) -> list[UObject]:
    if _item_target is None:
        return []
    current = getattr(_item_target.DefinitionData, field, None)
    if current is None:
        return []
    # Ensure all packaged item definitions have entered the live object table
    # before enumerating the current definition class.
    _item_catalog("physical")
    _item_catalog("name")
    try:
        class_name = current.Class.Name
        return sorted(
            [
                obj for obj in unrealsdk.find_all(class_name)
                if not str(obj).startswith(f"{class_name}'WillowGame.Default__")
            ],
            key=lambda obj: core._short(obj).lower(),
        )
    except Exception as exc:
        logging.warning(f"Pandora's Workshop could not index item {field}: {exc}")
        return []


def _apply_item_definition(label: str, field: str, definition: UObject) -> None:
    if _item_target is None:
        return
    try:
        _replace_item_definition(_item_target, {field: definition})
        for row_label, option in _item_definition_options.get(field, []):
            previous = option.display_name
            option.display_name = f"{row_label}: {core._leaf(definition)}"
            _refresh_native_labeled_row(previous, option.display_name)
        for obj, option in _item_definition_choice_options.get(field, []):
            option.display_name = ("[CURRENT] " if _same_object(obj, definition) else "") + core._leaf(obj)
        _refresh_workshop_card()
        core._notify(f"{label}: {core._leaf(definition)}")
    except Exception as exc:
        logging.error(f"Pandora's Workshop could not set item {field}: {exc}")
        core._notify(f"Could not apply {label}; see SDK log.")


def _open_item_definition_menu(label: str, field: str) -> None:
    objects = _item_definition_objects(field)
    current = None if _item_target is None else getattr(_item_target.DefinitionData, field, None)
    choices: list[ButtonOption] = []
    _item_definition_choice_options[field] = []
    for obj in objects:
        option = _button(
            ("[CURRENT] " if _same_object(obj, current) else "") + core._leaf(obj),
            "",
            lambda obj=obj: _apply_item_definition(label, field, obj),
        )
        choices.append(option)
        _item_definition_choice_options[field].append((obj, option))
    _open_nested(
        label,
        choices or [_button("No Definitions Found", "", lambda: None)],
    )


def _item_definition_menu(label: str, field: str) -> ButtonOption:
    current = "None" if _item_target is None else core._leaf(
        getattr(_item_target.DefinitionData, field, None)
    )
    option = _button(
        f"{label}: {current}", "",
        lambda: _open_item_definition_menu(label, field),
    )
    _item_definition_options.setdefault(field, []).append((label, option))
    return option


def _item_mode(mode: str) -> NestedOption:
    title = {
        "valid": "VALID - Compatible Item Parts",
        "invalid": "INVALID - Cross-Family Item Parts",
        "box": "PANDORA'S BOX - Every Item Part",
    }[mode]
    rows: list[Any] = []
    if mode == "box":
        rows.append(NestedOption(
            "Core Item Definitions",
            [
                _item_definition_menu("Item Type", "ItemDefinition"),
                _item_definition_menu("Item Grade", "BalanceDefinition"),
                _item_definition_menu("Manufacturer", "ManufacturerDefinition"),
            ],
            description="",
        ))
    for label, field, definition_list, overlay_list in ITEM_SLOTS:
        current = _overview_part_name(getattr(_item_target.DefinitionData, field, None))
        option = _button(
            f"{label}: {current}", "",
            lambda label=label, field=field, definition_list=definition_list, overlay_list=overlay_list:
                _open_item_slot(label, field, definition_list, overlay_list, mode),
        )
        _item_slot_options.setdefault(field, []).append((label, option))
        rows.append(option)
    return NestedOption(
        title,
        rows,
        description="",
    )


def _discard_item_changes() -> None:
    global _item_target, _item_original, _active_item_destination
    if _item_target is not None:
        _replace_item_definition(_item_target, _item_original)
        _refresh_item_name_rows(_item_target)
        core._notify(f"Restored {_item_name(_item_target)}")
    _item_target = None
    _item_original = {}
    _active_item_destination = None
    _refresh_workshop_card()


def _save_item_changes() -> bool:
    global _item_original
    if _item_target is None:
        return True
    quality, level = core._grade_components(_item_target)
    desired = (int(_item_grade_rows["Quality"].value), int(_item_grade_rows["Level"].value))
    if desired != (quality, level):
        try:
            _replace_item_definition(_item_target, {"ManufacturerGradeIndex": core._pack_grade(*desired)})
        except Exception as exc:
            core._notify(f"Could not save item grade: {exc}")
            return False
    _item_original = _item_snapshot(_item_target)
    _refresh_workshop_card()
    core._notify(f"Saved Workshop changes to {_item_name(_item_target)}")
    return True


def _duplicate_current_item() -> None:
    item = _item_target
    if item is None:
        return
    try:
        pawn = get_pc().Pawn
        manager = getattr(pawn, "InvManager", None) or getattr(pawn, "InventoryManager", None)
        if manager is None:
            raise RuntimeError("Local inventory manager is unavailable")
        snapshot = _item_snapshot(item)
        if set(snapshot) != set(ITEM_FIELDS):
            raise ValueError("Could not read the complete item definition")
        definition = unrealsdk.make_struct("ItemDefinitionData", **snapshot)
        _require_backpack_room()
        before = _manager_inventory_members([manager])
        manager.ClientAddItemToBackpack(definition, 1, False, False)
        after = _manager_inventory_members([manager])
        if not after - before:
            core._notify("No new backpack item was detected. Check inventory before retrying.")
            return
        core._notify(f"Duplicated {_item_name(item)} into the backpack.")
    except Exception as exc:
        logging.warning(f"Workshop item duplication failed: {exc}")
        core._notify(f"Item duplication failed: {exc}")


def _export_item() -> None:
    if _item_target is None:
        return
    fields = {
        field: int(value) if field == "ManufacturerGradeIndex"
        else None if value is None else core._short(value)
        for field, value in _item_snapshot(_item_target).items()
    }
    clipboard_copy(json.dumps({"format": "PandorasWorkshopItem/1", "fields": fields}, indent=2))
    core._notify("Workshop item code copied to the clipboard.")


def _resolve_item_core_definition(field: str, path: Any) -> UObject:
    """Resolve an item's ItemDefinition/BalanceDefinition by path.

    Their concrete classes differ between shields, grenade mods and class mods,
    so try every class seen on that field across the live inventory.
    """
    if not isinstance(path, str) or "." not in path:
        raise ValueError(f"Invalid {field}")
    inventory = [_item_target, *_inventory_items()]  # one inventory scan per lookup
    for item in inventory:
        if item is None:
            continue
        current = getattr(item.DefinitionData, field, None)
        if current is not None and core._short(current).lower() == path.lower():
            return current
    # Classes seen on this field in the inventory, plus their parent classes
    # (e.g. a loyalty deck's definition class may differ from a normal deck's).
    class_names: list[str] = []
    for item in inventory:
        try:
            cls = getattr(item.DefinitionData, field).Class
        except Exception:
            continue
        while cls is not None and cls.Name not in ("Object", "GBXDefinition"):
            if cls.Name not in class_names:
                class_names.append(cls.Name)
            cls = getattr(cls, "SuperField", None)
    class_names.append("Object")

    def lookup() -> UObject | None:
        for class_name in class_names:
            try:
                resolved = unrealsdk.find_object(class_name, path)
            except Exception:
                resolved = None
            if resolved is not None:
                return resolved
        return None

    # The game can unload a package's unused objects after it was first
    # loaded, so retry with a fresh package load before giving up.
    resolved = None
    for retry in (False, True):
        try:
            core._load_catalog_package(path, retry=retry)
        except Exception:
            pass
        resolved = lookup()
        if resolved is not None:
            break
    if resolved is None:
        # Last resort: scan live objects of the parent definition classes.
        wanted = path.lower()
        for class_name in class_names[:-1]:
            try:
                resolved = next(
                    (obj for obj in unrealsdk.find_all(class_name, exact=False)
                     if core._short(obj).lower() == wanted),
                    None,
                )
            except Exception:
                resolved = None
            if resolved is not None:
                break
    if resolved is None:
        logging.warning(f"Pandora's Workshop could not resolve {field} {path}; tried classes {class_names}")
        raise ValueError(f"Could not resolve {path}")
    return core._pin_definition(resolved)


# Grades flagged bInterpolateExpLevel ("big level" in WillowTree). Their codes
# store the level's low 16 bits on the quality line and its high 16 bits on
# the level line, with quality always 0, so the normal ranges do not apply.
# Only the Scorpio and the DLC4 skill-point item are player inventory; the
# rest are vehicle and turret weapons. Listed in case the live flag is absent.
BIG_LEVEL_GRADES = frozenset(path.lower() for path in (
    "gd_itemgrades.Weapons.ItemGrade_Weapon_Scorpio",
    "dlc4_gd_items.ItemGrades_SkillPoints.ItemGrade_SkillPointIncrease",
))


def _uses_big_level(balance: Any, path: str) -> bool:
    if path.lower() in BIG_LEVEL_GRADES:
        return True
    try:
        return bool(getattr(balance, "bInterpolateExpLevel", False))
    except Exception:
        return False


def _check_grade_values(balance: Any, path: str, quality: int, level: int) -> None:
    """Range-check a code's quality/level lines (the game's packed halves)."""
    if _uses_big_level(balance, path):
        for name, value in (("Quality", quality), ("Level", level)):
            if not -(1 << 15) <= value < (1 << 16):
                raise ValueError(f"{name} line {value} does not fit in 16 bits")
        return
    if quality < 0 or quality > 5:
        raise ValueError("Quality must be between 0 and 5")
    # The level line is the item level + 2 (71 = level 69); 0 means the level
    # comes from the grade's manufacturer/quality table.
    if level < 0 or level > 71:
        raise ValueError("Level must be between 0 and 71")


# WillowTree gear code: one value per line, in this order, followed by
# quantity, quality, equipped slot and level.
WILLOWTREE_ITEM_FIELDS = (
    "BalanceDefinition", "ItemDefinition", "BodyItemPartDefinition",
    "LeftSideItemPartDefinition", "RightSideItemPartDefinition",
    "MaterialItemPartDefinition", "ManufacturerDefinition",
    "PrefixItemNamePartDefinition", "TitleItemNamePartDefinition",
)


def _parse_item_code(text: str) -> dict[str, Any]:
    """Accept a WillowTree gear code (13 lines) or a Workshop JSON item code."""
    stripped = text.strip()
    if stripped.startswith("{"):
        code = json.loads(stripped)
        if code.get("format") != "PandorasWorkshopItem/1":
            raise ValueError("Expected a Workshop item code")
        fields = code["fields"]
        if set(fields) != set(ITEM_FIELDS):
            raise ValueError("Item code has missing or unexpected fields")
        return fields
    tokens = stripped.split()
    if len(tokens) != 13:
        raise ValueError(f"Expected 13 WillowTree gear fields; found {len(tokens)}")
    fields: dict[str, Any] = {
        field: None if token.lower() == "none" else token
        for field, token in zip(WILLOWTREE_ITEM_FIELDS, tokens[:9])
    }
    _quantity, quality, _slot, level = (int(value) for value in tokens[9:])
    _check_grade_values(None, tokens[0], quality, level)
    fields["ManufacturerGradeIndex"] = core._pack_grade(quality, level)
    return fields


def _import_item(text: str | None = None) -> None:
    try:
        fields = _parse_item_code(clipboard_paste() if text is None else text)
        grade = fields["ManufacturerGradeIndex"]
        if type(grade) is not int or not -(1 << 31) <= grade < (1 << 31):
            raise ValueError("Invalid packed item grade")
        changes: dict[str, Any] = {"ManufacturerGradeIndex": grade}
        for field in ("ItemDefinition", "BalanceDefinition"):
            changes[field] = _resolve_item_core_definition(field, fields[field])
        for field in ITEM_FIELDS:
            if field in ("ItemDefinition", "BalanceDefinition", "ManufacturerGradeIndex"):
                continue
            path = fields[field]
            if path is None and field != "ManufacturerDefinition":
                changes[field] = None
                continue
            if not isinstance(path, str) or "." not in path:
                raise ValueError(f"Invalid {field}")
            class_name = ("ManufacturerDefinition" if field == "ManufacturerDefinition" else
                          "ItemNamePartDefinition" if field.endswith("NamePartDefinition") else "ItemPartDefinition")
            part = core._resolve_catalog_part(core.CatalogPart(path, class_name))
            if part is None:
                raise ValueError(f"Could not resolve {path}")
            changes[field] = part
        pawn = get_pc().Pawn
        manager = getattr(pawn, "InvManager", None) or getattr(pawn, "InventoryManager", None)
        if manager is None:
            raise RuntimeError("Local inventory manager is unavailable")
        definition = unrealsdk.make_struct("ItemDefinitionData", **changes)
        # Check every part against the Valid lists for the imported item's
        # own definition and balance, not the selected item's.
        candidate = SimpleNamespace(
            DefinitionData=definition,
            PartListCollection=None,
            Class=SimpleNamespace(Name=""),
        )
        problems = []
        for label, field, definition_list, overlay_list in ITEM_SLOTS:
            part = changes.get(field)
            if part is None:
                if not _item_slot_allows_empty(field, definition_list, overlay_list, target=candidate):
                    problems.append(f"{label} cannot be empty")
            elif not _item_part_is_valid(field, part, target=candidate):
                problems.append(f"{label} {core._leaf(part)} is not Valid")
        if problems:
            logging.warning(f"Pandora's Workshop rejected invalid item code: {'; '.join(problems)}")
            raise ValueError(problems[0] + (f" (+{len(problems) - 1} more; see SDK log)" if len(problems) > 1 else ""))
        _require_backpack_room()
        before = _manager_inventory_members([manager])
        manager.ClientAddItemToBackpack(definition, 1, False, False)
        after = _manager_inventory_members([manager])
        if not after - before:
            core._notify("No new backpack item was detected. Check inventory before retrying.")
            return
        title = changes.get("TitleItemNamePartDefinition")
        name = core._leaf(title).removeprefix("Title_") if title is not None else "gear"
        core._notify(f"Imported {name} into the backpack.")
    except Exception as exc:
        logging.warning(f"Workshop item import failed: {exc}")
        core._notify(f"Gear import rejected: {exc}")


_backpack_diagnostics_logged = False


def _backpack_space() -> tuple[int | None, int | None]:
    """(items in the backpack, backpack capacity); None where unknown.

    BL1E's property names are not documented, so try the likely ones and
    log what exists once if the capacity cannot be found.
    """
    global _backpack_diagnostics_logged
    pc = get_pc()
    pawn = getattr(pc, "Pawn", None)
    manager = getattr(pawn, "InvManager", None) or getattr(pawn, "InventoryManager", None)
    capacity = None
    for owner in (manager, pc):
        for name in ("InventorySlotMax_Misc", "MaxBackpackSize", "BackpackSize", "MaxInventorySlots", "InventorySlotMax"):
            try:
                value = getattr(owner, name)
            except Exception:
                continue
            if isinstance(value, int) and value > 0:
                capacity = value
                break
        if capacity is not None:
            break
    used = None
    try:
        used = int(manager.GetUnreadiedInventoryCount())
    except Exception:
        try:
            used = sum(1 for inv in (*_inventory_weapons(), *_inventory_items()) if not getattr(inv, "bReadied", False))
        except Exception:
            used = None
    if capacity is None and not _backpack_diagnostics_logged:
        _backpack_diagnostics_logged = True
        found = []
        for owner_name, owner in (("InvManager", manager), ("PlayerController", pc)):
            try:
                cls = owner.Class
                while cls is not None:
                    for prop in cls._properties():
                        name = str(prop.Name)
                        if any(word in name.lower() for word in ("slot", "backpack", "capacity", "inventorymax")):
                            found.append(f"{owner_name}.{name}={getattr(owner, name, '?')}")
                    cls = cls.SuperField
            except Exception:
                pass
        logging.info(
            "Pandora's Workshop could not find the backpack capacity; imports are not limited. "
            f"Backpack items counted: {used}. Related properties: {', '.join(found) or 'none found'}"
        )
    return used, capacity


def _require_backpack_room() -> None:
    """Raise if the backpack is known to be full."""
    used, capacity = _backpack_space()
    if used is not None and capacity is not None and used >= capacity:
        raise ValueError(f"Backpack is full ({used}/{capacity}); make room first")


def _import_from_clipboard() -> None:
    """Import a weapon (18 lines) or gear (13 lines / Workshop JSON) code."""
    text = clipboard_paste()
    if text.lstrip().startswith("{") or len(text.split()) == 13:
        _import_item(text)
    else:
        _import_weapon(text)


def _refresh_item_name_rows(item: UObject) -> None:
    name = _item_name(item)
    for option, label in (
        (_item_selector_rows.get(core._short(item)), _item_selector_label(item)),
        (_item_selected_row, f"Selected Item: {name}"),
    ):
        if option is not None and option.display_name != label:
            previous = option.display_name
            option.display_name = label
            _refresh_native_labeled_row(previous, label)


def _open_item_editor(item: UObject) -> None:
    _confirm_selection_change(lambda: _activate_item_editor(item))


def _set_item_grade(component: str, value: int) -> None:
    """Apply a gear Quality/Level slider step live, like the weapon sliders.

    Discard still restores the snapshot taken when the item was selected.
    """
    item = _item_target
    if item is None:
        return
    quality, level = core._grade_components(item)
    if component == "Quality":
        quality = value
    else:
        level = value
    try:
        _replace_item_definition(item, {"ManufacturerGradeIndex": core._pack_grade(quality, level)})
        _refresh_workshop_card()
    except Exception as exc:
        logging.warning(f"Pandora's Workshop could not apply gear {component.lower()}: {exc}")
        core._notify(f"Could not apply {component.lower()}; see SDK log.")


def _activate_item_editor(item: UObject) -> None:
    global _item_target, _item_original, _item_selected_row
    _clear_card_preview()
    _item_target = item
    _item_slot_options.clear()
    _item_definition_options.clear()
    _item_original = _item_snapshot(item)
    quality, level = core._grade_components(item)
    _item_selected_row = _button(f"Selected Item: {_item_name(item)}", "", lambda: None)
    _item_grade_rows.clear()
    for label, value, maximum in (("Quality", quality, 5), ("Level", level, 71)):
        _item_grade_rows[label] = SliderOption(
            label, value, min(0, value), max(maximum, value), 1, True,
            description="",
            on_change_anytime=lambda _option, new_value, label=label: _set_item_grade(label, int(new_value)),
        )
    _refresh_workshop_card()
    _open_nested(
        f"ITEM WORKSHOP - {_item_name(item)}",
        [
            _item_selected_row,
            *_item_grade_rows.values(),
            _button("DUPLICATE ITEM", "Create one copy in the backpack.", _duplicate_current_item),
            _button("EXPORT ITEM CODE", "", _export_item),
            _button("IMPORT ITEM CODE", "Create a new backpack item from a WillowTree or Workshop item code.", _import_from_clipboard),
            _item_mode("valid"),
            _button("SAVE ITEM CHANGES", "", _save_item_changes),
            _button("DISCARD ITEM CHANGES", "", _discard_item_changes),
        ],
    )


def _item_selector_label(item: UObject) -> str:
    return ("[EQUIPPED] " if item.bReadied else "") + _item_name(item)


def _item_selector() -> NestedOption:
    items = _inventory_items()
    _item_selector_rows.clear()
    _item_selector_entries.clear()
    for item in items:
        _item_selector_rows[core._short(item)] = _button(
            _item_selector_label(item), core._short(item.DefinitionData.ItemDefinition),
            lambda item=item: _open_item_editor(item),
        )
        _item_selector_entries.append((_item_selector_rows[core._short(item)], item))
    return NestedOption(
        f"Shields / Grenades / Class Mods ({len(items)})",
        list(_item_selector_rows.values()) or [_button("No Inventory Items Found", "", lambda: None)],
        description="",
    )


def _export_weapon() -> None:
    session = core._session
    if session is None:
        return
    data = session.weapon.DefinitionData
    fields = (
        "BalanceDefinition", "ManufacturerDefinition", "WeaponTypeDefinition",
        "BodyPartDefinition", "GripPartDefinition", "MagazinePartDefinition",
        "BarrelPartDefinition", "SightPartDefinition", "StockPartDefinition",
        "ActionPartDefinition", "AccessoryPartDefinition", "MaterialPartDefinition",
        "PrefixPartDefinition", "TitlePartDefinition",
    )
    quality, level = core._grade_components(session.weapon)
    # WillowTree's first trailing field is carried for text compatibility,
    # but BL1 Enhanced does not expose RemainingAmmo on WillowWeapon.
    remaining = 0
    equipped_slot = int(getattr(session.weapon, "QuickSelectSlot", 0) or 0)
    lines = [core._short(getattr(data, field, None)) for field in fields]
    lines.extend((str(remaining), str(quality), str(equipped_slot), str(level)))
    clipboard_copy("\r\n".join(lines) + "\r\n")
    core._notify("WillowTree weapon code copied to the clipboard.")


WEAPON_CODE_FIELDS = (
    "BalanceDefinition", "ManufacturerDefinition", "WeaponTypeDefinition",
    "BodyPartDefinition", "GripPartDefinition", "MagazinePartDefinition",
    "BarrelPartDefinition", "SightPartDefinition", "StockPartDefinition",
    "ActionPartDefinition", "AccessoryPartDefinition", "MaterialPartDefinition",
    "PrefixPartDefinition", "TitlePartDefinition",
)


def _resolve_code_object(field: str, path: str, current: UObject | None) -> UObject | None:
    if path.lower() == "none":
        if field in WEAPON_CODE_FIELDS[:3]:
            raise ValueError(f"{field} cannot be None")
        return None
    try:
        unrealsdk.load_package(path.split(".", 1)[0])
    except Exception:
        pass
    if field in ("PrefixPartDefinition", "TitlePartDefinition"):
        class_name = "WeaponNamePartDefinition"
    elif field.endswith("PartDefinition"):
        class_name = "WeaponPartDefinition"
    elif current is not None:
        class_name = current.Class.Name
    else:
        raise ValueError(f"Cannot determine the class for {field}")
    resolved = unrealsdk.find_object(class_name, path)
    if resolved is None:
        raise ValueError(f"Unknown {field}: {path}")
    return resolved


def _import_weapon(text: str | None = None) -> None:
    """Spawn a new backpack weapon from WillowTree text.

    The selected weapon is only used as a class reference for resolving the
    core definitions; it is never modified.
    """
    global _pending_duplicate_source, _pending_duplicate_result
    session = core._session
    if session is None:
        return
    try:
        tokens = (clipboard_paste() if text is None else text).split()
        if len(tokens) != 18:
            raise ValueError(f"Expected 18 WillowTree fields; found {len(tokens)}")
        data = session.weapon.DefinitionData
        resolved = {
            field: _resolve_code_object(field, token, getattr(data, field, None))
            for field, token in zip(WEAPON_CODE_FIELDS, tokens[:14])
        }
        remaining, quality, source_slot, level = (int(value) for value in tokens[14:])
        if remaining < 0 or remaining > 999999:
            raise ValueError("Remaining ammo must be between 0 and 999999")
        if source_slot < 0 or source_slot > 4:
            raise ValueError("Equipped slot must be between 0 and 4")
        _check_grade_values(resolved["BalanceDefinition"], tokens[0], quality, level)

        pawn = getattr(get_pc(), "Pawn", None)
        manager = getattr(pawn, "InvManager", None) or getattr(pawn, "InventoryManager", None)
        if manager is None:
            raise RuntimeError("Local inventory manager is unavailable")
        definition = unrealsdk.make_struct(
            "WeaponDefinitionData",
            **resolved,
            ManufacturerGradeIndex=core._pack_grade(quality, level),
        )
        # Check every part against the Valid lists for the imported weapon's
        # own type/manufacturer/balance, not the selected weapon's.
        candidate = core.Session(
            weapon=SimpleNamespace(DefinitionData=definition, PartListCollection=None),
            original={},
        )
        problems = []
        for label, field, _collection in core.SLOTS:
            part = resolved.get(field)
            if part is None:
                if not _weapon_slot_may_be_empty(candidate, field):
                    problems.append(f"{label} cannot be empty")
            elif not _weapon_part_is_valid(candidate, field, part):
                problems.append(f"{label} {core._leaf(part)} is not Valid")
        if problems:
            logging.warning(f"Pandora's Workshop rejected invalid weapon code: {'; '.join(problems)}")
            raise ValueError(problems[0] + (f" (+{len(problems) - 1} more; see SDK log)" if len(problems) > 1 else ""))
        # Reuse the Duplicate button's native spawn path; the hook only needs a
        # non-None marker to capture the newly spawned backpack weapon.
        _require_backpack_room()
        _pending_duplicate_source = session.weapon
        _pending_duplicate_result = None
        try:
            manager.ClientAddWeaponToBackpack(definition, False, False)
            created = _pending_duplicate_result
        finally:
            _pending_duplicate_source = None
            _pending_duplicate_result = None
        if created is None:
            raise RuntimeError("Enhanced did not expose the spawned backpack weapon")
        try:
            name = core._weapon_name(created)
        except Exception:
            name = "weapon"
        core._notify(f"Imported {name} into the backpack.")
    except Exception as exc:
        logging.warning(f"Pandora's Workshop rejected clipboard weapon code: {exc}")
        core._notify(f"Clipboard import rejected: {exc}")


def _duplicate_current_weapon() -> None:
    """Create a fresh backpack weapon through Enhanced's native path."""
    global _pending_duplicate_source, _pending_duplicate_result
    session = core._session
    if session is None:
        return
    try:
        pc = get_pc()
        pawn = getattr(pc, "Pawn", None)
        manager = getattr(pawn, "InvManager", None) or getattr(pawn, "InventoryManager", None)
        if manager is None:
            raise RuntimeError("local inventory manager was unavailable")
        source = session.weapon
        _require_backpack_room()
        _pending_duplicate_source = source
        _pending_duplicate_result = None
        # This native routine spawns and initializes a new WillowWeapon before
        # adding it to the backpack. Passing the live weapon itself to an Add
        # routine moves/retires it and caused the old duplicate-button crash.
        manager.ClientAddWeaponToBackpack(
            source.DefinitionData,
            False,
            False,
        )
        duplicate = _pending_duplicate_result
        _pending_duplicate_source = None
        _pending_duplicate_result = None
        if duplicate is None:
            raise RuntimeError("Enhanced did not expose the spawned backpack weapon")
        core._notify(f"Duplicated {core._weapon_name(source)} into the backpack.")
    except Exception as exc:
        _pending_duplicate_source = None
        _pending_duplicate_result = None
        logging.warning(f"Pandora's Workshop could not duplicate the selected weapon: {exc}")
        if isinstance(exc, ValueError):
            # Expected refusals (e.g. a full backpack) say why on screen.
            core._notify(f"Could not duplicate the weapon: {exc}")
        else:
            core._notify("Could not duplicate the weapon; see SDK log.")


def _set_grade(component: str, value: int, redraw: bool = False) -> None:
    session = core._session
    if session is None:
        return
    quality, level = core._grade_components(session.weapon)
    if component == "quality":
        quality = max(0, min(5, int(value)))
    else:
        level = max(0, min(71, int(value)))
    session.weapon.DefinitionData.ManufacturerGradeIndex = core._pack_grade(quality, level)
    session.dirty = True
    core._rebuild(session.weapon)
    _refresh_workshop_card()
    if _grade_header is not None:
        _grade_header.display_name = f"Quality / Level ({quality} / {level})"
    if "quality" in _grade_sliders:
        object.__setattr__(_grade_sliders["quality"], "value", quality)
    if "level" in _grade_sliders:
        object.__setattr__(_grade_sliders["level"], "value", level)
    core._notify(f"Quality {quality}; level {level}")
    # A button-driven Max change does not pass through the slider handler, so
    # the native row otherwise retains its old thumb/value until reopened.
    if redraw and _active_pause_menu is not None:
        try:
            draw_custom_menu(_active_pause_menu)
        except Exception as exc:
            logging.warning(f"Pandora's Workshop could not redraw grade sliders: {exc}")


def _grade_options(quality: int, level: int) -> list[Any]:
    quality_slider = SliderOption("Quality", quality, 0, 5, 1, True, description="", on_change_anytime=lambda _o, value: _set_grade("quality", int(value)))
    level_slider = SliderOption("Level", level, 0, 71, 1, True, description="", on_change_anytime=lambda _o, value: _set_grade("level", int(value)))
    _grade_sliders["quality"] = quality_slider
    _grade_sliders["level"] = level_slider
    return [
        quality_slider,
        _button("Set Quality to Max", "Set quality to 5.", lambda: _set_grade("quality", 5, True)),
        level_slider,
        _button("Set Level to Max", "Set stored level to 71.", lambda: _set_grade("level", 71, True)),
    ]


def _finish(restore: bool) -> None:
    global _active_pause_menu, _workshop_root_screen, _pending_requip
    global _pending_requip_ticks, _pending_requip_stage, _pending_requip_slot
    global _pending_requip_backpack, _pending_requip_readied
    global _pending_menu_close, _pending_menu_close_ticks
    global _item_target, _item_original
    if _item_target is not None:
        if restore:
            _discard_item_changes()
        elif not _save_item_changes():
            _resume_workshop_card()
            return
    weapon_changed = core._session is not None and core._session.dirty
    edited_weapon = core._session.weapon if core._session is not None else None
    was_equipped = edited_weapon is not None and _same_object(edited_weapon, core._current_weapon())
    original_slot = int(getattr(edited_weapon, "QuickSelectSlot", 0) or 0) if edited_weapon is not None else 0
    if not weapon_changed:
        core._session = None
    elif restore:
        core._cancel()
    else:
        core._apply()
    _item_target = None
    _item_original = {}
    menu = _active_pause_menu
    _close_workshop_card(menu)
    _active_pause_menu = None
    _workshop_root_screen = None
    if menu is not None:
        try:
            menu.Close()
        except Exception as exc:
            logging.warning(f"Pandora's Workshop UI could not close pause menu: {exc}")
    if not restore and weapon_changed and was_equipped and edited_weapon is not None and original_slot > 0:
        _pending_requip = edited_weapon
        _pending_requip_ticks = 15
        _pending_requip_stage = 0
        _pending_requip_slot = original_slot
        _pending_requip_backpack = None
        _pending_requip_readied = None
        core._notify("Changes applied; refreshing the equipped weapon.")


def _confirm_discard() -> None:
    global _card_modal_hidden
    if not _has_unsaved_changes():
        _finish(False)
        return
    # A nested generic-options confirmation corrupts Enhanced's ScreenStack:
    # NO deactivates the Workshop root and YES leaves an empty custom screen
    # behind for the next Escape press. OptionBox is independent of that stack.
    _card_modal_hidden = True
    try:
        core._show_box(
            "EXIT",
            "",
            [
                ("NO - KEEP EDITING", '<p align="center">Return to Pandora\'s Workshop.</p>', _resume_workshop_card),
                ("REVERT UNSAVED CHANGES AND EXIT", '<p align="center">Undo current unsaved edits and close. Previously saved edits stay saved.</p>', lambda: _finish(True)),
                ("Save Changes and Exit", '<p align="center">Keep current edits and close the Workshop.</p>', lambda: _finish(False)),
            ],
            _resume_workshop_card,
        )
    except Exception:
        _card_modal_hidden = False
        raise


def _resume_workshop_card() -> None:
    global _card_modal_hidden
    _card_modal_hidden = False


def _root_options() -> NestedOption:
    global _equipped_header, _grade_header
    _slot_options.clear()
    _item_slot_options.clear()
    _definition_options.clear()
    _item_definition_options.clear()
    _definition_choice_options.clear()
    _item_definition_choice_options.clear()
    _part_buttons.clear()
    _preview_options.clear()
    _global_search_options.clear()
    _grade_sliders.clear()
    session = core._session
    assert session is not None
    quality, level = core._grade_components(session.weapon)
    valid_slots = [_valid_slot(*slot) for slot in core.SLOTS]
    _equipped_header = ButtonOption(f"Selected Weapon: {core._weapon_name(session.weapon)}")
    _grade_header = NestedOption(
        f"Quality / Level ({quality} / {level})",
        _grade_options(quality, level),
        description="",
    )
    return NestedOption(
        "PANDORA'S WORKSHOP",
        [
            _equipped_header,
            _weapon_selector(),
            _item_selector(),
            NestedOption(
                "VALID - Compatible Parts",
                valid_slots,
                description="",
            ),
            _grade_header,
            _button("Export Weapon to Clipboard", "WillowTree-compatible text format.", _export_weapon),
            _button("Import from Clipboard", "Create a new backpack weapon or gear item from a WillowTree code.", _import_from_clipboard),
            _button("Duplicate Current Weapon", "Create an unequipped backpack copy of the selected weapon.", _duplicate_current_weapon),
            _button("SAVE CHANGES AND CLOSE", "Keep all changes made during this session.", lambda: _finish(False)),
            _button("DISCARD CHANGES AND CLOSE", "Ask before restoring the definition captured when this session opened.", _confirm_discard),
        ],
        description="",
    )


def _hud_movie() -> UObject | None:
    try:
        return get_pc().myHUD.HUDMovie
    except Exception:
        return None


def _set_friends_visible(menu: UObject | None, visible: bool) -> None:
    # The panel normally belongs to the pause movie, but also try the HUD
    # movie because Enhanced ships several aspect/platform-specific layouts.
    movies = [candidate for candidate in (menu, _hud_movie()) if candidate is not None]
    for movie in movies:
        for root in FRIENDS_ROOTS:
            try:
                movie.SetVariableBool(f"{root}._visible", visible)
            except Exception:
                pass


def _native_card_helper() -> UObject | None:
    """Return the game's static card renderer without creating a GFx movie."""
    try:
        return unrealsdk.find_object(
            "InventoryCardGFx", "WillowGame.Default__InventoryCardGFx"
        )
    except Exception:
        try:
            klass = unrealsdk.find_class("WillowGame.InventoryCardGFx")
            return getattr(klass, "ClassDefaultObject", None)
        except Exception:
            return None


def _set_hud_comparison(hud: UObject, inventory: UObject | None) -> None:
    """Populate WillowHUD's fixed comparison array used by its pickup card."""
    try:
        hud.ItemComparison[0] = inventory
        hud.ItemComparison[1] = None
        return
    except Exception:
        pass
    try:
        hud.ItemComparison = (inventory, None)
    except Exception as exc:
        logging.info(f"Pandora's Workshop could not set HUD comparison data: {exc}")


@hook("WillowGame.ItemPickupGFxMovie:CreateBackupRenderTarget", hook_type=Type.POST_UNCONDITIONAL)
def _workshop_card_render_resolution(obj: UObject, _args: WrappedStruct, _ret: Any, _func: BoundFunction) -> None:
    """Replace the stock 512px target before Start assigns it to GFx."""
    if _workshop_card_movie is None or core._short(obj) != core._short(_workshop_card_movie):
        return
    _upgrade_card_render_target(obj)


CARD_TARGET_WIDTH = 1024


def _upgrade_card_render_target(movie: UObject) -> bool:
    """Swap the card's render target for a 1024-wide one with the same shape.

    Returns True if the movie now has a full-resolution target.
    """
    try:
        original = movie.MyRenderTexture
        stock_w = float(original.SizeX) if original is not None else 0.0
        stock_h = float(original.SizeY) if original is not None else 0.0
        if stock_w >= CARD_TARGET_WIDTH:
            return True
        manager = get_pc().GetWillowGlobals().GetRenderTextureManager()
        # Keep the stock target's proportions. The card movie is stretched to
        # fill whatever target it gets, so a square target squeezes the card.
        width, height = CARD_TARGET_WIDTH, CARD_TARGET_WIDTH
        if stock_w > 0 and stock_h > 0 and abs(stock_w / stock_h - 1.0) > 0.02:
            height = max(64, int(round(CARD_TARGET_WIDTH * stock_h / stock_w)))
        target = manager.GetRenderTexture(width, height, True)
        if target is None:
            return False
        movie.MyRenderTexture = target
        if original is not None and core._short(original) != core._short(target):
            manager.FreeRenderTexture(original)
        return float(target.SizeX) >= CARD_TARGET_WIDTH
    except Exception as exc:
        logging.info(f"Pandora's Workshop retained stock card resolution: {exc}")
        return False


def _card_texture_size(movie: UObject | None) -> tuple[int, int]:
    try:
        texture = movie.MyRenderTexture
        return int(texture.SizeX), int(texture.SizeY)
    except Exception:
        return 0, 0


def _initialize_workshop_card() -> None:
    """Spawn and start a private card using Enhanced's real movie definition."""
    global _workshop_card_active, _workshop_card_movie, _workshop_card_saved_look
    global _workshop_card_saved_comparison, _workshop_card_original_flags
    global _card_startup_ticks, _card_resolution_retries
    if not CARD_PREVIEW_ENABLED or not _workshop_card_requested or (core._session is None and _item_target is None):
        return
    try:
        pc = get_pc()
        hud = pc.myHUD
        inventory = _item_target if _item_target is not None else core._session.weapon
        definition = pc.GetWillowGlobals().GetGlobalsDefinition().ItemPickupCardMovie
        core._pin_definition(definition)
        movie = definition.SpawnPlayerMovie(pc, None)
        if movie is None:
            raise RuntimeError("Enhanced's card definition did not spawn a movie")
        _workshop_card_movie = movie
        _workshop_card_original_flags = int(movie.ObjectFlags)
        movie.ObjectFlags |= ObjectFlags.KEEP_ALIVE
        _workshop_card_saved_look = getattr(hud, "SavedLookAtInventory", None)
        _workshop_card_saved_comparison = (hud.ItemComparison[0], hud.ItemComparison[1])
        hud.SavedLookAtInventory = inventory
        _set_hud_comparison(hud, inventory)
        movie.bShouldGetCompareAgainstThing = False
        # The cooked template's ExternalInterface points at the template itself.
        # Route ActionScript callbacks to this live instance before Start caches
        # the interface. The Workshop pauses game time; use GFx TM_Real (1).
        movie.SetExternalInterface(movie)
        movie.SetTimingMode(1)
        movie.bTickFirstFrame = True
        _workshop_card_active = True
        # ItemPickupGFxMovie.Start creates MyRenderTexture, assigns RenderTexture,
        # sets RenderTextureMode=2 and initializes the owner. InitializeFrom on
        # an existing HUD object never performed this lifecycle for our preview.
        # The definition can hand back a card that already has a (stock,
        # 512px) target, in which case Start skips CreateBackupRenderTarget
        # and the hook above never runs. Upgrade it directly first.
        if movie.MyRenderTexture is not None:
            _upgrade_card_render_target(movie)
        if not movie.Start(False):
            raise RuntimeError("ItemPickupGFxMovie.Start returned false")
        tex_w, tex_h = _card_texture_size(movie)
        if 0 < tex_w < CARD_TARGET_WIDTH:
            if _card_resolution_retries < 1:
                _card_resolution_retries += 1
                logging.info("Pandora's Workshop card started at low resolution; restarting the card once")
                _restart_workshop_card()
                return
            logging.info("Pandora's Workshop card is still low resolution after a restart; keeping it")
        movie.PickupMesh = inventory.GetInvMesh()
        movie.Pause(False)
        # Initialize the root's TurnOnPickupCard function before calling Show.
        # The weapon_card SWF signals extReadyForInventoryInfo from frame 4
        # of its ten-frame card animation at 24 fps, not its first frame.
        movie.Advance(0.05)
        movie.Show(True)
        # Invoke the actual Flash entry point: Show also manages the pickup
        # particle, and does not guarantee playback of this private card.
        movie.SetRenderingEnabled(True)
        movie.Invoke("TurnOnPickupCard", [])
        _card_startup_ticks = 24
        _refresh_workshop_card()
        if DEBUG_LOGGING:
            logging.info(f"Pandora's Workshop card started: definition={core._short(definition)} movie={core._short(movie)} interface={core._short(movie.ExternalInterface)} ready={movie.bReadyToDisplay} texture={core._short(movie.MyRenderTexture)}")
    except Exception as exc:
        logging.error(f"Pandora's Workshop could not acquire the HUD item card: {exc}")
        _close_workshop_card()
        core._notify("Item card unavailable; Workshop editing remains active.")


@hook("WillowGame.ItemPickupGFxMovie:extReadyForInventoryInfo", hook_type=Type.POST_UNCONDITIONAL)
def _workshop_card_ready(obj: UObject, _args: WrappedStruct, _ret: Any, _func: BoundFunction) -> None:
    global _pending_layout_ticks
    if _workshop_card_active and _workshop_card_movie is not None and core._short(obj) == core._short(_workshop_card_movie):
        _refresh_workshop_card()
        _pending_layout_ticks = 2
        if DEBUG_LOGGING:
            logging.info("Pandora's Workshop native card ready callback received")


# Weapon/item shown on the card while a selector-list row is highlighted.
_card_preview_override: UObject | None = None
_card_preview_signature: Any = None
_weapon_selector_entries: list[tuple[ButtonOption, UObject]] = []
_item_selector_entries: list[tuple[ButtonOption, UObject]] = []


def _is_weapon(inventory: Any) -> bool:
    try:
        return "WillowWeapon" in str(inventory.Class)
    except Exception:
        return False


def _card_inventory() -> UObject:
    """What the card shows: a highlighted selector row, else the current edit."""
    if _card_preview_override is not None:
        return _card_preview_override
    return _item_target if _item_target is not None else core._session.weapon


def _hovered_selector_object(menu: UObject) -> UObject | None:
    """The weapon/item behind the highlighted selector row, if any."""
    label = _focused_label(menu)
    if not label:
        return None
    matches = [obj for option, obj in (*_weapon_selector_entries, *_item_selector_entries)
               if option.display_name == label]
    if len(matches) <= 1:
        return matches[0] if matches else None
    # Identical names: count same-named rows above the cursor to pick the right one.
    try:
        focused = find_focused_item(menu)
        match = re.match(r"^(.*\.item)(\d+)$", focused)
        if match is None:
            return matches[0]
        base, index = match.group(1), int(match.group(2))
        above = sum(
            1 for row in range(index)
            if str(menu.GetVariableString(f"{base}{row}.mLabel.text")) == label
        )
        return matches[min(above, len(matches) - 1)]
    except Exception:
        return matches[0]


def _update_card_preview(menu: UObject) -> None:
    global _card_preview_override
    hovered = _hovered_selector_object(menu)
    if hovered is _card_preview_override:
        return
    if hovered is not None and _card_preview_override is not None and str(hovered) == str(_card_preview_override):
        return
    _card_preview_override = hovered
    _refresh_workshop_card()


def _clear_card_preview() -> None:
    global _card_preview_override, _card_preview_signature
    _card_preview_override = None
    _card_preview_signature = None


def _refresh_workshop_card() -> None:
    """Refresh the edited item labels and visible HUD pickup card."""
    if _item_target is not None:
        _refresh_item_name_rows(_item_target)
    if not CARD_PREVIEW_ENABLED or not _workshop_card_active or _workshop_card_movie is None:
        return
    if not getattr(_workshop_card_movie, "bReadyToDisplay", False):
        return
    if core._session is None and _item_target is None:
        return
    inventory = _card_inventory()
    try:
        hud = get_pc().myHUD
        hud.SavedLookAtInventory = inventory
        _set_hud_comparison(hud, inventory)
        if _is_weapon(inventory):
            inventory.CacheWeaponCard()
        else:
            inventory.CacheItemCard()
        helper = _native_card_helper()
        if helper is None:
            raise RuntimeError("InventoryCardGFx renderer was unavailable")
        # extReadyForInventoryInfo in WillowHUDGFxMovie uses card index zero
        # for player one.  Populate it directly as well so edits update without
        # waiting for another ActionScript ready callback.
        helper.SetInventoryCard(_workshop_card_movie, 0, inventory, None, False)
        _refresh_workshop_thumbnail(inventory)
    except Exception as exc:
        logging.error(f"Pandora's Workshop could not refresh the HUD item card: {exc}")


def _refresh_workshop_thumbnail(inventory: UObject) -> None:
    """Render an inventory-style mesh copy into the Flash image resource."""
    global _workshop_card_mesh, _workshop_thumbnail, _workshop_thumbnail_manager
    global _workshop_mesh_original_flags
    movie = _workshop_card_movie
    if movie is None:
        return
    navigator = unrealsdk.find_object("CellsNavigator", "WillowGame.Default__CellsNavigator")
    mesh = navigator.ConstructInvMesh(inventory)
    if mesh is None:
        raise RuntimeError("Inventory thumbnail mesh could not be constructed")
    if _workshop_thumbnail_manager is None:
        _workshop_thumbnail_manager = get_pc().GetWillowGlobals().GetRenderTextureManager()
    manager = _workshop_thumbnail_manager
    if _workshop_thumbnail is None:
        # Thumbnail_Update (1) refreshes after SetThumbnailMesh, matching the
        # inventory pipeline without continuously rendering a static weapon.
        _workshop_thumbnail = manager.GetThumbnail(512, 256, 1, 512, 256)
    previous_mesh, previous_flags = _workshop_card_mesh, _workshop_mesh_original_flags
    _workshop_mesh_original_flags = int(mesh.ObjectFlags)
    mesh.ObjectFlags |= ObjectFlags.KEEP_ALIVE
    _workshop_card_mesh = mesh
    manager.SetThumbnailMesh(_workshop_thumbnail, mesh)
    movie.PickupMesh = mesh
    bound = movie.SetExternalTexture(str(movie.WeapTexName), _workshop_thumbnail)
    if previous_mesh is not None and previous_flags is not None:
        previous_mesh.ObjectFlags = (int(previous_mesh.ObjectFlags) & ~int(ObjectFlags.KEEP_ALIVE)) | (previous_flags & int(ObjectFlags.KEEP_ALIVE))
    if DEBUG_LOGGING:
        logging.info(f"Pandora's Workshop thumbnail: resource={movie.WeapTexName} bound={bound} texture={core._short(_workshop_thumbnail)} mesh={core._short(mesh)}")


_card_resolution_retries = 0


def _restart_workshop_card() -> None:
    """Close the private card and open a fresh one a few UI ticks later."""
    menu = _active_pause_menu
    _close_workshop_card(menu)
    if menu is not None:
        _open_workshop_card(menu, reset_retries=False)


def _open_workshop_card(menu: UObject, reset_retries: bool = True) -> None:
    global _workshop_card_active, _workshop_card_requested, _workshop_card_movie
    global _pending_card_open_ticks
    global _card_canvas_logged, _card_canvas_failed
    global _card_modal_hidden, _card_resolution_retries
    _clear_card_preview()
    if reset_retries:
        _card_resolution_retries = 0
    _card_modal_hidden = False
    _card_canvas_logged = False
    _card_canvas_failed = False
    _set_friends_visible(menu, False)
    _workshop_card_movie = None
    _workshop_card_active = False
    _workshop_card_requested = CARD_PREVIEW_ENABLED
    # Let the pause screen and its first layout pass finish before asking HUD
    # for the already-supported pickup-card overlay.
    _pending_card_open_ticks = 6 if CARD_PREVIEW_ENABLED else 0


def _close_workshop_card(menu: UObject | None = None) -> None:
    _clear_card_preview()
    global _workshop_card_active, _workshop_card_requested
    global _workshop_card_movie, _workshop_card_mesh, _pending_card_open_ticks
    global _workshop_card_saved_look
    global _workshop_card_saved_comparison, _workshop_card_original_flags
    global _workshop_thumbnail, _workshop_thumbnail_manager, _workshop_mesh_original_flags
    _set_friends_visible(menu, True)
    _workshop_card_requested = False
    _pending_card_open_ticks = 0
    if not CARD_PREVIEW_ENABLED:
        _workshop_card_active = False
        _workshop_card_movie = None
        _workshop_card_mesh = None
        return
    movie = _workshop_card_movie
    _workshop_card_active = False
    try:
        hud = get_pc().myHUD
        if _workshop_card_saved_comparison is not None:
            hud.SavedLookAtInventory = _workshop_card_saved_look
            hud.ItemComparison = _workshop_card_saved_comparison
    except Exception as exc:
        logging.info(f"Pandora's Workshop card HUD restore differed: {exc}")
    if movie is not None:
        try:
            movie.Show(False)
            movie.Close(False)
        except Exception as exc:
            logging.info(f"Pandora's Workshop private card close differed: {exc}")
        finally:
            if _workshop_card_original_flags is not None:
                movie.ObjectFlags = (int(movie.ObjectFlags) & ~int(ObjectFlags.KEEP_ALIVE)) | (_workshop_card_original_flags & int(ObjectFlags.KEEP_ALIVE))
    if _workshop_thumbnail_manager is not None and _workshop_thumbnail is not None:
        try:
            _workshop_thumbnail_manager.SetThumbnailMesh(_workshop_thumbnail, None)
            _workshop_thumbnail_manager.FreeThumbnail(_workshop_thumbnail)
        except Exception as exc:
            logging.info(f"Pandora's Workshop thumbnail cleanup differed: {exc}")
    if _workshop_card_mesh is not None and _workshop_mesh_original_flags is not None:
        _workshop_card_mesh.ObjectFlags = (int(_workshop_card_mesh.ObjectFlags) & ~int(ObjectFlags.KEEP_ALIVE)) | (_workshop_mesh_original_flags & int(ObjectFlags.KEEP_ALIVE))
    _workshop_thumbnail = None
    _workshop_thumbnail_manager = None
    _workshop_mesh_original_flags = None
    _workshop_card_movie = None
    _workshop_card_mesh = None
    _workshop_card_saved_look = None
    _workshop_card_saved_comparison = None
    _workshop_card_original_flags = None


_card_canvas_logged = False
_card_canvas_failed = False

# Width/height of the card movie's stage, measured from in-game screenshots
# (stock card vs. the square-target Workshop card). Used only if the real
# stage size cannot be read from the running movie or its SWF header.
CARD_FALLBACK_ASPECT = 1.68
_card_stage_aspect: float | None = None
# Right edge of the card as a fraction of screen width (the original layout
# placed a 35%-wide card at 63.5%, ending at 98.5%).
CARD_RIGHT_EDGE = 0.985
card_size_option = SliderOption(
    "Card Preview Size",
    40, 30, 60, 1, True,
    description="Width of the Workshop item card preview, as a percentage of the screen width.",
)


def _plausible_card_aspect(width: float, height: float) -> float | None:
    if not (math.isfinite(width) and math.isfinite(height)) or width <= 0 or height <= 0:
        return None
    aspect = width / height
    # A square result means we read the render target, not the stage.
    return aspect if 1.1 <= aspect <= 2.5 else None


def _swf_header_aspect(movie: UObject) -> float | None:
    """Read the frame size from the card SWF's header (FWS/CWS/GFX/CFX)."""
    info = getattr(movie, "MovieInfo", None)
    raw = getattr(info, "RawData", None)
    if raw is None:
        return None
    head = bytes(int(raw[i]) & 0xFF for i in range(min(len(raw), 4096)))
    signature = head[:3]
    if signature in (b"FWS", b"GFX"):
        body = head[8:]
    elif signature in (b"CWS", b"CFX"):
        body = zlib.decompressobj().decompress(head[8:])
    else:
        return None
    if len(body) < 17:
        return None
    bits = int.from_bytes(body[:17], "big")
    nbits = bits >> (17 * 8 - 5)

    def field(index: int) -> int:
        shift = 17 * 8 - 5 - nbits * (index + 1)
        value = (bits >> shift) & ((1 << nbits) - 1)
        return value - (1 << nbits) if value & (1 << (nbits - 1)) else value

    x_min, x_max, y_min, y_max = (field(i) for i in range(4))
    return _plausible_card_aspect(float(x_max - x_min), float(y_max - y_min))


def _card_content_aspect(movie: UObject, texture: UObject) -> float:
    """Width/height the card should be drawn at."""
    global _card_stage_aspect
    texture_aspect = _plausible_card_aspect(float(texture.SizeX), float(texture.SizeY))
    if texture_aspect is not None:
        return texture_aspect
    if _card_stage_aspect is None:
        source, aspect = "fallback", None
        try:
            aspect = _plausible_card_aspect(
                float(movie.GetVariableNumber("Stage.width")),
                float(movie.GetVariableNumber("Stage.height")),
            )
            source = "Stage"
        except Exception:
            aspect = None
        if aspect is None:
            try:
                aspect = _swf_header_aspect(movie)
                source = "SWF header"
            except Exception as exc:
                logging.info(f"Pandora's Workshop could not read the card SWF header: {exc}")
                aspect = None
        if aspect is None:
            source, aspect = "fallback", CARD_FALLBACK_ASPECT
        _card_stage_aspect = aspect
        logging.info(f"Pandora's Workshop card aspect {aspect:.3f} ({source})")
    return _card_stage_aspect


def _workshop_layout_signature(menu: UObject) -> tuple:
    focused = find_focused_item(menu)
    parent = focused.rsplit(".item", 1)[0]
    return (
        focused,
        menu.GetVariableNumber(parent + ".mItems.length"),
        menu.GetVariableString("_level0.title.htmlText"),
        menu.GetVariableNumber(focused + ".mLabel._yscale"),
        menu.GetVariableString(focused + ".mLabel.text"),
    )


@hook("Engine.GameViewportClient:PostRender")
def _prepare_workshop_layout(_obj: UObject, _args: WrappedStruct, _ret: Any, _func: BoundFunction) -> None:
    """Style new Flash rows before the viewport renders, without a timed resize."""
    global _pending_layout_ticks, _layout_markers_pending, _layout_signature
    menu = _active_pause_menu
    if menu is None:
        _layout_signature = None
        return
    try:
        signature = _workshop_layout_signature(menu)
        global _card_preview_signature
        if signature != _card_preview_signature:
            _card_preview_signature = signature
            _update_card_preview(menu)
        if _pending_layout_ticks == 0 and signature == _layout_signature:
            return
        _pending_layout_ticks = 0
        if _layout_markers_pending:
            _layout_markers_pending = False
            _refresh_visible_current_markers(menu)
        _expand_workshop_rows(menu)
        # Capture the styled state, not the values that triggered the repair.
        # Late-created Flash rows change the count and get styled next frame.
        _layout_signature = _workshop_layout_signature(menu)
    except Exception as exc:
        logging.info(f"Pandora's Workshop layout preparation failed: {exc}")


@hook("Engine.GameViewportClient:PostRender", hook_type=Type.POST_UNCONDITIONAL)
def _draw_workshop_card(_obj: UObject, args: WrappedStruct, _ret: Any, _func: BoundFunction) -> None:
    """Composite the native card texture above the pause menu at screen right."""
    global _card_canvas_logged, _card_canvas_failed
    if not _workshop_card_active or _workshop_card_movie is None or _card_canvas_failed or _card_modal_hidden:
        return
    if not getattr(_workshop_card_movie, "bReadyToDisplay", False):
        return
    try:
        canvas = args.Canvas
        texture = _workshop_card_movie.MyRenderTexture
        if texture is None:
            return
        width, height = float(canvas.SizeX), float(canvas.SizeY)
        tex_width, tex_height = float(texture.SizeX), float(texture.SizeY)
        if tex_width <= 0 or tex_height <= 0:
            return
        # Draw at the card's real proportions, not the render target's.
        aspect = _card_content_aspect(_workshop_card_movie, texture)
        card_width = width * float(card_size_option.value) / 100.0
        card_height = card_width / aspect
        if card_height > height * 0.80:
            card_height = height * 0.80
            card_width = card_height * aspect
        # Keep the right edge fixed so a larger card grows toward the menu.
        card_x = max(0.0, width * CARD_RIGHT_EDGE - card_width)
        old_x, old_y, old_color = canvas.CurX, canvas.CurY, canvas.DrawColor
        try:
            # The pickup SWF includes transparent padding around its card.
            # Account for it when placing the visible frame beside Workshop.
            canvas.SetPos(card_x, height * 0.05)
            canvas.SetDrawColor(255, 255, 255, 255)
            canvas.DrawTile(texture, card_width, card_height, 0.0, 0.0, tex_width, tex_height)
        finally:
            canvas.SetPos(old_x, old_y)
            canvas.DrawColor = old_color
        if DEBUG_LOGGING and not _card_canvas_logged:
            logging.info(f"Pandora's Workshop card diagnostic: texture={int(tex_width)}x{int(tex_height)} ready={getattr(_workshop_card_movie, 'bReadyToDisplay', None)} mesh={getattr(_workshop_card_movie, 'PickupMesh', None)} render_mode={getattr(_workshop_card_movie, 'RenderTextureMode', None)} canvas={int(width)}x{int(height)}")
            _card_canvas_logged = True
    except Exception as exc:
        _card_canvas_failed = True
        logging.error(f"Pandora's Workshop Canvas card display failed: {exc}")


def _open_on_pause(menu: UObject) -> None:
    global _pending_open, _opening, _active_pause_menu, _workshop_root_screen, _pending_layout_ticks
    if not _pending_open or _opening or core._session is None:
        return
    _opening = True
    try:
        _active_pause_menu = menu
        create_nested_options_menu(menu, _root_options())
        _pending_layout_ticks = 2
        _workshop_root_screen = menu.ScreenStack[-1] if menu.ScreenStack else None
        _pending_open = False
        _open_workshop_card(menu)
    except Exception as exc:
        logging.error(f"Pandora's Workshop could not open native screen: {exc}")
        core._notify("Pandora's Workshop screen failed; see SDK log.")
    finally:
        _opening = False


@hook("WillowGame.WillowGFxMenuScreenGeneric:Screen_Deactivate", hook_type=Type.POST_UNCONDITIONAL)
def _workshop_screen_closed(
    obj: UObject,
    _args: WrappedStruct,
    _ret: Any,
    _func: BoundFunction,
) -> None:
    """Treat backing out of the Workshop root as Cancel, never implicit Apply."""
    global _active_pause_menu, _workshop_root_screen
    if _workshop_root_screen is None or obj != _workshop_root_screen:
        return
    _workshop_root_screen = None
    if core._session is not None:
        core._cancel()
        logging.info("Pandora's Workshop restored the starting weapon after Escape")
    if _item_target is not None:
        _discard_item_changes()
    _close_workshop_card(_active_pause_menu)
    _active_pause_menu = None


@hook("WillowGame.WillowGFxMenuScreenGeneric:Screen_Activate", hook_type=Type.POST_UNCONDITIONAL)
def _workshop_screen_activated(
    _obj: UObject,
    _args: WrappedStruct,
    _ret: Any,
    _func: BoundFunction,
) -> None:
    """Reapply the widened row geometry after every submenu/back transition."""
    global _pending_layout_ticks, _layout_markers_pending
    if _active_pause_menu is not None and _workshop_root_screen is not None:
        _pending_layout_ticks = 2
        _layout_markers_pending = True


@hook("WillowGame.WillowGFxMenuPause:extInitMain", hook_type=Type.POST_UNCONDITIONAL)
def _pause_ready(obj: UObject, _args: WrappedStruct, _ret: Any, _func: BoundFunction) -> None:
    _open_on_pause(obj)


@hook("GearboxFramework.GearboxGFxMovie:PlaySpecialUISound", hook_type=Type.POST_UNCONDITIONAL)
def _workshop_focus_layout(obj: UObject, _args: WrappedStruct, _ret: Any, _func: BoundFunction) -> None:
    # Focus/unfocus changes the native row's timeline and can restore its
    # authored multiline text field. Reapply after that transition settles.
    global _pending_layout_ticks
    if _active_pause_menu is not None and obj == _active_pause_menu:
        _pending_layout_ticks = 2


@hook("WillowGame.WillowUIInteraction:TickImp")
def _delayed_requip(_obj: UObject, _args: WrappedStruct, _ret: Any, _func: BoundFunction) -> None:
    global _pending_requip, _pending_requip_ticks, _pending_requip_stage, _pending_requip_slot
    global _pending_requip_backpack, _pending_requip_readied
    global _pending_menu_close, _pending_menu_close_ticks, _pending_discard_confirmation_ticks
    global _pending_layout_ticks, _pending_card_open_ticks, _card_startup_ticks
    global _pending_part_change
    if _pending_part_change is not None and not _part_change_busy and time.monotonic() - _last_part_change_time >= 0.15:
        pending = _pending_part_change
        _pending_part_change = None
        if pending[0] is core._session and _active_pause_menu is not None:
            _apply_part_now(*pending[1:])
    if _pending_card_open_ticks > 0:
        _pending_card_open_ticks -= 1
        if _pending_card_open_ticks == 0:
            _initialize_workshop_card()
    if _card_startup_ticks > 0:
        movie = _workshop_card_movie
        if not _workshop_card_active or movie is None or movie.bReadyToDisplay:
            _card_startup_ticks = 0
        else:
            _card_startup_ticks -= 1
            try:
                # Give each animation frame a separate UI tick while paused.
                movie.Advance(1.0 / 24.0)
                if _card_startup_ticks == 0 and not movie.bReadyToDisplay:
                    logging.warning(f"Pandora's Workshop card animation stalled: frame={movie.GetVariableNumber('_root.inventory._currentframe')} total={movie.GetVariableNumber('_root.inventory._totalframes')} visible={movie.GetVariableBool('_root.inventory._visible')} rendering_disabled={movie.bRenderingDisabled}")
            except Exception as exc:
                _card_startup_ticks = 0
                logging.error(f"Pandora's Workshop card animation failed: {exc}")
    if _pending_discard_confirmation_ticks > 0:
        _pending_discard_confirmation_ticks -= 1
        if _pending_discard_confirmation_ticks == 0 and _active_pause_menu is not None:
            _confirm_discard()
    if _pending_menu_close is not None:
        if _pending_menu_close_ticks > 0:
            _pending_menu_close_ticks -= 1
        else:
            try:
                _pending_menu_close.Close()
            except Exception as exc:
                logging.warning(f"Pandora's Workshop could not finish closing its menu: {exc}")
            _pending_menu_close = None
    weapon = _pending_requip
    if weapon is None:
        return
    if _pending_requip_ticks > 0:
        _pending_requip_ticks -= 1
        return
    try:
        pc = get_pc()
        pawn = getattr(pc, "Pawn", None)
        manager = getattr(pawn, "InvManager", None) or getattr(pawn, "InventoryManager", None)
        if manager is None:
            raise RuntimeError("local inventory manager was unavailable")

        if _pending_requip_stage == 0:
            # Exact first step recorded from Enhanced's inventory UI. This
            # completes the normal put-down rather than drawing another slot.
            manager.SetCurrentWeapon(None)
            _pending_requip_stage = 1
            _pending_requip_ticks = 60
            return

        if _pending_requip_stage == 1:
            # Enhanced clones a readied weapon into a new backpack object
            # inside this call. The AddInventoryToBackpack POST hook captures
            # that replacement; the original object is retired afterward.
            _pending_requip_backpack = None
            manager.InventoryUnreadied(weapon)
            if _pending_requip_backpack is None:
                raise RuntimeError("Enhanced did not expose the backpack replacement weapon")
            _pending_requip_stage = 2
            _pending_requip_ticks = 30
            return

        if _pending_requip_stage == 2:
            # This call creates the final live/readied replacement object. Its
            # nested InventoryReadied event is captured by the POST hook.
            _pending_requip_readied = None
            manager.ReadyBackpackInventory(_pending_requip_backpack, _pending_requip_slot)
            if _pending_requip_readied is None:
                raise RuntimeError("Enhanced did not expose the readied replacement weapon")
            _pending_requip_stage = 3
            _pending_requip_ticks = 30
            return

        if _pending_requip_stage == 3:
            manager.SetCurrentWeapon(_pending_requip_readied)
            _pending_requip_stage = 4
            _pending_requip_ticks = 60
            return

        active = getattr(pawn, "Weapon", None)
        if not _same_object(active, _pending_requip_readied):
            raise RuntimeError("the replacement weapon did not become current")
        logging.info(f"Pandora's Workshop re-equipped replacement {core._weapon_name(active)} after Apply")
        _pending_requip = None
        _pending_requip_backpack = None
        _pending_requip_readied = None
        _pending_requip_stage = 0
        _pending_requip_slot = 0
    except Exception as exc:
        # If conversion reached the backpack/readied stages, finish through
        # those same safe native objects instead of resurrecting the retired
        # original weapon or inserting it a second time.
        try:
            if manager is not None and _pending_requip_readied is not None:
                manager.SetCurrentWeapon(_pending_requip_readied)
            elif manager is not None and _pending_requip_backpack is not None:
                manager.ReadyBackpackInventory(_pending_requip_backpack, _pending_requip_slot)
        except Exception as recovery_exc:
            logging.warning(f"Pandora's Workshop weapon recovery also differed: {recovery_exc}")
        _pending_requip = None
        _pending_requip_backpack = None
        _pending_requip_readied = None
        _pending_requip_stage = 0
        _pending_requip_slot = 0
        logging.warning(f"Pandora's Workshop could not re-equip the edited weapon: {exc}")
        core._notify("Changes applied; re-equip the weapon manually to refresh derived stats.")


@hook("WillowGame.WillowInventoryManager:InventoryReadied", hook_type=Type.POST_UNCONDITIONAL)
def _capture_inventory_readied(_obj: UObject, args: WrappedStruct, _ret: Any, _func: BoundFunction) -> None:
    global _pending_requip_readied
    if _pending_requip is not None:
        _pending_requip_readied = args.Inv


@hook("WillowGame.WillowInventoryManager:AddInventoryToBackpack", hook_type=Type.POST_UNCONDITIONAL)
def _capture_add_to_backpack(_obj: UObject, args: WrappedStruct, _ret: Any, _func: BoundFunction) -> None:
    global _pending_requip_backpack, _pending_duplicate_result
    if _pending_requip is not None:
        _pending_requip_backpack = args.Inv
    if _pending_duplicate_source is not None:
        _pending_duplicate_result = args.Inv


@keybind(
    "Open Pandora's Workshop",
    "F7",
    event_filter=EInputEvent.IE_Pressed,
    description="Open Pandora's Workshop.",
)
def open_workshop() -> type[Block] | None:
    global _pending_open
    if _pending_open:
        # Ignore key-repeat/spam while the pause movie is being constructed.
        return Block
    if _active_pause_menu is not None:
        return Block
    # Every F7 press starts from the weapon currently in first person. A
    # session left behind by closing with Escape must never pin the weapon that
    # happened to be active when the save originally loaded.
    weapon = core._current_weapon()
    if weapon is None:
        core._notify("Equip a weapon before opening Pandora's Workshop.")
        return None
    core._session = core.Session(weapon=weapon, original=core._snapshot(weapon))
    try:
        core._remember_weapon_parts(weapon)
    except Exception as exc:
        # A single stale SDK wrapper must never strand the global session and
        # permanently disable F7 for the remainder of the game process.
        logging.warning(f"Pandora's Workshop skipped a live-part catalog error: {exc}")

    pc = get_pc()
    try:
        playing = pc.GFxUIManager.GetPlayingMovie()
        if playing is not None and playing.Class.Name == "WillowGFxMenuPause":
            _pending_open = True
            _open_on_pause(playing)
            return Block
    except Exception:
        pass

    _pending_open = True
    try:
        # Play the complete menu definition. PauseGFxMovie with only the movie
        # asset prepared it but left activation to the normal Escape action.
        pc.ConsoleCommand("PlayGfxMovieDefinition ui_pause.Definitions.pause_menu_DEF")
    except Exception as exc:
        _pending_open = False
        logging.error(f"Pandora's Workshop could not open pause movie: {exc}")
        core._notify("Could not open the native menu; see SDK log.")
        return None
    return Block


build_mod(keybinds=[open_workshop], options=[card_size_option])
logging.info(f"Pandora's Workshop {WORKSHOP_VERSION} loaded; press F7")
