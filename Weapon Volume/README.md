# Weapon Volume BL1E

A **Borderlands GOTY Enhanced** mod for the [willow1-mod-manager](https://github.com/bl-sdk/willow1-mod-manager) that lets you set the volume of your weapons separately for each weapon type.

Some weapons are far louder than others and the game's single "Sound Effects Volume" slider can't fix that without turning down everything else. Weapon Volume BL1E gives you a volume slider per weapon type instead.

## Features

- A separate volume slider (0-100%, in steps of 5) for each weapon type:
  - Pistols / Revolvers (including repeaters)
  - SMGs
  - Shotguns
  - Assault Rifles
  - Sniper Rifles
  - Rocket Launchers
- A **Grenades** slider for grenade bounce and explosion sounds (not affected by the master slider).
- A **Master Gun Volume** slider applied on top of the per-type sliders.
- **Only My Weapons** - leave enemy and NPC weapons at their normal volume.
- **Affect Reload / Handling Sounds** - also scale reload, equip and dry-fire sounds, not just firing sounds.
- **Reset All To 100%** button.
- Only affects weapon and grenade sounds - music, voices, footsteps, and other sound effects are left alone.

Eridian weapons use the slider for their base type (an Eridian SMG follows the SMG slider, and so on).

## Requirements

- Borderlands GOTY Enhanced
- [willow1-mod-manager](https://github.com/bl-sdk/willow1-mod-manager) (the Python SDK)
- Not compatible with the original (non-Enhanced) game

## Installation

1. Download [`WeaponVolumeBL1E.sdkmod`](https://github.com/OngoGablogian/OngoBL1Mods/raw/refs/heads/main/Weapon%20Volume/WeaponVolumeBL1E.sdkmod) from this repository.
2. Copy it into your `sdk_mods` folder, inside your Borderlands install's `Binaries` folder.
3. Start the game and open **Mods** from the main menu.
4. Choose **Weapon Volume BL1E** and make sure it's enabled.

## Options

| Option | Default | Description |
| --- | --- | --- |
| Master Gun Volume | 100 | Applied on top of every per-type slider |
| Pistols / Revolvers | 100 | Pistols, revolvers and repeaters |
| SMGs | 100 | Submachine guns |
| Shotguns | 100 | Shotguns |
| Assault Rifles | 100 | Combat / assault rifles |
| Sniper Rifles | 100 | Sniper rifles |
| Rocket Launchers | 100 | Rocket launchers |
| Grenades | 100 | Grenade bounce and explosion sounds (ignores the master slider) |
| Only My Weapons | Off | Leave enemy and NPC weapons at stock volume |
| Affect Reload / Handling Sounds | Off | Also scale reload, equip and dry-fire sounds |
| Log Weapon Sounds | Off | Debug: records which sounds weapons play |
| Debug: Copy Full Report | - | Debug: copies a report to the clipboard and saves it to a file |
| Reset All To 100% | - | Sets the master, per-type and grenade sliders back to 100 |

