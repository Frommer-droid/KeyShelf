"""Преобразование оригинального PNG в multi-resolution ICO и лист миниатюр."""
import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter

SIZES = (16, 24, 32, 48, 64, 128, 256)
ROOT = Path(__file__).resolve().parents[1]


def png_bytes(image):
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise RuntimeError("Не удалось кодировать PNG.")
    return bytes(data)


def main():
    application = QGuiApplication([])
    source = QImage(str(Path(sys.argv[1]).resolve()))
    if source.isNull() or source.width() != source.height() or not source.hasAlphaChannel():
        raise ValueError("Нужен квадратный PNG с прозрачностью.")
    preview = ROOT / "docs" / "app-icon.png"
    assert source.save(str(preview), "PNG")
    frames = [source.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation) for size in SIZES]
    payloads = [png_bytes(frame) for frame in frames]
    offset = 6 + 16 * len(SIZES)
    directory = []
    for size, payload in zip(SIZES, payloads, strict=True):
        encoded_size = size if size < 256 else 0
        directory.append(struct.pack("<BBBBHHII", encoded_size, encoded_size, 0, 0,
                                     1, 32, len(payload), offset))
        offset += len(payload)
    (ROOT / "logo.ico").write_bytes(struct.pack("<HHH", 0, 1, len(SIZES)) +
                                    b"".join(directory) + b"".join(payloads))
    sheet = QImage(1100, 600, QImage.Format.Format_ARGB32)
    sheet.fill(QColor("#282C34"))
    painter = QPainter(sheet)
    painter.setPen(QColor("#E6E6E6"))
    painter.setFont(QFont("Tahoma", 11))
    painter.drawText(20, 28, "Иконка: реальные размеры 1:1")
    x = 20
    widths = [110, 110, 110, 140, 140, 190, 280]
    for size, frame, cell_width in zip(SIZES, frames, widths, strict=True):
        painter.drawText(x, 55, f"{size} px")
        painter.drawImage(x, 70, frame)
        x += cell_width
    painter.drawText(20, 365, "Маленькие размеры, увеличенные ×4 без сглаживания")
    for index, (size, frame) in enumerate(zip(SIZES[:4], frames[:4], strict=True)):
        x = 20 + index * 270
        painter.drawText(x + 205, 390, f"{size} px")
        enlarged = frame.scaled(size * 4, size * 4, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.FastTransformation)
        painter.drawImage(x, 380, enlarged)
    painter.end()
    assert sheet.save(str(ROOT / "docs" / "icon-sizes.png"), "PNG")
    print(f"ICO sizes={SIZES}; PNG alpha preserved; interpreter={sys.executable}")
    del application


if __name__ == "__main__":
    main()
