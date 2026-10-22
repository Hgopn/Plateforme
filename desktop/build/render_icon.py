"""Render the neutral launcher fallback icon without external image tools."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

SIZE = 512


def rounded(x: int, y: int, left: int, top: int, right: int, bottom: int,
            radius: int) -> bool:
    nearest_x = max(left + radius, min(x, right - radius))
    nearest_y = max(top + radius, min(y, bottom - radius))
    return (x - nearest_x) ** 2 + (y - nearest_y) ** 2 <= radius**2


def chunk(kind: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + kind + body + struct.pack(
        ">I", zlib.crc32(kind + body) & 0xFFFFFFFF
    )


def main() -> None:
    rows = []
    for y in range(SIZE):
        row = bytearray(b"\x00")
        for x in range(SIZE):
            inside = rounded(x, y, 0, 0, SIZE - 1, SIZE - 1, 110)
            bar = any(rounded(x, y, 125, top, 387, top + 37, 18)
                      for top in (150, 238, 326))
            row.extend((232, 229, 218, 255) if bar else
                       (23, 34, 26, 255) if inside else (0, 0, 0, 0))
        rows.append(row)
    body = b"".join(rows)
    png = (b"\x89PNG\r\n\x1a\n" +
           chunk(b"IHDR", struct.pack(">IIBBBBB", SIZE, SIZE, 8, 6, 0, 0, 0)) +
           chunk(b"IDAT", zlib.compress(body, level=9)) + chunk(b"IEND", b""))
    Path(__file__).with_name("icon.png").write_bytes(png)


if __name__ == "__main__":
    main()
