"""Convert the selected PNG into a Windows ICO with crisp frames for common DPI scales."""
from __future__ import annotations

import struct
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QImage


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    source = QImage(str(root / "assets" / "app.png"))
    if source.isNull() or source.width() != source.height():
        raise SystemExit("assets/app.png must be a readable square PNG")
    frames = []
    for size in (16, 20, 24, 32, 40, 48, 64, 128, 256):
        scaled = source.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not scaled.save(buffer, "PNG"):
            raise SystemExit(f"Could not encode {size}px icon frame")
        frames.append((size, bytes(data)))
    offset = 6 + 16 * len(frames)
    header = bytearray(struct.pack("<HHH", 0, 1, len(frames)))
    for size, data in frames:
        header.extend(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset))
        offset += len(data)
    destination = root / "assets" / "app.ico"
    destination.write_bytes(header + b"".join(data for _, data in frames))
    print(f"Created {destination.name}: {len(frames)} sizes, 16–256 px")


if __name__ == "__main__":
    main()
