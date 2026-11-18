# Saves Backuper

A **Borderlands GOTY / GOTY Enhanced** mod for the [willow1-mod-manager](https://github.com/bl-sdk/willow1-mod-manager) that automatically backs up your save files.

This is a port of plu5's Borderlands 2 mod [Saves Backuper](https://github.com/plu5/p-borderlands/tree/main/SavesBackuper).

## Features

### Backups
- Each time you launch the game, your whole save folder is zipped into a timestamped backup, such as `SaveData_2026-11-17_21-30-05.zip`. This happens before any character is loaded or saved.
- Your save files are only ever read, never changed. Each backup is checked against your saves before it's kept.
- **Back Up Now**: makes a backup straight away.
- **Open Backup Folder**: opens the backup folder in File Explorer.
- **Back Up On Game Launch**: backs up each time the game starts (on by default).
- **Skip If Unchanged**: doesn't make a new backup if your saves are identical to the latest one (on by default).

### Old Backups
- Every backup is kept by default.
- **Delete Old Backups**: when on, moves the oldest backups to the Recycle Bin so only *Backups To Keep* remain (off by default). At most 2 are removed per new backup, so your history is never wiped in one go.
- **Backups To Keep**: how many backups to keep when *Delete Old Backups* is on (1–100, default 10).
- Renamed backups are never removed. To keep a backup forever, add something like `keep_` to the front of its name.

### Folders
- Saves are read from:
  - GOTY Enhanced: `Documents\My Games\Borderlands Game of the Year\Binaries\SaveData`
  - GOTY: `Documents\My Games\Borderlands\SaveData`
- Backups are saved to:
  - GOTY Enhanced: `Documents\My Games\Borderlands Game of the Year\SaveData Backups`
  - GOTY: `Documents\My Games\Borderlands\SaveData Backups`
- A Documents folder that has been moved (to OneDrive or another drive, for example) is still found.
- **Folders**: shows the folders in use, and lets you change or reset them. To use a different folder, right-click it in File Explorer, choose **Copy as path**, then press **Set Save Folder From Clipboard** or **Set Backup Folder From Clipboard**.

## Restoring a Backup
1. Quit the game.
2. Open the backup zip and copy the files inside it into your save folder, replacing the existing ones.

## Requirements

- Borderlands GOTY or Borderlands GOTY Enhanced
- [willow1-mod-manager](https://github.com/bl-sdk/willow1-mod-manager) (the Python SDK)

## Installation

1. Download [`SavesBackuper.sdkmod`](https://github.com/OngoGablogian/OngoBL1Mods/raw/refs/heads/main/Saves%20Backuper/SavesBackuper.sdkmod) from this repository.
2. Copy it into your `sdk_mods` folder, inside your Borderlands install's `Binaries` folder.
3. Start the game and open **Mods** from the main menu.
4. Choose **Saves Backuper** and make sure it's enabled.

## Credits
- **plu5** for the original Borderlands 2 [Saves Backuper](https://github.com/plu5/p-borderlands/tree/main/SavesBackuper).
