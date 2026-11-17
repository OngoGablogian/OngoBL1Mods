"""Keep active weapon bonuses out of InitializeInternal's base-value collapse.

RecomputeAttributeBaseValues copies current values to bases and empties their
modifier stacks. Parts are intended to be collapsed; equipped skill/COM bonuses
are not. Suspend only the modifiers present before initialization, using the
engine's attribute API so current values are recalculated on removal/restoration.
"""
from contextlib import contextmanager

import unrealsdk
from mods_base import ObjectFlags

_definitions = {}


def _direct_attribute(name):
    if name not in _definitions:
        attribute = unrealsdk.construct_object("AttributeDefinition", outer=unrealsdk.find_object("Package", "Transient"))
        resolver = unrealsdk.construct_object(
            "ObjectPropertyAttributeValueResolver", outer=attribute
        )
        resolver.PropertyName = name
        attribute.Attribute = name
        attribute.ContextResolverChain = []
        attribute.ValueResolverChain = [resolver]
        attribute.ObjectFlags |= ObjectFlags.KEEP_ALIVE
        _definitions[name] = attribute
    return _definitions[name]


def _active_modifiers(weapon):
    seen = set()
    result = []
    for cls in weapon.Class._superfields():
        for prop in cls._properties():
            stack_name = str(prop.Name)
            if not stack_name.endswith("ModifierStack"):
                continue
            name = stack_name.removesuffix("ModifierStack")
            if name in seen or not hasattr(weapon, name + "BaseValue"):
                continue
            seen.add(name)
            modifiers = list(getattr(weapon, name + "ModifierStack"))
            if modifiers:
                result.append((_direct_attribute(name), name, modifiers))
    return result


@contextmanager
def suspend_bonuses(weapon):
    # Resolve everything before touching any stack. An unsupported property
    # fails without initiating a partially prepared weapon rebuild.
    active = _active_modifiers(weapon)
    removed = []
    try:
        for attribute, name, modifiers in active:
            for modifier in modifiers:
                if not attribute.RemoveAttributeModifier(weapon, modifier, True):
                    raise RuntimeError(f"Could not suspend weapon attribute {name}")
                removed.append((attribute, name, modifier))
        yield
    finally:
        failures = []
        for attribute, name, modifier in removed:
            try:
                if modifier in getattr(weapon, name + "ModifierStack"):
                    continue
                if not attribute.AddAttributeModifier(weapon, modifier, True):
                    failures.append(name)
            except Exception as exc:
                failures.append(f"{name}: {exc}")
        if failures:
            raise RuntimeError("Could not restore weapon bonuses: " + ", ".join(failures))
