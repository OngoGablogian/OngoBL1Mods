"""Correct Enhanced's out-of-bounds item-card replication copy.

CacheItemCard counts attribute-slot lines in r14d, then appends part/name lines.
The shipped copy loop uses that SOURCE index as its destination index in a
two-element ReplicatedItemCardModifierValues array. Five slot lines plus custom
text overwrite TempStatModifierModifierStack.Data with the first line's float.

The replacement keeps source/destination indices separate, bounds both, skips
hidden lines, and resets unused entries. It changes neither effects nor card
text. Exact original bytes must match; no on-disk executable edits. Applied at
module import, before loading a character, and retained until process exit so
existing custom items remain safe when the Workshop UI is disabled.
"""
from __future__ import annotations

import ctypes
import struct

RVA = 0x1401BB6
ORIGINAL = bytes.fromhex("4533e4418bdc4963c6418bfc488d34c50c0400004903f70f1f00453bb7000400000f8da40000004180bfce000000030f858700000085db7810418b45083bd87c2885db750485c074204c8d0deee1520041b856020000488d150d455300488d0d4e455300e881e1dafe498b4500f644071401744885db7810418b45083bd87c2885db750485c074204c8d0dafe1520041b856020000488d15ce445300488d0d0f455300e842e1dafe498b45008b4c0710894efc891e41ffc64883c608ffc34883c71883fb020f8c4fffffff")
REPLACEMENT = bytes.fromhex("4531e431db4180bfce000000030f856100000048b800000000ffffffff498987080400004989871004000083fb020f8d40000000453b75080f8d360000004963c6488d3c40498b5500488d3cfaf64714010f84150000008b4710418984df080400004589b4df0c040000ffc341ffc6e9b7ffffff909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090")


def install() -> str:
    if ctypes.sizeof(ctypes.c_void_p) != 8:
        return "not-enhanced"
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
    kernel.GetModuleHandleW.restype = ctypes.c_void_p
    base = kernel.GetModuleHandleW("BorderlandsGOTY.exe")
    if not base:
        return "not-enhanced"
    dos = ctypes.string_at(base, 64)
    pe_offset = struct.unpack_from("<I", dos, 60)[0]
    if dos[:2] != b"MZ" or not 64 <= pe_offset < 4096:
        raise RuntimeError("Unrecognized Enhanced executable header")
    pe = ctypes.string_at(base + pe_offset, 88)
    if pe[:4] != b"PE\0\0" or struct.unpack_from("<H", pe, 4)[0] != 0x8664:
        raise RuntimeError("Unrecognized Enhanced executable architecture")
    image_size = struct.unpack_from("<I", pe, 80)[0]
    if len(ORIGINAL) != 203 or len(REPLACEMENT) != 203 or RVA + 203 > image_size:
        raise RuntimeError("Invalid item-card fix signature or executable size")
    address = base + RVA
    current = ctypes.string_at(address, len(ORIGINAL))
    if current == REPLACEMENT:
        return "already-installed"
    if current != ORIGINAL:
        raise RuntimeError("Enhanced item-card code differs; no memory was changed")
    kernel.VirtualProtect.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint, ctypes.POINTER(ctypes.c_uint)]
    kernel.VirtualProtect.restype = ctypes.c_int
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    kernel.FlushInstructionCache.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    kernel.FlushInstructionCache.restype = ctypes.c_int
    old = ctypes.c_uint()
    if not kernel.VirtualProtect(address, len(REPLACEMENT), 0x40, ctypes.byref(old)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        ctypes.memmove(address, REPLACEMENT, len(REPLACEMENT))
        if not kernel.FlushInstructionCache(kernel.GetCurrentProcess(), address, len(REPLACEMENT)):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        restored = ctypes.c_uint()
        if not kernel.VirtualProtect(address, len(REPLACEMENT), old.value, ctypes.byref(restored)):
            raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.string_at(address, len(REPLACEMENT)) != REPLACEMENT:
        raise RuntimeError("Item-card fix verification failed")
    return "installed"
