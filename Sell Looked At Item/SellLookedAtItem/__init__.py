from mods_base import keybind, EInputEvent, get_pc, build_mod

# "Sell Looked At Item" keybind, isolated from Pyrex's BonkUtilities.
# Look at an item on the ground and press the key to sell it for its
# cash value without picking it up. Mission items are never sold.


@keybind(identifier="Sell Looked At Item", key=None, event_filter=EInputEvent.IE_Pressed)
def sellLookedAtItem() -> None:
    pc = get_pc()
    if pc is None or pc.myHUD is None:
        return

    item = pc.myHUD.SavedLookAtInventory
    if item is None:
        return

    pickup = item.Base
    if pickup is None:
        return

    if item.CashValue > 0 and not pickup.bIsMissionItem:
        pc.PlayerReplicationInfo.AddCurrencyOnHand(item.CashValue)
        pickup.FailedPickup()
        pickup.PickupShrinkDuration = 0.25
        pickup.ShrinkPickupBeforeDestruction()
        pickup.Behavior_ChangeUsability(2)


build_mod()
