import ctypes
import os
from pathlib import Path

from mods_base import (
    BoolOption,
    ButtonOption,
    Game,
    HiddenOption,
    NestedOption,
    SliderOption,
    build_mod,
)
from unrealsdk import logging

from .backup import BackupError, BackupResult, list_backups, make_backup

try:
    from ui_utils import TrainingBox, clipboard_paste
except ImportError:
    TrainingBox = None  # type: ignore
    clipboard_paste = None  # type: ignore

__version__: str
__version_info__: tuple[int, ...]

MOD_NAME = "Saves Backuper"


# ---------------------------------------------------------------------------------------------------
# Default folders
# ---------------------------------------------------------------------------------------------------


def get_documents_dir() -> Path:
    """
    Gets the user's real Documents folder from Windows, so a Documents folder that's been moved
    (e.g. redirected into OneDrive or to another drive) is still found.
    """
    try:
        CSIDL_PERSONAL = 5  # noqa: N806
        SHGFP_TYPE_CURRENT = 0  # noqa: N806
        buf = ctypes.create_unicode_buffer(260)
        result = ctypes.windll.shell32.SHGetFolderPathW(  # type: ignore
            None,
            CSIDL_PERSONAL,
            None,
            SHGFP_TYPE_CURRENT,
            buf,
        )
        if result == 0 and buf.value:
            return Path(buf.value)
    except Exception:  # noqa: BLE001
        pass
    return Path(os.path.expanduser("~")) / "Documents"


def get_game_user_dir() -> Path:
    my_games = get_documents_dir() / "My Games"
    if Game.get_current() == Game.BL1E:
        return my_games / "Borderlands Game of the Year"
    return my_games / "Borderlands"


def default_save_dir() -> Path:
    if Game.get_current() == Game.BL1E:
        # Documents\My Games\Borderlands Game of the Year\Binaries\SaveData
        return get_game_user_dir() / "Binaries" / "SaveData"
    # Documents\My Games\Borderlands\SaveData
    return get_game_user_dir() / "SaveData"


def default_backup_dir() -> Path:
    # Next to the game's own folders, not inside SaveData, so the game never sees the zips
    return get_game_user_dir() / "SaveData Backups"


# ---------------------------------------------------------------------------------------------------
# Options
# ---------------------------------------------------------------------------------------------------

custom_save_dir: HiddenOption[str] = HiddenOption("custom_save_dir", "")
custom_backup_dir: HiddenOption[str] = HiddenOption("custom_backup_dir", "")


def get_save_dir() -> Path:
    return Path(custom_save_dir.value) if custom_save_dir.value else default_save_dir()


def get_backup_dir() -> Path:
    return Path(custom_backup_dir.value) if custom_backup_dir.value else default_backup_dir()


def show_message(title: str, message: str) -> None:
    """Shows a dialog if possible, and always writes to the console/log."""
    logging.info(f"[{MOD_NAME}] {title}: {message}")
    if TrainingBox is None:
        return
    try:
        TrainingBox(title=f"{MOD_NAME}: {title}", message=message).show()
    except Exception:  # noqa: BLE001
        pass


def describe_result(result: BackupResult) -> str:
    if result.skipped_unchanged:
        assert result.latest_existing is not None
        return (
            "Your saves haven't changed since the last backup, so no new one was made.\n\n"
            f"Latest backup: {result.latest_existing.name}"
        )

    assert result.path is not None
    s = "" if result.file_count == 1 else "s"
    msg = f"Backed up {result.file_count} file{s} to:\n{result.path}"
    if result.deleted:
        n = len(result.deleted)
        msg += (
            f"\n\nMoved {n} old backup{'' if n == 1 else 's'} to the Recycle Bin"
            f" (keeping {int(keep_count.value)})."
        )
    if result.delete_errors:
        msg += "\n\nCouldn't remove some old backups (they were left in place):\n"
        msg += "\n".join(result.delete_errors)
    return msg


def run_backup(show_dialog: bool) -> None:
    save_dir = get_save_dir()
    backup_dir = get_backup_dir()
    try:
        result = make_backup(
            save_dir,
            backup_dir,
            skip_unchanged=skip_unchanged.value,
            keep=int(keep_count.value) if delete_old.value else None,
        )
    except BackupError as ex:
        if show_dialog:
            show_message("Backup Failed", str(ex))
        else:
            logging.warning(f"[{MOD_NAME}] Backup failed: {ex}")
        return
    except Exception as ex:  # noqa: BLE001
        if show_dialog:
            show_message("Backup Failed", f"{type(ex).__name__}: {ex}")
        else:
            logging.error(f"[{MOD_NAME}] Backup failed: {type(ex).__name__}: {ex}")
        logging.dev_warning(repr(ex))
        return

    message = describe_result(result)
    if show_dialog:
        show_message("Backup Complete", message)
    else:
        logging.info(f"[{MOD_NAME}] {message}")


def on_backup_now(_: ButtonOption) -> None:
    run_backup(show_dialog=True)


def on_open_backup_folder(_: ButtonOption) -> None:
    backup_dir = get_backup_dir()
    if not backup_dir.is_dir():
        show_message(
            "Folder Not Found",
            f"The backup folder doesn't exist yet. It's created on the first backup.\n\n{backup_dir}",
        )
        return
    try:
        os.startfile(backup_dir)  # type: ignore  # noqa: S606
    except OSError as ex:
        show_message("Couldn't Open Folder", f"{ex}\n\n{backup_dir}")


def on_show_folders(_: ButtonOption) -> None:
    save_dir = get_save_dir()
    backup_dir = get_backup_dir()
    count = len(list_backups(backup_dir))
    show_message(
        "Folders",
        f"Save folder ({'custom' if custom_save_dir.value else 'default'}"
        f"{'' if save_dir.is_dir() else ', NOT FOUND'}):\n{save_dir}\n\n"
        f"Backup folder ({'custom' if custom_backup_dir.value else 'default'}):\n{backup_dir}\n\n"
        f"Backups in folder: {count}",
    )


def read_clipboard_path() -> Path | None:
    if clipboard_paste is None:
        show_message("Clipboard Unavailable", "Couldn't access the clipboard.")
        return None
    text = (clipboard_paste() or "").strip().strip('"').strip()
    if not text:
        show_message(
            "Clipboard Empty",
            "Copy a folder path first (in File Explorer: right-click the folder, Copy as path), "
            "then press this again.",
        )
        return None
    path = Path(os.path.expandvars(text))
    if not path.is_absolute():
        show_message("Invalid Path", f"Not a full folder path:\n{text}")
        return None
    return path


def on_set_save_dir(_: ButtonOption) -> None:
    path = read_clipboard_path()
    if path is None:
        return
    if not path.is_dir():
        show_message("Folder Not Found", f"Save folder wasn't changed. Couldn't find:\n{path}")
        return
    custom_save_dir.value = str(path)
    custom_save_dir.save()
    show_message("Save Folder Set", str(path))


def on_set_backup_dir(_: ButtonOption) -> None:
    path = read_clipboard_path()
    if path is None:
        return
    if not path.parent.is_dir():
        show_message(
            "Folder Not Found",
            f"Backup folder wasn't changed. Its parent folder doesn't exist:\n{path.parent}",
        )
        return
    if os.path.normcase(os.path.abspath(path)) == os.path.normcase(
        os.path.abspath(get_save_dir()),
    ):
        show_message("Invalid Folder", "The backup folder can't be the same as the save folder.")
        return
    custom_backup_dir.value = str(path)
    custom_backup_dir.save()
    show_message("Backup Folder Set", f"{path}\n\nCreated on the next backup if it doesn't exist.")


def on_reset_save_dir(_: ButtonOption) -> None:
    custom_save_dir.value = ""
    custom_save_dir.save()
    show_message("Save Folder Reset", str(get_save_dir()))


def on_reset_backup_dir(_: ButtonOption) -> None:
    custom_backup_dir.value = ""
    custom_backup_dir.save()
    show_message("Backup Folder Reset", str(get_backup_dir()))


backup_now = ButtonOption(
    "Back Up Now",
    description="Make a backup of your saves right now.",
    on_press=on_backup_now,
)

open_backup_folder = ButtonOption(
    "Open Backup Folder",
    description="Open the backup folder in File Explorer.",
    on_press=on_open_backup_folder,
)

backup_on_launch = BoolOption(
    "Back Up On Game Launch",
    True,
    "Yes",
    "No",
    description=(
        "Back up your saves each time the game starts, before any character is loaded or saved."
    ),
)

skip_unchanged = BoolOption(
    "Skip If Unchanged",
    True,
    "Yes",
    "No",
    description=(
        "Don't make a new backup if your saves are identical to the latest backup. Stops repeated"
        " launches from filling the backup limit with copies of the same saves."
    ),
)

delete_old = BoolOption(
    "Delete Old Backups",
    False,
    "Yes",
    "No",
    description=(
        "Off by default: every backup is kept. When on, each new backup moves the oldest backups to"
        " the Recycle Bin until only 'Backups To Keep' remain, at most 2 per new backup so the"
        " history is never wiped in one go. Backups you rename are never touched."
    ),
)

keep_count = SliderOption(
    "Backups To Keep",
    10,
    1,
    100,
    description=(
        "How many backups to keep. Only used when 'Delete Old Backups' is on, and old backups are"
        " only removed after the next successful backup."
    ),
)

folders = NestedOption(
    "Folders",
    children=[
        ButtonOption(
            "Show Current Folders",
            description="Show which save folder and backup folder are being used.",
            on_press=on_show_folders,
        ),
        ButtonOption(
            "Set Save Folder From Clipboard",
            description=(
                "Copy the folder that holds your .sav files (File Explorer: right-click, Copy as"
                " path), then press this. Only needed if your saves aren't in the usual place."
            ),
            on_press=on_set_save_dir,
        ),
        ButtonOption(
            "Reset Save Folder",
            description="Go back to the default save folder.",
            on_press=on_reset_save_dir,
        ),
        ButtonOption(
            "Set Backup Folder From Clipboard",
            description=(
                "Copy a folder path (File Explorer: right-click, Copy as path), then press this to"
                " store backups there instead."
            ),
            on_press=on_set_backup_dir,
        ),
        ButtonOption(
            "Reset Backup Folder",
            description="Go back to the default backup folder.",
            on_press=on_reset_backup_dir,
        ),
    ],
    description="Choose where saves are read from and where backups go.",
)


def on_enable() -> None:
    # When the mod was left enabled, this runs while the game is starting up
    if backup_on_launch.value:
        run_backup(show_dialog=False)


build_mod(
    options=[
        backup_now,
        open_backup_folder,
        backup_on_launch,
        skip_unchanged,
        delete_old,
        keep_count,
        folders,
        custom_save_dir,
        custom_backup_dir,
    ],
    on_enable=on_enable,
)
