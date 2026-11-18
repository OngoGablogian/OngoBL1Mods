"""
Backup logic for Saves Backuper.

This module has no game / SDK dependencies so it can be tested outside of Borderlands.

Safety rules followed here:
- Save files are only ever opened read-only. Nothing in the save folder is written, moved or deleted.
- A backup is written to a temporary ".partial" file, verified, and only then renamed into place,
  so a crash or full disk can never leave a half-written zip that looks like a real backup.
- Old backups are only removed after a new backup has been written and verified, only files whose
  names exactly match this mod's naming scheme are ever removed, at most a couple are removed per
  new backup, and they go to the Recycle Bin rather than being permanently deleted. Rename a backup
  (e.g. add "keep_" to the front) and it will never be touched.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

__all__: tuple[str, ...] = (
    "BACKUP_PREFIX",
    "BackupError",
    "BackupResult",
    "list_backups",
    "make_backup",
)

BACKUP_PREFIX = "SaveData_"
TIMESTAMP_FORMAT = "%Y-%m-%d_%H-%M-%S"
PARTIAL_SUFFIX = ".partial"

# SaveData_2026-11-17_21-30-05.zip, or SaveData_2026-11-17_21-30-05_2.zip on a name collision
BACKUP_NAME_RE = re.compile(
    r"^" + re.escape(BACKUP_PREFIX) + r"(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})(?:_(\d+))?\.zip$",
)
FINGERPRINT_PREFIX = "SavesBackuper fingerprint: "

# Zip timestamps can't go below 1980
_MIN_ZIP_TIME = time.mktime((1980, 1, 1, 0, 0, 0, 0, 0, -1)) + 86400


class BackupError(Exception):
    """A problem that stops a backup from being made. The message is shown to the user."""


@dataclass
class BackupResult:
    path: Path | None
    """The new backup, or None if it was skipped."""
    file_count: int = 0
    skipped_unchanged: bool = False
    latest_existing: Path | None = None
    """When skipped, the existing backup that already holds these saves."""
    deleted: list[Path] = field(default_factory=list[Path])
    delete_errors: list[str] = field(default_factory=list[str])


@dataclass
class _SaveFile:
    rel_path: str
    data: bytes
    mtime: float


def _is_within(child: Path, parent: Path) -> bool:
    """True if child is parent, or is somewhere inside it."""
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def _normalise(path: Path) -> Path:
    return Path(os.path.normcase(os.path.abspath(path)))


def _read_save_files(save_dir: Path, backup_dir: Path) -> list[_SaveFile]:
    """Reads every file in the save folder (read-only), skipping the backup folder if nested."""
    backup_norm = _normalise(backup_dir)
    files: list[_SaveFile] = []

    for root, dirs, filenames in os.walk(save_dir):
        root_path = Path(root)
        # Don't descend into the backup folder if it's been put inside the save folder
        dirs[:] = sorted(d for d in dirs if not _is_within(_normalise(root_path / d), backup_norm))

        for name in sorted(filenames):
            full = root_path / name
            if full.is_symlink() or not full.is_file():
                continue
            with full.open("rb") as f:
                data = f.read()
            files.append(
                _SaveFile(
                    rel_path=full.relative_to(save_dir).as_posix(),
                    data=data,
                    mtime=full.stat().st_mtime,
                ),
            )

    return files


def _fingerprint(files: list[_SaveFile]) -> str:
    h = hashlib.sha256()
    for f in files:
        h.update(f.rel_path.encode("utf-8"))
        h.update(b"\0")
        h.update(len(f.data).to_bytes(8, "little"))
        h.update(hashlib.sha256(f.data).digest())
    return h.hexdigest()


def _sort_key(path: Path) -> tuple[str, int]:
    match = BACKUP_NAME_RE.match(path.name)
    assert match is not None
    return match.group(1), int(match.group(2) or 1)


def list_backups(backup_dir: Path) -> list[Path]:
    """
    Lists this mod's backups in a folder, newest first.

    Only files whose name exactly matches the backup naming scheme are included.
    """
    if not backup_dir.is_dir():
        return []
    found = [
        entry
        for entry in backup_dir.iterdir()
        if entry.is_file() and BACKUP_NAME_RE.match(entry.name)
    ]
    return sorted(found, key=_sort_key, reverse=True)


def _read_fingerprint(zip_path: Path) -> str | None:
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            comment = zf.comment.decode("utf-8", "replace")
    except (OSError, zipfile.BadZipFile):
        return None
    if comment.startswith(FINGERPRINT_PREFIX):
        return comment[len(FINGERPRINT_PREFIX) :].strip()
    return None


def _pick_output_path(backup_dir: Path, now: datetime) -> Path:
    stamp = now.strftime(TIMESTAMP_FORMAT)
    candidate = backup_dir / f"{BACKUP_PREFIX}{stamp}.zip"
    counter = 2
    while candidate.exists() or candidate.with_name(candidate.name + PARTIAL_SUFFIX).exists():
        candidate = backup_dir / f"{BACKUP_PREFIX}{stamp}_{counter}.zip"
        counter += 1
    return candidate


def _write_and_verify(files: list[_SaveFile], fingerprint: str, output: Path) -> None:
    partial = output.with_name(output.name + PARTIAL_SUFFIX)
    try:
        with zipfile.ZipFile(partial, "x", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for f in files:
                date_time = time.localtime(max(f.mtime, _MIN_ZIP_TIME))[:6]
                info = zipfile.ZipInfo(f.rel_path, date_time=date_time)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                zf.writestr(info, f.data)
            zf.comment = (FINGERPRINT_PREFIX + fingerprint).encode("utf-8")

        # Verify: every file present, every CRC good, every byte identical to what we read
        with zipfile.ZipFile(partial, "r") as zf:
            bad = zf.testzip()
            if bad is not None:
                raise BackupError(f"Verification failed: '{bad}' is corrupt in the new backup.")
            if sorted(zf.namelist()) != sorted(f.rel_path for f in files):
                raise BackupError("Verification failed: the new backup is missing files.")
            for f in files:
                if zf.read(f.rel_path) != f.data:
                    raise BackupError(f"Verification failed: '{f.rel_path}' doesn't match.")

        os.replace(partial, output)
    except BaseException:
        try:
            partial.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _clean_stale_partials(backup_dir: Path) -> None:
    """Removes leftover temp files from a backup that was interrupted (e.g. the game crashed)."""
    for entry in backup_dir.iterdir():
        if not entry.name.endswith(PARTIAL_SUFFIX):
            continue
        if BACKUP_NAME_RE.match(entry.name[: -len(PARTIAL_SUFFIX)]) and entry.is_file():
            try:
                entry.unlink()
            except OSError:
                pass


def send_to_recycle_bin(path: Path) -> None:
    """
    Moves a file to the Windows Recycle Bin, so a deleted backup can still be restored.

    Raises OSError if that isn't possible. The file is never permanently deleted as a fallback.
    """
    import ctypes  # noqa: PLC0415
    from ctypes import wintypes  # noqa: PLC0415

    if not hasattr(ctypes, "windll"):
        raise OSError("The Recycle Bin is only available on Windows.")

    class SHFILEOPSTRUCTW(ctypes.Structure):
        # shellapi.h packs this struct to 1 byte on 32-bit Windows, natural alignment on 64-bit
        _pack_ = 1 if ctypes.sizeof(ctypes.c_void_p) == 4 else 8
        _fields_ = (
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", wintypes.LPCWSTR),
            ("pTo", wintypes.LPCWSTR),
            ("fFlags", wintypes.WORD),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", wintypes.LPVOID),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        )

    FO_DELETE = 0x3  # noqa: N806
    FOF_SILENT = 0x4  # noqa: N806
    FOF_NOCONFIRMATION = 0x10  # noqa: N806
    FOF_ALLOWUNDO = 0x40  # noqa: N806
    FOF_NOERRORUI = 0x400  # noqa: N806

    op = SHFILEOPSTRUCTW()
    op.wFunc = FO_DELETE
    op.pFrom = os.path.abspath(path) + "\0"  # Must be double null terminated
    op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI

    ret = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))  # type: ignore
    if ret != 0 or op.fAnyOperationsAborted or path.exists():
        raise OSError(f"Couldn't move to the Recycle Bin (error {ret:#x}).")


# At most this many old backups are removed per new backup. With the limit unchanged, each new
# backup replaces one old one. If the limit is lowered, or a stray settings reset happens, the
# history shrinks gradually instead of being wiped in one go.
MAX_REMOVALS_PER_BACKUP = 2


def _prune(
    backup_dir: Path,
    keep: int,
    protect: Path | None,
    remove: Callable[[Path], None],
) -> tuple[list[Path], list[str]]:
    deleted: list[Path] = []
    errors: list[str] = []
    # Oldest first
    candidates = [p for p in reversed(list_backups(backup_dir)[keep:]) if p != protect]
    for old in candidates[:MAX_REMOVALS_PER_BACKUP]:
        try:
            remove(old)
            deleted.append(old)
        except OSError as ex:
            errors.append(f"{old.name}: {ex}")
    return deleted, errors


def make_backup(
    save_dir: Path,
    backup_dir: Path,
    *,
    skip_unchanged: bool = True,
    keep: int | None = None,
    now: datetime | None = None,
    remove: Callable[[Path], None] = send_to_recycle_bin,
) -> BackupResult:
    """
    Zips the contents of the save folder into a new, timestamped backup.

    Args:
        save_dir: The folder to back up. Never modified.
        backup_dir: The folder to put backups in. Created if it doesn't exist.
        skip_unchanged: If True, and the newest existing backup already holds identical saves, don't
                        make a new one.
        keep: If not None, after a successful backup, remove the oldest backups so only this many
              remain (at most MAX_REMOVALS_PER_BACKUP per call).
        remove: How to remove an old backup. Defaults to sending it to the Recycle Bin.
        now: Override the timestamp (for tests).
    Returns:
        A BackupResult describing what happened.
    Raises:
        BackupError: For problems the user needs to fix (missing folders etc.).
        OSError: For unexpected I/O errors.
    """
    save_dir = Path(save_dir)
    backup_dir = Path(backup_dir)

    if not save_dir.is_dir():
        raise BackupError(f"Save folder not found:\n{save_dir}")
    if _normalise(save_dir) == _normalise(backup_dir):
        raise BackupError("The backup folder can't be the same as the save folder.")
    # A backup folder inside the save folder is allowed (it's skipped when zipping), as is one that
    # contains the save folder (pruning only ever deletes files matching our own naming scheme).

    files = _read_save_files(save_dir, backup_dir)
    if not files:
        raise BackupError(f"No files found in the save folder:\n{save_dir}")

    fingerprint = _fingerprint(files)

    backup_dir.mkdir(parents=True, exist_ok=True)
    _clean_stale_partials(backup_dir)

    existing = list_backups(backup_dir)
    if skip_unchanged and existing and _read_fingerprint(existing[0]) == fingerprint:
        return BackupResult(
            path=None,
            file_count=len(files),
            skipped_unchanged=True,
            latest_existing=existing[0],
        )

    output = _pick_output_path(backup_dir, now or datetime.now())
    _write_and_verify(files, fingerprint, output)

    result = BackupResult(path=output, file_count=len(files))
    if keep is not None and keep >= 1:
        result.deleted, result.delete_errors = _prune(backup_dir, keep, output, remove)
    return result
