# Double Jump Dash

A [willow1-mod-manager](https://github.com/bl-sdk/willow1-mod-manager) mod for **Borderlands GOTY** and **Borderlands GOTY Enhanced** that lets you double jump and dash in mid-air.

This combines ports of two Borderlands 2 mods: the double jump feature from ZetaDaemon's [Movement Tech](https://github.com/ZetaDaemon/willow2-sdk-mods/tree/main/movement_tech), and the air dash feature from juso's [BL2 Eternal](https://github.com/juso40/bl2sdk-mods/tree/main/bl2eternal).

## Features

### Double Jump
- Press jump while in the air to jump again. Air jumps refill when you land.
- **Air Jumps**: how many extra jumps you get before landing (1–5, default 1).
- **Air Jump Strength**: air jump height as a percentage of a normal jump (50–200%, default 100).

### Air Dash
- While in the air, hold a movement direction and press the dash key to dash in that direction. You get two dashes per jump.
- Dashes refill once you've touched the ground and the cooldown has passed.
- **Dash Cooldown**: time after your first dash before your dashes can refill (0–3.0 s, default 1.5 s).
- **Dash Camera Shake**: a short camera shake when dashing (on by default).
- **Camera Shake Strength**: Very Low, Low, Medium or High (default Very Low).

## Controls
Set both under **Keybinds** in the mod's options:
- **Air Dash (Keyboard)**: default Left Shift.
- **Air Dash (Controller)**: default L3 (left stick click). Select it and press the controller button you want when the popup appears. Pressing the current button clears it. A and B control the popup, so they can't be used.
- **Double Jump**: No options to configure, uses the default jump button.

## Requirements

- Borderlands GOTY or Borderlands GOTY Enhanced
- [willow1-mod-manager](https://github.com/bl-sdk/willow1-mod-manager) (the Python SDK)

## Installation

1. Download [`DoubleJumpDash.sdkmod`](https://github.com/OngoGablogian/OngoBL1Mods/raw/refs/heads/main/Double%20Jump%20Dash/DoubleJumpDash.sdkmod) from this repository.
2. Copy it into your `sdk_mods` folder, inside your Borderlands install's `Binaries` folder.
3. Start the game and open **Mods** from the main menu.
4. Choose **Double Jump Dash** and make sure it's enabled.

## Co-op
- Everyone in the session needs the mod installed and enabled. Otherwise the host will correct a client's position after a double jump.

- Air dashing only works for the host. A client's dash is corrected by the host, so the client snaps back.

## Credits
- **ZetaDaemon** for the original double jump in [Movement Tech](https://github.com/ZetaDaemon/willow2-sdk-mods/tree/main/movement_tech).
- **juso** for the original air dash in [BL2 Eternal](https://github.com/juso40/bl2sdk-mods/tree/main/bl2eternal) (MIT License).
