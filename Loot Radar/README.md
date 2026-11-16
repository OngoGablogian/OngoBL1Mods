# Loot Radar

A [willow1-mod-manager](https://github.com/bl-sdk/willow1-mod-manager) mod for **Borderlands GOTY** and **Borderlands GOTY Enhanced** that marks loot, quest items and unopened chests on your compass, with the distance to each one.

## Mark colours

- Green: weapons and items
- Yellow: money
- Blue: ammo
- Pink: health
- Purple: a quest item
- Red: an unopened red chest
- White: an unopened white chest
- Deep pink: an unopened Knoxx chest

## Settings

- **Show Weapon Loot**: Weapons and items on the compass.
- **Show Money Loot**: Money on the compass.
- **Show Ammo Loot**: Ammo on the compass.
- **Show Health Loot**: Health on the compass.
- **Show Quest Items**: Pickups that belong to a mission, such as the Scavenger weapon parts or Hidden Journal entries. They only appear while their mission is active, are never hidden by Hide Full Pickups or Display Only Better Weapons, and take priority over ordinary loot sitting in the same spot on the compass.
- **Show Red Chests**: Red chests nobody has opened yet.
- **Show White Chests**: White chests nobody has opened yet.
- **Show Knoxx Chests**: Knoxx DLC chests nobody has opened yet.
- **Display Only Better Weapons**: Hides weapons that are worse than the worst one of that type you already carry, and stops you picking them up. Score is shots x damage x pellets, divided by (shots x fire interval plus reload), where shots is the magazine divided by the ammo each shot costs.
- **Hide Full Pickups**: Ammo and health you cannot carry stops lighting up.
- **Show Distance**: How far away each mark is, written above it.
- **Units**: Metres or feet.
- **Checks per second**: How often loot and chests around you are looked for. Lower is better for performance.

## Requirements

- Borderlands GOTY or Borderlands GOTY Enhanced
- [willow1-mod-manager](https://github.com/bl-sdk/willow1-mod-manager) (the Python SDK)

## Install

1. Download [`LootRadar.sdkmod`](https://github.com/OngoGablogian/OngoBL1Mods/raw/refs/heads/main/Loot%20Radar/LootRadar.sdkmod) from this repository.
2. Copy it into your `sdk_mods` folder, inside your Borderlands install's `Binaries` folder.
3. Start the game and open **Mods** from the main menu.
4. Choose **Loot Radar** and make sure it's enabled.

## Credits

This is a modified version of [Loot Radar](https://github.com/EerieGoesD/borderlands-1-goty-mods/tree/main/LootRadar)
by **EerieGoesD**, with quest item marks added by Ongo. All other features are **EerieGoesD's** work.

If you'd like to support the original author, you can
[buy EerieGoesD a coffee](https://buymeacoffee.com/eeriegoesd).
