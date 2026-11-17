# Loot Radar

A **Borderlands GOTY / GOTY Enhanced** mod for the [willow1-mod-manager](https://github.com/bl-sdk/willow1-mod-manager) that marks loot, quest items and unopened chests on your compass, with the distance to each one.

This is a modified version of EerieGoesD's [Loot Radar](https://github.com/EerieGoesD/borderlands-1-goty-mods/tree/main/LootRadar), adding marks for quest items.

## Features

### Mark Colours
- Green: weapons and items
- Yellow: money
- Blue: ammo
- Pink: health
- Purple: a quest item
- Red: an unopened red chest
- White: an unopened white chest
- Deep pink: an unopened Knoxx chest

### Loot
- **Show Weapon Loot**: weapons and items on the compass (on by default).
- **Show Money Loot**: money on the compass (on by default).
- **Show Ammo Loot**: ammo on the compass (on by default).
- **Show Health Loot**: health on the compass (on by default).
- **Show Quest Items**: pickups that belong to a mission, such as the Scavenger weapon parts or Hidden Journal entries (on by default). They only appear while their mission is active, are never hidden by Hide Full Pickups or Display Only Better Weapons, and take priority over ordinary loot sitting in the same spot on the compass.

### Chests
- **Show Red Chests**: red chests nobody has opened yet (on by default).
- **Show White Chests**: white chests nobody has opened yet (on by default).
- **Show Knoxx Chests**: Knoxx DLC chests nobody has opened yet (on by default).

### Filters
- **Display Only Better Weapons**: hides weapons that are worse than the worst one of that type you already carry, and stops you picking them up (off by default). Score is shots x damage x pellets, divided by (shots x fire interval plus reload), where shots is the magazine divided by the ammo each shot costs.
- **Hide Full Pickups**: ammo and health you cannot carry stops lighting up (on by default).

### Display
- **Show Distance**: how far away each mark is, written above it (on by default).
- **Units**: Metres or Feet (default Metres).
- **Checks per second**: how often loot and chests around you are looked for (0.1–10, default 1). Lower is better for performance.

## Requirements

- Borderlands GOTY or Borderlands GOTY Enhanced
- [willow1-mod-manager](https://github.com/bl-sdk/willow1-mod-manager) (the Python SDK)

## Installation

1. Download [`LootRadar.sdkmod`](https://github.com/OngoGablogian/OngoBL1Mods/raw/refs/heads/main/Loot%20Radar/LootRadar.sdkmod) from this repository.
2. Copy it into your `sdk_mods` folder, inside your Borderlands install's `Binaries` folder.
3. Start the game and open **Mods** from the main menu.
4. Choose **Loot Radar** and make sure it's enabled.

## Credits
- **EerieGoesD** for the original [Loot Radar](https://github.com/EerieGoesD/borderlands-1-goty-mods/tree/main/LootRadar). All features apart from the quest item marks are EerieGoesD's work. If you'd like to support the original author, you can [buy EerieGoesD a coffee](https://buymeacoffee.com/eeriegoesd).
