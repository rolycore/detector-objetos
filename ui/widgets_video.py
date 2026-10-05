"""Video embebido y banner de avisos.

El fotograma llega como numpy BGR desde el hilo de deteccion. Aca se convierte a
QPixmap. Ojo con `QImage`: no copia el buffer, asi que hay que conservar una
referencia al array numpy mientras se use (por eso `self._buffer`).
"""

from __future__ import annotations

import cv2
import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

COLOR_BANNER = "#38BDF8"


def _a_qcolor(color) -> QColor:
    """Normaliza un color a QColor.

    Acepta "#RRGGBB", una tupla RGB (r, g, b) o None. Tener todo el manejo de
    formatos aca evita el `QColor(*"#38BDF8")` que revienta con Too many
    arguments, y que ademasmezcle el orden BGR con el RGB.
    """
    if color is None:
        return QColor(COLOR_BANNER)
    if isinstance(color, str):
        q = QColor(color)
        return q if q.isValid() else QColor(COLOR_BANNER)
    try:
        r, g, b = color
    except (TypeError, ValueError):
        return QColor(COLOR_BANNER)
    return QColor(int(r), int(g), int(b))


class VisorVideo(QWidget):
    """Muestra el video anotado y, arriba, el aviso de objeto nuevo."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._buffer = None  # referencia viva del array que usa el QImage

        self.setMinimumSize(480, 320)
        self.setStyleSheet("background-color: #0b0f14;")

        self.etiqueta = QLabel("Presiona Iniciar para ver el video")
        self.etiqueta.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.etiqueta.setStyleSheet(
            "color: #64748b; font-size: 15px; background-color: #0b0f14;"
        )
        self.etiqueta.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        self.banner = QLabel()
        self.banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.banner.setWordWrap(True)
        self.banner.setVisible(False)
        self.banner.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        layout.addWidget(self.banner, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.etiqueta, 1)

        self._timer_banner = QTimer(self)
        self._timer_banner.setSingleShot(True)
        self._timer_banner.timeout.connect(self.banner.setVisible)

    # --- video ---------------------------------------------------------

    def mostrar_frame(self, frame_bgr: np.ndarray) -> None:
        """Pinta un fotograma BGR ocupando el espacio disponible."""
        alto, ancho = frame_bgr.shape[:2]
        if alto == 0 or ancho == 0:
            return

        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        self._buffer = np.ascontiguousarray(rgb)

        imagen = QImage(
            self._buffer.data,
            ancho,
            alto,
            int(self._buffer.strides[0]),
            QImage.Format.Format_RGB888,
        )
        pixmap = QPixmap.fromImage(imagen)

        destino = self.etiqueta.size()
        if destino.width() > 0 and destino.height() > 0:
            pixmap = pixmap.scaled(
                destino,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        self.etiqueta.setPixmap(pixmap)

    def limpiar(self, mensaje: str = "") -> None:
        """Deja el visor vacio (o con un mensaje centrado)."""
        self.etiqueta.clear()
        if not self.etiqueta.pixmap():
            self.etiqueta.setText(mensaje or "Sin video")

    # --- banner --------------------------------------------------------

    def mostrar_banner(self, titulo: str, subtitulo: str = "",
                       color_rgb=None, segundos: int = 5) -> None:
        """Aviso de primer plano sobre el video, con fondo semitransparente.

        `color_rgb` acepta "#RRGGBB", una tupla RGB (r, g, b) o None.
        """
        color = _a_qcolor(color_rgb)
        if not color.isValid():
            color = QColor(COLOR_BANNER)

        texto = f"<div style='font-size:17px; font-weight:600;'>{titulo}</div>"
        if subtitulo:
            texto += (f"<div style='font-size:13px; opacity:0.9;'>"
                      f"{subtitulo}</div>")
        self.banner.setText(
            f"<div style='background-color: rgba(15,23,42,220); "
            f"color:{color.name()}; border:2px solid {color.name()}; "
            f"border-radius:8px; padding:10px 18px;'>{texto}</div>"
        )
        self.banner.setVisible(True)
        self._timer_banner.start(segundos * 1000)

    def ocultar_banner(self) -> None:
        self._timer_banner.stop()
        self.banner.setVisible(False)