"""Panel de historial: todos los objetos vistos, de todas las sesiones.

Lee de SQLite (siempre en el hilo principal). Filtrar por texto, categoria o
rango de fechas.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import formato

COLUMNAS = ["#", "Nombre", "Clase COCO", "Categoria", "Primera vez",
            "Hace", "Veces", "Conf. max", "Fuente"]

RANGOS = [
    ("Todo el historial", None),
    ("Hoy", 0),
    ("Últimos 7 días", 7),
    ("Últimos 30 días", 30),
]


class PanelHistorial(QWidget):
    """Tabla del historial, con buscador y filtros."""

    historial_vaciado = Signal()

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self._db = db

        self.buscador = QLineEdit()
        self.buscador.setPlaceholderText("Buscar por nombre o clase...")
        self.buscador.textChanged.connect(self.refrescar)

        self.combo_categoria = QComboBox()
        self.combo_categoria.currentIndexChanged.connect(self.refrescar)

        self.combo_rango = QComboBox()
        for nombre, _dias in RANGOS:
            self.combo_rango.addItem(nombre)
        self.combo_rango.setCurrentIndex(1)
        self.combo_rango.currentIndexChanged.connect(self.refrescar)

        self.boton_actualizar = QPushButton("Actualizar")
        self.boton_actualizar.clicked.connect(self.refrescar)
        self.boton_vaciar = QPushButton("Vaciar historial")
        self.boton_vaciar.clicked.connect(self._vaciar)

        filtros = QHBoxLayout()
        filtros.addWidget(self.buscador, 1)
        filtros.addWidget(self.combo_categoria)
        filtros.addWidget(self.combo_rango)
        filtros.addWidget(self.boton_actualizar)
        filtros.addWidget(self.boton_vaciar)

        self.resumen = QLabel("")
        self.resumen.setStyleSheet("color: #64748b; padding: 2px;")

        self.tabla = QTableWidget(0, len(COLUMNAS))
        self.tabla.setHorizontalHeaderLabels(COLUMNAS)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setSortingEnabled(False)
        cabecera = self.tabla.horizontalHeader()
        for i in range(len(COLUMNAS)):
            cabecera.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        cabecera.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addLayout(filtros)
        layout.addWidget(self.tabla, 1)
        layout.addWidget(self.resumen)

    # --- datos -----------------------------------------------------------

    def refrescar(self) -> None:
        """Relee el historial aplicando los filtros actuales."""
        self._recargar_categorias()

        texto = self.buscador.text().strip()
        categoria = self.combo_categoria.currentData()
        dias = self.combo_rango.currentData()
        desde = None if dias is None else formato.ahora() - dias * 86400

        objetos = self._db.listar_historial(texto=texto, categoria_id=categoria,
                                          desde=desde)

        self.tabla.setRowCount(len(objetos))
        for fila, o in enumerate(objetos):
            color = QColor(o["color"] or "#38BDF8")
            self._texto(fila, 0, str(o["id"]))
            item = QTableWidgetItem(o["etiqueta"] or o["clase"])
            item.setForeground(QBrush(color))
            item.setToolTip(f"Clase COCO: {o['clase']}")
            self.tabla.setItem(fila, 1, item)
            self._texto(fila, 2, o["clase"])
            self._texto(fila, 3, o["categoria"] or "sin categoria")
            self._texto(fila, 4, formato.fecha_hora(o["primera_deteccion"]))
            self._texto(fila, 5, formato.hace_cuanto(o["primera_deteccion"]))
            self._texto(fila, 6, str(o["detecciones"]))
            self._texto(fila, 7, f"{o['confianza_max']:.2f}")
            self._texto(fila, 8, o["fuente"] or "")

        if objetos:
            total = sum(o["detecciones"] for o in objetos)
            self.resumen.setText(
                f"{len(objetos)} objeto(s) · {total} deteccion(es) en total"
            )
        else:
            self.resumen.setText("Todavia no hay objetos registrados.")

    def _recargar_categorias(self) -> None:
        """Recarga el combo de categorias respetando la seleccion actual."""
        actual = self.combo_categoria.currentData()
        self.combo_categoria.blockSignals(True)
        self.combo_categoria.clear()
        self.combo_categoria.addItem("Todas las categorías", None)
        for cat in self._db.listar_categorias():
            self.combo_categoria.addItem(cat["nombre"], cat["id"])
        pos = self.combo_categoria.findData(actual)
        self.combo_categoria.setCurrentIndex(pos if pos >= 0 else 0)
        self.combo_categoria.blockSignals(False)

    def _texto(self, fila: int, columna: int, valor: str) -> None:
        item = self.tabla.item(fila, columna)
        if item is None:
            self.tabla.setItem(fila, columna, QTableWidgetItem(valor))
        elif item.text() != valor:
            item.setText(valor)

    # --- acciones --------------------------------------------------------

    def _vaciar(self) -> None:
        respuesta = QMessageBox.question(
            self, "Vaciar historial",
            "¿Borrar todo el historial?\n\n"
            "Se borran los objetos y las sesiones, pero se conservan "
            "las categorias y el mapeo de clases.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if respuesta != QMessageBox.StandardButton.Yes:
            return
        self._db.vaciar_historial()
        self.refrescar()
        self.historial_vaciado.emit()