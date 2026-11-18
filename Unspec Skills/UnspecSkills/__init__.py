# Unspec Skills (Borderlands GOTY / GOTY Enhanced)
# Port of ZetaDaemon's Borderlands 2 mod "Unspec Skills"
# (https://github.com/ZetaDaemon/bl-sdk-mods/tree/main/UnspecSkills).
#
# How it works
# ------------
# Highlight a skill in the skill tree and press the unspec button to take one point back out of it.
# The point is taken straight out of the skill and given back as an unspent point, then the game
# is told about the change with the same calls it makes after you buy a point, so the skill's
# effect, the tree's tier unlocks and your save all follow along. A point that a higher skill in
# the same tree needs to stay unlocked can't be taken out.
#
# (Doing it through the New-U station respec and buying the points back crashes the game whenever
# an Adrenaline skill such as Lilith's Girl Power is bought back straight after the respec.)
from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from mods_base import EInputEvent, SpinnerOption, build_mod, get_pc, hook
from unrealsdk import logging
from unrealsdk.hooks import Block, Type
from unrealsdk.unreal import BoundFunction, UObject, WeakPointer, WrappedStruct

__version__: str
__version_info__: tuple[int, ...]

MOD_NAME = "Unspec Skills"


# ---------------------------------------------------------------------------------------------------
# Public API for other mods (same as the BL2 original)
# ---------------------------------------------------------------------------------------------------
# A condition gets the WillowPlayerController and the SkillDefinition about to lose a point, and
# returns False to block it.
UnspecCondition = Callable[[UObject, UObject], bool]
unspec_conditions: list[UnspecCondition] = []


def add_unspec_condition(condition: UnspecCondition) -> None:
    unspec_conditions.append(condition)


def remove_unspec_condition(condition: UnspecCondition) -> None:
    unspec_conditions.remove(condition)


# ---------------------------------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------------------------------
# ESkillBranch: First (action skill), Left, Middle, Right. None (4) is weapon proficiencies etc.
TREE_BRANCHES = (1, 2, 3)

ROLE_AUTHORITY = 3

# Each tier of a tree opens once this many points are spent in the tiers below it.
POINTS_PER_TIER = 5

KEYBOARD_KEYS = {
    "Right Mouse Button": "RightMouseButton",
    "Middle Mouse Button": "MiddleMouseButton",
    "Backspace": "BackSpace",
    "Delete": "Delete",
    "R": "R",
}
CONTROLLER_KEYS = {
    "None": None,
    "X": "XboxTypeS_X",
    "Y": "XboxTypeS_Y",
    "Left Bumper": "XboxTypeS_LeftShoulder",
    "Right Bumper": "XboxTypeS_RightShoulder",
    "Left Trigger": "XboxTypeS_LeftTrigger",
    "Right Trigger": "XboxTypeS_RightTrigger",
    "Back": "XboxTypeS_Back",
}


def _int(value: Any) -> int:
    """Enum members, bytes and ints all to a plain int."""
    return int(getattr(value, "value", value))


def _try(func: Callable[[], Any], default: Any = None) -> Any:
    try:
        return func()
    except Exception:  # noqa: BLE001
        return default


def _info(msg: str) -> None:
    logging.info(f"[{MOD_NAME}] {msg}")


# ---------------------------------------------------------------------------------------------------
# Skill tree rules
# ---------------------------------------------------------------------------------------------------
def _tier_blocker(pc: UObject, index: int) -> str | None:
    """With one point out of `index`, name a higher skill that would lose its tier unlock."""
    skills = pc.PlayerSkills
    branch = _int(skills[index].SkillTreeBranch)
    grades = {
        i: int(e.Grade)
        for i, e in enumerate(skills)
        if e.Definition is not None and _int(e.SkillTreeBranch) == branch
    }
    grades[index] -= 1
    for i, grade in grades.items():
        tier = int(skills[i].SkillTreeTierIndex)
        if grade <= 0 or tier <= 0:
            continue
        below = sum(g for j, g in grades.items() if 0 <= int(skills[j].SkillTreeTierIndex) < tier)
        if below < POINTS_PER_TIER * tier:
            return str(skills[i].Definition.Name)
    return None


# ---------------------------------------------------------------------------------------------------
# Skill menu updates
# ---------------------------------------------------------------------------------------------------
# While a point is being taken out, the skill menu's own update calls are held back, and it's
# refreshed once at the end without the "point spent" flash and sound.
_quiet: bool = False
_no_feedback: bool = False


@contextmanager
def _quiet_ui() -> Iterator[None]:
    global _quiet
    _quiet = True
    try:
        yield
    finally:
        _quiet = False


def _block_while_quiet(*_: Any) -> Any:
    return Block if _quiet else None


quiet_ui_hooks = _block_while_quiet
for _name in (
    "WillowGame.SkillTreeGFxHelper:HandleSkillGradeChange",
    "WillowGame.SkillTreeGFxHelper:HandleSkillPointsChange",
):
    quiet_ui_hooks = hook(_name, Type.PRE)(quiet_ui_hooks)
del _name


@hook("WillowGame.SkillTreeGFxHelper:Flash_SkillPointSpentFeedback", Type.PRE)
def no_spent_feedback(*_: Any) -> Any:
    return Block if _quiet or _no_feedback else None


def _refresh_ui(pc: UObject, movie: UObject, index: int) -> None:
    global _no_feedback
    helper = movie.SkillHelper
    if helper is None:
        return
    # The same refresh the game does after spending a point, minus the "point spent" flash.
    points = int(pc.PlayerReplicationInfo.GeneralSkillPoints)
    grade = int(pc.PlayerSkills[index].Grade)
    _no_feedback = True
    try:
        _try(lambda: helper.HandleSkillGradeChange(points, index, grade))
    finally:
        _no_feedback = False
    nav = _try(lambda: helper.CurrentNavDef)
    if nav is not None:
        _try(lambda: helper.HandleSelection(nav))
    # Keep -Ry's "Skilltree UI Fix" colours in sync if it's running
    try:
        from skill_tree_tweaks import MOD_INSTANCE as STT  # type: ignore
        from skill_tree_tweaks.hooks import apply_skill_tree_changes  # type: ignore

        if STT.is_enabled:
            apply_skill_tree_changes(movie)
    except Exception:  # noqa: BLE001
        pass


def _play_failure(movie: UObject | None) -> None:
    if movie is not None:
        _try(lambda: movie.PlaySpecialUISound("ResultFailure"))


# ---------------------------------------------------------------------------------------------------
# Unspeccing
# ---------------------------------------------------------------------------------------------------
def _lower_tier_counters(pc: UObject, branch: int, tier: int) -> None:
    """Keep the tree's own points-spent counters in step with the skill's grade."""
    data = pc.SkillTreeBranches[branch]
    spent = int(data.PointsSpentInBranch)
    if spent > 0:
        data.PointsSpentInBranch = spent - 1
    tiers = data.Tiers
    if 0 <= tier < len(tiers):
        entry = tiers[tier]
        in_tier = int(entry.PointsSpentInTier)
        if in_tier > 0:
            entry.PointsSpentInTier = in_tier - 1


def unspec(pc: UObject, index: int) -> None:
    skills = pc.PlayerSkills
    entry = skills[index]
    grade = int(entry.Grade)
    pri = pc.PlayerReplicationInfo

    entry.Grade = grade - 1
    if int(skills[index].Grade) != grade - 1:
        raise RuntimeError("couldn't change the skill's grade")
    pri.GeneralSkillPoints = int(pri.GeneralSkillPoints) + 1
    _lower_tier_counters(pc, _int(entry.SkillTreeBranch), int(entry.SkillTreeTierIndex))

    # The same follow-up the game does itself after ServerUpgradeSkill buys a point: re-check
    # the tree's unlocks, update the skill's effect, and send the new grade to the client side.
    pc.UpdateSkillTreeForSkillChange(index)
    pc.CheckSkillReadiness("ServerUpgradeSkill")
    pc.ClientCheckSkillReadiness()
    pc.ClientSetSkillGrade(
        int(pri.GeneralSkillPoints), index, int(skills[index].Grade), int(skills[index].GradePoints)
    )


def _check_unspec(movie: UObject) -> tuple[UObject, int] | None:
    """Everything that can refuse an unspec, before anything is changed."""
    pc = get_pc()
    helper = movie.SkillHelper
    if pc is None or helper is None:
        return None
    # Only act on the skill menu that's actually open (not one left over from a closed menu)
    if helper.WPCOwner != pc or helper.Movie is None:
        return None

    def fail(reason: str) -> None:
        _info(f"can't unspec: {reason}")
        _play_failure(movie)

    nav = helper.CurrentNavDef
    index = int(helper.GetSkillIndexForNavDef(nav)) if nav is not None else -1
    skills = pc.PlayerSkills
    if index < 0 or index >= len(skills):
        return fail("no skill selected")

    entry = skills[index]
    skill = entry.Definition
    if _int(entry.SkillTreeBranch) not in TREE_BRANCHES:
        return fail("only skills in the three trees can be unspecced")
    if int(entry.Grade) <= 0:
        return fail(f"{skill.Name} has no points in it")
    if _try(lambda: _int(pc.Role), ROLE_AUTHORITY) != ROLE_AUTHORITY:
        return fail("only the host can unspec in co-op")
    for condition in unspec_conditions:
        if not condition(pc, skill):
            return fail("blocked by another mod")
    if (blocker := _tier_blocker(pc, index)) is not None:
        return fail(f"{blocker} needs that point to stay unlocked - take points out of {blocker} first")
    return pc, index


def try_unspec(movie: UObject) -> None:
    checked = _check_unspec(movie)
    if checked is None:
        return
    pc, index = checked
    with _quiet_ui():
        unspec(pc, index)
    _refresh_ui(pc, movie, index)


# ---------------------------------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------------------------------
# The game buys a point when the button comes up, inside SkillTreeGFxHelper.HandleInputKey, so the
# unspec happens at the same moment and place. The status menu's own input functions swallow the
# press (and held repeats) of the unspec button, so the game's own use of that button never runs.
_status_movie: WeakPointer = WeakPointer()
_status_screen: str = ""


@hook("WillowGame.StatusMenuExGFxMovie:extSetCurrentScreen", Type.POST_UNCONDITIONAL)
def on_set_screen(obj: UObject, args: WrappedStruct, _ret: Any, _func: BoundFunction) -> None:
    global _status_movie, _status_screen
    _status_movie = WeakPointer(obj)
    _status_screen = str(args.ScreenName).lower()


def _skills_movie() -> UObject | None:
    if _status_screen != "skills":
        return None
    pc = get_pc()
    if pc is None or not pc.bStatusMenuOpen:
        return None
    return _status_movie()


def _is_unspec_key(key: Any) -> bool:
    return str(key) in (KEYBOARD_KEYS[keyboard_key.value], CONTROLLER_KEYS[controller_key.value])


def _menu_input(_obj: UObject, args: WrappedStruct, _ret: Any, _func: BoundFunction) -> Any:
    if _status_screen != "skills" or not _is_unspec_key(args.ukey):
        return None
    if args.uevent == EInputEvent.IE_Released:
        return None  # let it through to SkillTreeGFxHelper.HandleInputKey
    return Block, True


menu_input_hooks = _menu_input
for _name in (
    "WillowGame.StatusMenuExGFxMovie:HandleSkillsInputKey",
    "WillowGame.StatusMenuExGFxMovie:HandleInputKey",
):
    menu_input_hooks = hook(_name, Type.PRE)(menu_input_hooks)
del _name


@hook("WillowGame.SkillTreeGFxHelper:HandleInputKey", Type.PRE)
def on_helper_input(obj: UObject, args: WrappedStruct, _ret: Any, _func: BoundFunction) -> Any:
    if _status_screen != "skills" or not _is_unspec_key(args.ukey):
        return None
    if args.uevent == EInputEvent.IE_Released:
        movie = _skills_movie()
        if movie is not None and movie.SkillHelper == obj:
            try:
                try_unspec(movie)
            except Exception as ex:  # noqa: BLE001
                logging.error(f"[{MOD_NAME}] unspec failed: {ex!r}")
    return Block, True


# ---------------------------------------------------------------------------------------------------
# Options
# ---------------------------------------------------------------------------------------------------
keyboard_key = SpinnerOption(
    "Unspec Button (Keyboard/Mouse)",
    "Right Mouse Button",
    list(KEYBOARD_KEYS),
    description="Press this while a skill is highlighted in the skill tree to take a point out of it.",
)

controller_key = SpinnerOption(
    "Unspec Button (Controller)",
    "X",
    list(CONTROLLER_KEYS),
    description="Press this while a skill is highlighted in the skill tree to take a point out of it.",
)


build_mod(
    options=[keyboard_key, controller_key],
    hooks=[on_set_screen, menu_input_hooks, on_helper_input, quiet_ui_hooks, no_spent_feedback],
)
