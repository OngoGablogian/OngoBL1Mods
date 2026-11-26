"""
XP Multiplier - Borderlands GOTY / GOTY Enhanced (willow1-mod-manager)

Multiplies character experience and weapon proficiency experience independently.

How it works
------------
BL1 awards kill XP through native code that can't be hooked directly, so instead:

  * PRE  WillowGameInfo:AwardCombatExperience  -> snapshot XP + proficiency points
  * POST WillowGameInfo:AwardCombatExperience  -> measure what was actually gained
        - extra character XP  = gained XP   * (char mult - 1), added to the XP pool
        - extra proficiency   = gained prof * (prof mult - 1), added via
                                ConvertExperienceGainToWeaponProficiency
  * MissionDefinition:GetExperienceReward      -> scaled return value (mission XP)
"""

from __future__ import annotations

from typing import Any

from unrealsdk import logging
from unrealsdk.hooks import Block, Type, prevent_hooking_direct_calls
from unrealsdk.unreal import BoundFunction, UObject, WrappedStruct

from mods_base import BoolOption, SliderOption, build_mod, get_pc, hook

AWARD_FUNC = "WillowGame.WillowGameInfo:AwardCombatExperience"
MISSION_FUNC = "WillowGame.MissionDefinition:GetExperienceReward"

# --------------------------------------------------------------------------------------------------
# Options
# --------------------------------------------------------------------------------------------------

char_xp_slider = SliderOption(
    "Character XP Multiplier",
    1,
    1,
    50,
    1,
    True,
    description="Multiplies the experience your character earns. 1 = vanilla.",
)

prof_xp_slider = SliderOption(
    "Proficiency XP Multiplier",
    1,
    1,
    50,
    1,
    True,
    description="Multiplies weapon proficiency experience. 1 = vanilla.",
)

mission_xp_toggle = BoolOption(
    "Apply To Mission XP",
    True,
    description="Also multiply mission reward XP by the Character XP Multiplier.",
)

# --------------------------------------------------------------------------------------------------
# XP / proficiency helpers
# --------------------------------------------------------------------------------------------------


def get_xp(pc: UObject) -> int:
    return int(pc.GetExpPoints())


def prof_total(skill: WrappedStruct) -> int:
    """Cumulative proficiency points (reaching grade g costs 1200 * (g^2 + g))."""
    g = int(skill.Grade)
    return 1200 * (g * g + g) + int(skill.GradePoints)


def prof_totals(pc: UObject) -> dict[int, int]:
    return {int(s.PlayerSkillIndex): prof_total(s) for s in pc.ProficiencySkills}


def prof_delta(before: dict[int, int], after: dict[int, int]) -> int:
    return sum(after.get(k, 0) - v for k, v in before.items())


def add_xp_pool(pc: UObject, amount: int) -> None:
    pool = pc.ExpPool.Data
    try:
        current = float(pool.GetCurrentValue())
    except AttributeError:
        current = float(pool.CurrentValue)
    try:
        pool.SetCurrentValue(current + amount)
    except AttributeError:
        pool.CurrentValue = current + amount
    pool.ApplyExpPointsToExpLevel()
    # Don't call pc.UpdateHUDCachedXPValue here: the HUD's XP popup is the difference
    # between the real XP and that cached value, so updating it hides the popup.


def add_bonus_xp(pc: UObject, amount: int) -> None:
    if amount <= 0:
        return
    before = get_xp(pc)
    try:
        add_xp_pool(pc, amount)
    except Exception:  # noqa: BLE001, S110
        pass
    if get_xp(pc) - before <= 0:
        # Fallback: the game's own award function (doesn't add proficiency).
        pc.ExpEarn(amount, 0)


# --------------------------------------------------------------------------------------------------
# Hooks
# --------------------------------------------------------------------------------------------------

_snapshots: list[tuple[int, dict[int, int]] | None] = []


@hook(AWARD_FUNC, Type.PRE)
def award_pre(_obj: UObject, _args: WrappedStruct, _ret: Any, _func: BoundFunction) -> None:
    pc = get_pc()
    _snapshots.append((get_xp(pc), prof_totals(pc)) if pc is not None else None)


@hook(AWARD_FUNC, Type.POST)
def award_post(_obj: UObject, _args: WrappedStruct, _ret: Any, _func: BoundFunction) -> None:
    snap = _snapshots.pop() if _snapshots else None
    pc = get_pc()
    if snap is None or pc is None:
        return
    xp_before, prof_before = snap

    prof_after_award = prof_totals(pc)
    xp_gain = get_xp(pc) - xp_before
    prof_gain = prof_delta(prof_before, prof_after_award)

    char_mult = int(char_xp_slider.value)
    prof_mult = int(prof_xp_slider.value)

    if xp_gain > 0 and char_mult > 1:
        add_bonus_xp(pc, xp_gain * (char_mult - 1))

    if prof_gain > 0 and prof_mult > 1:
        # Subtract anything the XP bonus may have added as a side effect.
        side_effect = prof_delta(prof_after_award, prof_totals(pc))
        prof_bonus = prof_gain * (prof_mult - 1) - side_effect
        if prof_bonus > 0:
            pc.ConvertExperienceGainToWeaponProficiency(prof_bonus)


@hook(MISSION_FUNC, Type.PRE)
def mission_reward(_obj: UObject, args: WrappedStruct, _ret: Any, func: BoundFunction) -> Any:
    mult = int(char_xp_slider.value)
    if not mission_xp_toggle.value or mult == 1:
        return None
    with prevent_hooking_direct_calls():
        base = int(func(args.InWPC))
    return Block, base * mult


def on_enable() -> None:
    _snapshots.clear()


def on_disable() -> None:
    _snapshots.clear()


mod = build_mod(
    options=[char_xp_slider, prof_xp_slider, mission_xp_toggle],
    hooks=[award_pre, award_post, mission_reward],
    on_enable=on_enable,
    on_disable=on_disable,
)

logging.info(f"{mod.name} {mod.version} loaded")
