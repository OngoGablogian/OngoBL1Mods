from typing import Any

from mods_base import BoolOption, EInputEvent, Game, build_mod, get_pc, hook, keybind
from unrealsdk.hooks import Block, Type
from unrealsdk.unreal import BoundFunction, UObject, WrappedStruct

__version__: str
__version_info__: tuple[int, ...]


@keybind(
    identifier="Quit Without Saving",
    key=None,
    event_filter=EInputEvent.IE_Pressed,
    description="Disconnect to the main menu without saving your progress.",
)
def doQuitWithoutSaving() -> None:
    pc = get_pc()
    if pc is None:
        return
    pc.ConsoleCommand("disconnect")


# The "Quit to Desktop" pause-menu entry only exists in GOTY Enhanced.
if Game.get_current() == Game.BL1E:
    DisableQuitToDesktop: BoolOption = BoolOption(
        "Disable Quit To Desktop",
        True,
        "Yes",
        "No",
        description="Removes the Quit to Desktop option from the pause menu.",
    )

    @hook("WillowGame.WillowGFxLobbyTools:menuAddItem", Type.PRE)
    def menuAddItemHook(
        obj: UObject,
        args: WrappedStruct,
        ret: Any,
        func: BoundFunction,
    ) -> type[Block] | None:
        if DisableQuitToDesktop.value and args.menuCaption == "$WillowMenu.Pause.QuitPC":
            return Block
        return None

    build_mod(options=[DisableQuitToDesktop])
else:
    build_mod(options=[])
