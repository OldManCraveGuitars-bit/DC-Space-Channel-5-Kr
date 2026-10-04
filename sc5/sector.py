"""Recompute Mode 1 EDC/ECC after changing GD-ROM sector user data."""
from __future__ import annotations

import struct

from .disc import PAYLOAD, SECTOR, SYNC


def _tables():
    edc = []
    forward = []
    backward = [0] * 256
    for i in range(256):
        value = i
        for _ in range(8):
            value = (value >> 1) ^ (0xD8018001 if value & 1 else 0)
        edc.append(value)
        step = ((i << 1) ^ (0x11D if i & 0x80 else 0)) & 0xFF
        forward.append(step)
        backward[i ^ step] = i
    return edc, forward, backward


EDC_TABLE, ECC_FORWARD, ECC_BACKWARD = _tables()


def edc(data: bytes) -> int:
    value = 0
    for byte in data:
        value = (value >> 8) ^ EDC_TABLE[(value ^ byte) & 0xFF]
    return value


def _ecc(source: bytes, major_count: int, minor_count: int,
         major_mult: int, minor_inc: int) -> bytes:
    size = major_count * minor_count
    if len(source) < size:
        raise ValueError("ECC source too short")
    result = bytearray(major_count * 2)
    for major in range(major_count):
        index = (major >> 1) * major_mult + (major & 1)
        a = b = 0
        for _ in range(minor_count):
            temp = source[index]
            index = (index + minor_inc) % size
            a ^= temp
            b ^= temp
            a = ECC_FORWARD[a]
        a = ECC_BACKWARD[ECC_FORWARD[a] ^ b]
        result[major] = a
        result[major + major_count] = a ^ b
    return bytes(result)


def update_mode1(raw: bytes, payload: bytes) -> bytes:
    if len(raw) != SECTOR or raw[:12] != SYNC or raw[15] != 1:
        raise ValueError("Not a raw Mode 1 sector")
    if len(payload) != PAYLOAD:
        raise ValueError("Expected exactly 2048 payload bytes")
    sector = bytearray(raw)
    sector[16:2064] = payload
    struct.pack_into("<I", sector, 2064, edc(sector[:2064]))
    sector[2068:2076] = b"\0" * 8
    sector[2076:2248] = _ecc(sector[12:2076], 86, 24, 2, 86)
    sector[2248:2352] = _ecc(sector[12:2248], 52, 43, 86, 88)
    return bytes(sector)


def verify_mode1(raw: bytes) -> bool:
    return update_mode1(raw, raw[16:2064]) == raw
