# SDU Guaranteed

A **Borderlands GOTY / GOTY Enhanced** mod for the [willow1-mod-manager](https://github.com/bl-sdk/willow1-mod-manager) that makes Backpack SDU mission rewards guaranteed.

This is an updated version of Miner Of Worlds' (MOW531) [SDU Guaranteed](https://github.com/MOW531/MOW531-BL1-SDK-Mods/tree/main/SDU%20Guaranteed).

## Features

### Guaranteed Backpack SDUs
- Claptrap Rescue missions always reward a Backpack SDU, on every playthrough. In the unmodded game they often give a grenade mod instead, especially in Playthrough 2.
- Works at any level and with any amount of free backpack space.
- Covers the base game, The Zombie Island of Dr. Ned and Claptrap's New Robot Revolution Claptraps. Any other Backpack SDU reward that gets loaded is picked up automatically, which should include Lockdown Palace in The Secret Armory of General Knoxx.
- No options to configure. Enable the mod and it works.

### Status Command
- **`sdu_guaranteed_status`**: type this in the console to list every Backpack SDU reward currently loaded and whether it's patched.

## Changes From the Original
- **Reliable patching**: the original only patched on every third world load event, so some map loads could miss the patch and leave the reward random. This version checks on every map load and skips anything already patched.
- **Works as soon as it's enabled**: the original waited for a map change. This version patches immediately when you enable it mid-game.
- **Clean disable**: the original left the rewards patched until the game reloaded them. This version saves the original values and restores them when you disable it.
- **Broader DLC coverage**: besides the three rewards the original patched, any other loaded Backpack SDU reward (such as a DLC-specific one) is patched too.
- **Keeps each reward's own manufacturer**: the original made every Backpack SDU reward a Dahl item. This version keeps the manufacturer each one already had.
- **`sdu_guaranteed_status` console command** added for checking the patch in-game.

## Requirements

- Borderlands GOTY or Borderlands GOTY Enhanced
- [willow1-mod-manager](https://github.com/bl-sdk/willow1-mod-manager) (the Python SDK)

## Installation

1. Download [`SDUGuaranteed.sdkmod`](https://github.com/OngoGablogian/OngoBL1Mods/raw/refs/heads/main/SDU%20Guaranteed/SDUGuaranteed.sdkmod) from this repository.
2. Copy it into your `sdk_mods` folder, inside your Borderlands install's `Binaries` folder.
3. Start the game and open **Mods** from the main menu.
4. Choose **SDU Guaranteed** and make sure it's enabled.

## Co-op
- Untested. Mission rewards are rolled by the host, so the host most likely needs the mod installed and enabled.

## Credits
- **Miner Of Worlds (MOW531)** for the original [SDU Guaranteed](https://github.com/MOW531/MOW531-BL1-SDK-Mods/tree/main/SDU%20Guaranteed) (GPL-3.0 License).
