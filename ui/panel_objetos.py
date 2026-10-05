"""Panel de objetos: lo que se ve en la camara/video durante la sesion actual."""

from __future__ import annotations

from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import formato

COLUMNAS = ["#", "Nombre", "Clase COCO", "Categoria",
            "1a vez", "Ultima vez", "Veces", "Conf. max"]


class PanelObjetos(QWidget):
    """Tabla en vivo. Se actualiza sin parpadeo: solo reconstruye si aparecen
    filas nuevas, si no solo refresca los contadores."""

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self._db = db
        self._sesion_id: int | None = None
        self._fila_de: dict[int, int] = {}   # objeto_id -> fila de la tabla

        self.titulo = QLabel("Sin sesion activa")
        self.titulo.setStyleSheet("font-weight: 600; padding: 2px;")

        self.tabla = QTableWidget(0, len(COLUMNAS))
        self.tabla.setHorizontalHeaderLabels(COLUMNAS)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        cabecera = self.tabla.horizontalHeader()
        for i in range(len(COLUMNAS)):
            cabecera.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        cabecera.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self.titulo)
        layout.addWidget(self.tabla, 1)

    # --- ciclo de vida de la sesion -------------------------------------

    def iniciar_sesion(self, sesion_id: int, fuente: str) -> None:
        self._sesion_id = sesion_id
        self._fila_de.clear()
        self.tabla.setRowCount(0)
        self.titulo.setText(f"Sesion #{sesion_id} · fuente: {fuente}")

    def finalizar(self) -> None:
        self._sesion_id = None
        self.titulo.setText("Sesion finalizada (la tabla queda como estaba)")

    # --- sincronizacion --------------------------------------------------

    def sincronizar(self) -> None:
        if self._sesion_id is None:
            return
        objetos = self._db.listar_objetos_sesion(self._sesion_id)
        ids = {o["id"] for o in objetos}
        nuevos = ids - set(self._fila_de)

        if nuevos or len(objetos) != len(self._fila_de):
            self._reconstruir(objetos, nuevos)
        else:
            for o in objetos:
                fila = self._fila_de[o["id"]]
                self._poner(fila, 6, str(o["detecciones"]))
                self._poner(fila, 7, f"{o['confianza_max']:.2f}")
                self._poner(fila, 5, formato.hora(o["ultima_deteccion"]))

    def _reconstruir(self, objetos: list[dict], nuevos: set[int]) -> None:
        self.tabla.setRowCount(len(objetos))
        self._fila_de.clear()
        for fila, o in enumerate(objetos):
            self._fila_de[o["id"]] = fila
            color = QColor(o["color"] or "#38BDF8")
            self._poner(fila, 0, str(o["id"]))
            item_nombre = QTableWidgetItem(o["etiqueta"] or o["clase"])
            item_nombre.setForeground(QBrush(color))
            item_nombre.setToolTip(f"Clase COCO: {o['clase']}")
            self.tabla.setItem(fila, 1, item_nombre)
            self._poner(fila, 2, o["clase"])
            self._poner(fila, 3, o["categoria"] or "sin categoria")
            self._poner(fila, 4, formato.hora(o["primera_deteccion"]))
            self._poner(fila, 5, formato.hora(o["ultima_deteccion"]))
            self._poner(fila, 6, str(o["detecciones"]))
            self._poner(fila, 7, f"{o['confianza_max']:.2f}")
            if o["id"] in nuevos:
                self._resaltar(fila, color)

    def _poner(self, fila: int, columna: int, texto: str) -> None:
        item = self.tabla.item(fila, columna)
        if item is None:
            self.tabla.setItem(fila, columna, QTableWidgetItem(texto))
        elif item.text() != texto:
            item.setText(texto)

    def _resaltar(self, fila: int, color: QColor) -> None:
        fondo = QColor(color)
        fondo.setAlpha(60)
        for columna in range(len(COLUMNAS)):
            item = self.tabla.item(fila, columna)
            if item:
                item.setBackground(QBrush(fondo))