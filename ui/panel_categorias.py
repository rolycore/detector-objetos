"""Panel de categorias: crear categorias, elegir color y renombrar clases.

Cambia lo que el detector muestra: cada clase de COCO pertenece a una categoria
(que define el color de la caja) y tiene un nombre visible opcional (alias).
"""

from __future__ import annotations

import sqlite3

import categorias
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

COLOR_POR_DEFECTO = "#38BDF8"


class DialogoCategoria(QDialog):
    """Nombre + color de una categoria."""

    def __init__(self, nombre: str = "", color: str = COLOR_POR_DEFECTO, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Categoria")
        self._color = QColor(color if QColor(color).isValid() else COLOR_POR_DEFECTO)

        self.entrada_nombre = QLineEdit(nombre)
        self.entrada_nombre.setPlaceholderText("Por ejemplo: Mascotas")

        self.boton_color = QPushButton("Elegir color")
        self.boton_color.setFixedHeight(30)
        self.boton_color.clicked.connect(self._elegir_color)
        self._pintar_boton()

        form = QFormLayout()
        form.addRow("Nombre", self.entrada_nombre)
        fila_color = QHBoxLayout()
        fila_color.addWidget(self.boton_color, 1)
        contenedor = QWidget()
        contenedor.setLayout(fila_color)
        form.addRow("Color", contenedor)

        botones = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        botones.accepted.connect(self.aceptar)
        botones.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(botones)

    def _pintar_boton(self) -> None:
        self.boton_color.setStyleSheet(
            f"background-color: {self._color.name()}; color: #0b0f14;"
            f"border: 1px solid #334155; border-radius: 4px; font-weight: 600;"
        )

    def _elegir_color(self) -> None:
        elegida = QColorDialog.getColor(self._color, self, "Elegir color")
        if elegida.isValid():
            self._color = elegida
            self._pintar_boton()

    def aceptar(self) -> None:
        if not self.entrada_nombre.text().strip():
            QMessageBox.warning(self, "Falta el nombre",
                                "La categoria necesita un nombre.")
            return
        self.accept()

    @property
    def nombre(self) -> str:
        return self.entrada_nombre.text().strip()

    @property
    def color(self) -> str:
        return self._color.name()


class PanelCategorias(QWidget):
    """Categorias (con color) + mapeo clase -> categoria y alias."""

    mapeo_cambiado = Signal()

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self._db = db
        self._bloqueado = True     # evita guardar mientras se puebla la tabla
        self._clases: list[str] = []

        self.lista = QListWidget()
        self.lista.setMinimumWidth(220)
        self.lista.currentRowChanged.connect(self._seleccion_actualizada)
        self.lista.itemDoubleClicked.connect(self._editar)

        self.boton_nueva = QPushButton("Nueva")
        self.boton_renombrar = QPushButton("Renombrar")
        self.boton_eliminar = QPushButton("Eliminar")
        self.boton_nueva.clicked.connect(self._nueva)
        self.boton_renombrar.clicked.connect(self._editar)
        self.boton_eliminar.clicked.connect(self._eliminar)

        botones = QVBoxLayout()
        botones.addWidget(self.boton_nueva)
        botones.addWidget(self.boton_renombrar)
        botones.addWidget(self.boton_eliminar)
        botones.addStretch(1)

        izquierda = QVBoxLayout()
        izquierda.addWidget(QLabel("Categorias"))
        izquierda.addWidget(self.lista, 1)
        izquierda.addLayout(botones)

        contenedor_izq = QWidget()
        contenedor_izq.setLayout(izquierda)

        self.buscador = QLineEdit()
        self.buscador.setPlaceholderText("Buscar clase de COCO (por ejemplo: dog)")
        self.buscador.textChanged.connect(self._filtrar)

        self.tabla = QTableWidget(0, 3)
        self.tabla.setHorizontalHeaderLabels(
            ["Clase COCO", "Categoria", "Nombre visible"]
        )
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        cabecera = self.tabla.horizontalHeader()
        cabecera.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        cabecera.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        cabecera.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

        derecha = QVBoxLayout()
        derecha.addWidget(self.buscador)
        derecha.addWidget(self.tabla, 1)

        contenedor_der = QWidget()
        contenedor_der.setLayout(derecha)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(contenedor_izq)
        splitter.addWidget(contenedor_der)
        splitter.setStretchFactor(1, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(splitter)

    # --- carga ---------------------------------------------------------

    def refrescar(self) -> None:
        self._cargar_categorias()
        self._cargar_clases()

    def _cargar_categorias(self) -> None:
        seleccionada = self.lista.currentRow()
        self.lista.blockSignals(True)
        self.lista.clear()
        for cat in self._db.listar_categorias():
            item = QListWidgetItem(cat["nombre"])
            item.setForeground(QColor(cat["color"]))
            item.setToolTip(f"Color {cat['color']}")
            self.lista.addItem(item)
        self.lista.blockSignals(False)
        if 0 <= seleccionada < self.lista.count():
            self.lista.setCurrentRow(seleccionada)
        elif self.lista.count():
            self.lista.setCurrentRow(0)
        self._actualizar_botones()

    def _cargar_clases(self) -> None:
        """Puebla la tabla: una fila por clase de COCO."""
        self._clases = categorias.leer_clases()
        mapa = self._db.mapa_clases()
        lista_cats = self._db.listar_categorias()
        nombres = [c["nombre"] for c in lista_cats]

        self._bloqueado = True
        try:
            self.tabla.setRowCount(len(self._clases))
            for fila, clase in enumerate(self._clases):
                item = QTableWidgetItem(clase)
                self.tabla.setItem(fila, 0, item)

                datos = mapa.get(clase) or {}

                combo = QComboBox()
                combo.addItems(nombres)
                pos = combo.findText(datos.get("categoria") or "")
                combo.setCurrentIndex(pos if pos >= 0 else 0)
                combo.currentIndexChanged.connect(
                    lambda _f=fila: self._guardar_fila(_f)
                )
                self.tabla.setCellWidget(fila, 1, combo)

                entrada = QLineEdit(datos.get("etiqueta") or "")
                entrada.setPlaceholderText(clase)
                entrada.editingFinished.connect(
                    lambda _f=fila: self._guardar_fila(_f)
                )
                self.tabla.setCellWidget(fila, 2, entrada)
        finally:
            self._bloqueado = False
        self._filtrar(self.buscador.text())

    def mapa_actual(self) -> dict[str, dict]:
        """Mapa clase -> {categoria, categoria_id, etiqueta} segun lo que se ve."""
        return self._db.mapa_clases()

    # --- acciones de categoria -----------------------------------------

    def _categoria_seleccionada(self) -> dict | None:
        fila = self.lista.currentRow()
        if fila < 0:
            return None
        categorias_ = self._db.listar_categorias()
        if fila >= len(categorias_):
            return None
        return categorias_[fila]

    def _seleccion_actualizada(self, _fila: int) -> None:
        self._actualizar_botones()

    def _actualizar_botones(self) -> None:
        self.boton_renombrar.setEnabled(self.lista.currentRow() >= 0)
        # siempre hay que dejar al menos una categoria
        self.boton_eliminar.setEnabled(
            self.lista.currentRow() >= 0 and len(self._db.listar_categorias()) > 1
        )

    def _nueva(self) -> None:
        dialogo = DialogoCategoria(parent=self)
        if not dialogo.exec():
            return
        try:
            self._db.crear_categoria(dialogo.nombre, dialogo.color)
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "Nombre repetido",
                                f"Ya existe la categoria '{dialogo.nombre}'.")
            return
        self.refrescar()
        self.mapeo_cambiado.emit()

    def _editar(self) -> None:
        cat = self._categoria_seleccionada()
        if not cat:
            return
        dialogo = DialogoCategoria(cat["nombre"], cat["color"], self)
        if not dialogo.exec():
            return
        try:
            self._db.actualizar_categoria(cat["id"], dialogo.nombre, dialogo.color)
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "Nombre repetido",
                                f"Ya existe la categoria '{dialogo.nombre}'.")
            return
        self.refrescar()
        self.mapeo_cambiado.emit()

    def _eliminar(self) -> None:
        cat = self._categoria_seleccionada()
        if not cat:
            return
        if len(self._db.listar_categorias()) <= 1:
            QMessageBox.information(self, "No se puede",
                                    "Tiene que quedar al menos una categoria.")
            return

        afectadas = [c for c, d in self._db.mapa_clases().items()
                     if d["categoria_id"] == cat["id"]]
        # El destino tiene que ser una categoria distinta de la que se borra:
        # si no, las clases afectadas quedan apuntando a un id que desaparece.
        candidatas = [c for c in self._db.listar_categorias()
                      if c["id"] != cat["id"]]
        destino = next((c["nombre"] for c in candidatas
                        if c["nombre"] == "Otros"),
                       candidatas[0]["nombre"] if candidatas else None)

        if afectadas and destino is None:
            QMessageBox.information(self, "No se puede",
                                    "Hace falta al menos otra categoria.")
            return

        detalle = (f"{len(afectadas)} clase(s) pasarán a '{destino}'."
                   if afectadas else "No hay clases asignadas a esta categoria.")
        respuesta = QMessageBox.question(
            self, "Eliminar categoria",
            f"¿Eliminar '{cat['nombre']}'?\n\n{detalle}\n"
            "El historial ya guardado no se borra (quedará sin categoria).",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if respuesta != QMessageBox.StandardButton.Yes:
            return

        ids = {c["nombre"]: c["id"] for c in self._db.listar_categorias()}
        if afectadas and destino in ids:
            mapa = self._db.mapa_clases()
            for clase in afectadas:
                self._db.asignar_clase(clase, ids[destino],
                                       mapa[clase]["etiqueta"])
        self._db.eliminar_categoria(cat["id"])
        self.refrescar()
        self.mapeo_cambiado.emit()

    # --- tabla de clases ------------------------------------------------

    # --- filtro ---------------------------------------------------------

    def _filtrar(self, texto: str) -> None:
        texto = texto.strip().lower()
        mapa = self._db.mapa_clases()
        for fila, clase in enumerate(self._clases):
            alias = (mapa.get(clase) or {}).get("etiqueta", "")
            coincide = (not texto) or texto in clase.lower() or texto in alias.lower()
            self.tabla.setRowHidden(fila, not coincide)

    # --- sincronizacion con la base -------------------------------------

    def _guardar_fila(self, fila: int) -> None:
        """Guarda la categoria y/o el alias que el usuario toco en esa fila."""
        if self._bloqueado or fila >= len(self._clases):
            return
        combo = self.tabla.cellWidget(fila, 1)
        entrada = self.tabla.cellWidget(fila, 2)
        if combo is None or entrada is None:
            return
        ids = {c["nombre"]: c["id"] for c in self._db.listar_categorias()}
        self._db.asignar_clase(self._clases[fila],
                               ids.get(combo.currentText()),
                               entrada.text())
        self.mapeo_cambiado.emit()