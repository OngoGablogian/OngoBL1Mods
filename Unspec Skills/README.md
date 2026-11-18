# Unspec Skills

A **Borderlands GOTY / GOTY Enhanced** mod for the [willow1-mod-manager](https://github.com/bl-sdk/willow1-mod-manager) that allows you to freely respec your skill points right from the Skills menu without having to purchase a full respec at a New-U station.

This is a port of ZetaDaemon's Borderlands 2 mod [Unspec Skills](https://github.com/ZetaDaemon/bl-sdk-mods/tree/main/UnspecSkills).

## Features

### Unspec Skills
- Highlight a skill in the skill tree and press the unspec button to take one point out of it. The point goes back into your unspent skill points.
- It's free and happens straight away in the skill menu, with no trip to a New-U station.
- The skill's effect drops along with its points, tiers lock again when you drop below their requirement, and the change is saved like any other skill change.
- You can't remove a point that a skill higher up in the same tree needs to stay unlocked. You get the failure sound instead.
- The action skill can't be unspecced.

## Controls
Set both in the mod's options:
- **Unspec Button (Keyboard/Mouse)**: default Right Mouse Button. Can also be Middle Mouse Button, Backspace, Delete or R.
- **Unspec Button (Controller)**: default X. Can also be Y, Left Bumper, Right Bumper, Left Trigger, Right Trigger, Back or None.

## Requirements

- Borderlands GOTY or Borderlands GOTY Enhanced
- [willow1-mod-manager](https://github.com/bl-sdk/willow1-mod-manager) (the Python SDK)

## Installation

1. Download [`UnspecSkills.sdkmod`](https://github.com/OngoGablogian/OngoBL1Mods/raw/refs/heads/main/Unspec%20Skills/UnspecSkills.sdkmod) from this repository.
2. Copy it into your `sdk_mods` folder, inside your Borderlands install's `Binaries` folder.
3. Start the game and open **Mods** from the main menu.
4. Choose **Unspec Skills** and make sure it's enabled.

## Co-op
- Only the host (or a single player game) can unspec. A client gets the failure sound.

## Credits
- **ZetaDaemon** for the original [Unspec Skills](https://github.com/ZetaDaemon/bl-sdk-mods/tree/main/UnspecSkills) for Borderlands 2.
