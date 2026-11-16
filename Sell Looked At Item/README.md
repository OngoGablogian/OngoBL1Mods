# Sell Looked At Item

A **Borderlands GOTY / GOTY Enhanced** mod for the [willow1-mod-manager](https://github.com/bl-sdk/willow1-mod-manager) that adds a keybind to sell the item you're looking at on the ground without picking it up.

## Features

- **Sell Looked At Item keybind**: look at a weapon, shield, grenade mod, or class mod on the ground and press the key. The item's cash value goes straight into your wallet so you never have to pick it up or visit a vendor.
- **Mission items are protected**: quest items are never sold.
- **Items worth nothing are skipped**: items with no cash value are left alone.
- **Lightweight**: no settings, hooks or console commands, just the one keybind.

## Requirements

- Borderlands GOTY or Borderlands GOTY Enhanced
- [willow1-mod-manager](https://github.com/bl-sdk/willow1-mod-manager) (the Python SDK)

## Installation

1. Download [`SellLookedAtItem.sdkmod`](https://github.com/OngoGablogian/OngoBL1Mods/raw/refs/heads/main/Sell%20Looked%20At%20Item/SellLookedAtItem.sdkmod) from this repository.
2. Copy it into your `sdk_mods` folder, inside your Borderlands install's `Binaries` folder.
3. Start the game and open **Mods** from the main menu.
4. Choose **Sell Looked At Item** and make sure it's enabled.
5. Open **Keybinds** and assign a key to **Sell Looked At Item**. No key is bound by default.

## Usage

- In game, look at a dropped item until its item card appears.
- Press your assigned key to sell it.

This keybind was taken from **Bonk Utilities**. If you also run Bonk Utilities, unbind its *Sell Looked At Item* key (or disable that mod) so that both mods don't fire on the same press.

## Credits

- **Pyrex** for the original feature in [Bonk Utilities](https://github.com/PyrexBLJ/BL1-SDK-Mods/tree/main/BonkUtilities).

