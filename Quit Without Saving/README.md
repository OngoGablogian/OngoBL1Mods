# Quit Without Saving

A **Borderlands GOTY / GOTY Enhanced** mod for the [willow1-mod-manager](https://github.com/bl-sdk/willow1-mod-manager) that lets you quit to the main menu without saving.

This splits the "Quit Without Saving" keybind and the "Disable Quit To Desktop" option out of Pyrex's [Bonk Utilities](https://github.com/PyrexBLJ/BL1-SDK-Mods/tree/main/BonkUtilities), so you can use them without the rest of that mod.

## Features

### Quit Without Saving
- Press the keybind to disconnect to the main menu straight away, without the game saving your character.
- Anything since your last save is discarded: loot, money, XP, quest progress and so on.

### Disable Quit To Desktop
- Removes the **Quit to Desktop** entry from the pause menu so you can't hit it by accident (on by default).
- GOTY Enhanced only. The option doesn't appear on the original GOTY.

## Controls
Set under **Keybinds** in the mod's options:
- **Quit Without Saving**: unbound by default.

## Requirements

- Borderlands GOTY or Borderlands GOTY Enhanced
- [willow1-mod-manager](https://github.com/bl-sdk/willow1-mod-manager) (the Python SDK)

## Installation

1. Download [`QuitWithoutSaving.sdkmod`](https://github.com/OngoGablogian/OngoBL1Mods/raw/refs/heads/main/Quit%20Without%20Saving/QuitWithoutSaving.sdkmod) from this repository.
2. Copy it into your `sdk_mods` folder, inside your Borderlands install's `Binaries` folder.
3. Start the game and open **Mods** from the main menu.
4. Choose **Quit Without Saving** and make sure it's enabled.

## Compatibility note

- This keybind was taken from **Bonk Utilities**. If you also run Bonk Utilities, unbind its *Quit Without Saving* key (or disable that mod) so that both mods don't fire on the same press.

## Credits
- **Pyrex** for the original features in [Bonk Utilities](https://github.com/PyrexBLJ/BL1-SDK-Mods/tree/main/BonkUtilities) (GPL-3.0).
