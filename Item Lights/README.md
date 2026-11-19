# Item Lights

A **Borderlands GOTY / GOTY Enhanced** mod for the [willow1-mod-manager](https://github.com/bl-sdk/willow1-mod-manager) that adds a light to items lying on the ground, colored by their rarity, so loot looks nicer and is easier to spot.

This is a port of RedxYeti's Borderlands 2 mod [Item Lights](https://github.com/RedxYeti/bl2-willow2-sdkmods/tree/main/ItemLights).

## Features

### Item Lights
- Every item dropped in the world gets a small light just above it, in the color of its rarity.
- Loot already on the ground when you enable the mod is lit straight away, and the lights are removed when you disable it.
- Changing an option updates the lights on loot that's already on the ground.
- The lights don't cast shadows, which keeps them cheap on performance.
- **Weapons and Gear Only**: only weapons, shields, grenade mods, class mods and artifacts get lights (off by default).
- **Light Brightness**: how bright the lights are (1–15, default 5).
- **Light Radius**: how far the light reaches (10–1024, default 300).
- **Light Falloff**: how the brightness fades toward the edge of the light. Lower values carry the brightness out to the edge, giving it a sharper edge (1–80, default 40).

## Requirements

- Borderlands GOTY or Borderlands GOTY Enhanced
- [willow1-mod-manager](https://github.com/bl-sdk/willow1-mod-manager) (the Python SDK)

## Installation

1. Download [`ItemLights.sdkmod`](https://github.com/OngoGablogian/OngoBL1Mods/raw/refs/heads/main/Item%20Lights/ItemLights.sdkmod) from this repository.
2. Copy it into your `sdk_mods` folder, inside your Borderlands install's `Binaries` folder.
3. Start the game and open **Mods** from the main menu.
4. Choose **Item Lights** and make sure it's enabled.

## Co-op
- Not tested in co-op yet. The lights are a visual effect on your own screen, so each player who wants them should need the mod themselves.

## Credits
- **RedxYeti** for the original [Item Lights](https://github.com/RedxYeti/bl2-willow2-sdkmods/tree/main/ItemLights) for Borderlands 2.
