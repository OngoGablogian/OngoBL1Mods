# XP Multiplier

A **Borderlands GOTY / GOTY Enhanced** mod for the [willow1-mod-manager](https://github.com/bl-sdk/willow1-mod-manager) that multiplies the XP for your character and weapon proficiencies.

## Features

### Character XP
- Multiplies the XP you earn from kills. The XP popup shows the multiplied amount.
- **Character XP Multiplier**: how much to multiply character XP by (1–50x, default 1x).
- **Apply To Mission XP**: also multiplies mission reward XP by the Character XP Multiplier (on by default). The reward shown on the mission screen is updated to match.

### Weapon Proficiency
- Multiplies the proficiency XP your equipped weapon type earns from kills.
- **Proficiency XP Multiplier**: how much to multiply proficiency XP by (1–50x, default 1x).

Changes to the sliders take effect immediately, with no need to reload.

## Requirements

- Borderlands GOTY or Borderlands GOTY Enhanced
- [willow1-mod-manager](https://github.com/bl-sdk/willow1-mod-manager) (the Python SDK)

## Installation

1. Download [`XPMultiplier.sdkmod`](https://github.com/OngoGablogian/OngoBL1Mods/raw/refs/heads/main/XP%20Multiplier/XPMultiplier.sdkmod) from this repository.
2. Copy it into your `sdk_mods` folder, inside your Borderlands install's `Binaries` folder.
3. Start the game and open **Mods** from the main menu.
4. Choose **XP Multiplier** and make sure it's enabled.

## Co-op
- Not tested in co-op yet. Kill XP is worked out by the host, so the multiplier will most likely only apply to the host's own XP.
