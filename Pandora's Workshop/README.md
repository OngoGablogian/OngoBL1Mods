# Pandora's Workshop

A **Borderlands GOTY Enhanced** mod for the [willow1-mod-manager](https://github.com/bl-sdk/willow1-mod-manager) that lets you edit, duplicate and import weapons and gear in game, using only parts the game itself accepts.

This is a modified version of Tisrok's [Pandora's Workshop](https://www.nexusmods.com/borderlandsgotyenhanced/mods/106). It removes the invalid-part modes, adds importing of WillowTree codes into the backpack, and improves the item card preview.

## Features

### Weapon and Gear Editing
- Edit the parts, quality and level of any weapon, shield, grenade mod or class mod in your inventory.
- **Select Inventory Weapon**: choose which weapon to edit. While scrolling the list, the item card shows the highlighted weapon.
- **Shields / Grenades / Class Mods**: choose which gear to edit. The card follows the highlighted item here too.
- Only parts in the game's own part lists can be chosen, pasted or imported, so every weapon and item the mod makes is valid.
- Quality and Level sliders update the card live for both weapons and gear.
- Changes can be saved, discarded, or reverted when you exit.

### Importing and Duplicating
- **Import from Clipboard**: creates a new weapon or item in your backpack from a WillowTree code. Weapon codes are 18 lines, and shield, grenade mod and class mod codes are 13 lines.
- **Duplicate**: copies the selected weapon or item into your backpack.
- Codes with parts that aren't valid are rejected, and the message names the part.
- Importing and duplicating are refused when your backpack is full.

### Item Card Preview
- The item card is shown beside the menu at its normal proportions.
- **Card Preview Size**: width of the card as a percentage of the screen (30–60%, default 40).

## Controls
- **Open Workshop**: default F7. Set it under **Keybinds** in the mod's options.
- **Escape** on the main Workshop screen: keep editing, revert and exit, or save and exit.

These keyboard shortcuts work while the Workshop is open:
- **Ctrl+C**: on a slot row (e.g. "Barrel: …"), copies the part in that slot. On a part in a part list, copies that part.
- **Ctrl+V**: pastes the copied part into the highlighted slot, or into the open part list's slot. Only works if the part is valid for that slot.
- **Delete**: on a slot row or a part in a weapon part list, empties that slot. Only works where the game allows the slot to be empty.
- A copied part stays copied until you copy another one, even after switching weapons.

## Requirements

- Borderlands GOTY Enhanced
- [willow1-mod-manager](https://github.com/bl-sdk/willow1-mod-manager) (the Python SDK)
- Not compatible with the original (non-Enhanced) game

## Installation

1. Download [`PandorasWorkshop.sdkmod`](https://github.com/OngoGablogian/OngoBL1Mods/raw/refs/heads/main/Pandora%27s%20Workshop/PandorasWorkshop.sdkmod) from this repository.
2. Copy it into your `sdk_mods` folder, inside your Borderlands install's `Binaries` folder.
3. Start the game and open **Mods** from the main menu.
4. Choose **Pandora's Workshop** and make sure it's enabled.

## Save Data
- The mod only changes weapons and gear in your inventory. It doesn't touch your character's level, XP, money, skills, proficiencies, missions or challenges.

## Co-op
- Not tested in co-op yet. Importing and duplicating are intended for single-player or the host.

## Changes from the Original
- Removed the "INVALID - Cross-Family Parts" and "PANDORA'S BOX - Unrestricted" modes, and their gear equivalents.
- Ctrl+V and Delete now follow the same Valid rules as the menus.
- Importing now creates a new weapon or item in the backpack instead of overwriting the selected one, and accepts WillowTree gear codes.
- Fixed valid weapons and DLC class mods (e.g. the Orion, Specter and Professional) being rejected on import.
- Fixed the item card being squashed, and sometimes appearing at lower resolution.
- Fixed the gun model on the item card being stretched.
- Renamed "ITEM WORKSHOP - Shields / Grenades / Class Mods" to "Shields / Grenades / Class Mods".

## Credits
- **Tisrok** for the original [Pandora's Workshop](https://www.nexusmods.com/borderlandsgotyenhanced/mods/106) (MIT License).
