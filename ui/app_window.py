"""Ventana principal de la aplicacion.

Aqui se junta todo: los controles, el video, las tablas y el hilo de deteccion.

Regla de oro: **esta clase es la unica que escribe en SQLite y la unica que toca
widgets**. El worker solo manda senales. Todos los slots se ejecutan en el hilo
principal porque las senales entre hilos de Qt se entregan en cola.
"""

from __future__ import annotations

import os
import sys
import time

import categorias
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from database import Database
from detector import parse_source

from . import formato
from .panel_categorias import PanelCategorias
from .panel_historial import PanelHistorial
from .panel_objetos import PanelObjetos
from .widgets_video import VisorVideo
from .worker import ConfigDeteccion, DetectorWorker

COLOR_POR_DEFECTO = "#38BDF8"


class VentanaPrincipal(QMainWindow):
    def __init__(self, db: Database, args, parent=None):
        super().__init__(parent)
        self._db = db
        self._args = args
        self._worker: DetectorWorker | None = None
        self._sesion_id: int | None = None
        self._objeto_por_track: dict[int, dict] = {}   # track_id -> {id, frames}
        self._ids_ya_mostrados: set[int] = set()
        self._clases_vistas: set[str] = set()
        self._mapa: dict[str, dict] = {}                # clase -> datos de color
        self._cat_id_por_clase: dict[str, int | None] = {}
        self._timer_historial: QTimer | None = None

        self.setWindowTitle("Detector de objetos - YOLOv4")
        self.resize(1360, 860)
        self._construir_ui()
        self._conectar()

        self._db.asegurar_datos_iniciales()
        self._reconstruir_mapa()
        self.panel_categorias.refrescar()
        self.panel_historial.refrescar()
        self._actualizar_estado_inicial()

    # --- construccion ---------------------------------------------------

    def _construir_ui(self) -> None:
        # --- controles de arriba ---
        self.combo_fuente = QComboBox()
        self.combo_fuente.setEditable(True)
        self.combo_fuente.addItems(["0", "1", "2", "3"])
        self.combo_fuente.setFixedWidth(90)
        self.combo_fuente.setToolTip("Indice de camara, o ruta de video")
        self.combo_fuente.setCurrentText(str(self._args.source))

        self.boton_archivo = QPushButton("Archivo...")
        self.boton_archivo.setToolTip("Elegir un archivo de video")

        self.spin_conf = QDoubleSpinBox()
        self.spin_conf.setRange(0.05, 0.95)
        self.spin_conf.setSingleStep(0.05)
        self.spin_conf.setDecimals(2)
        self.spin_conf.setValue(self._args.conf)
        self.spin_conf.setToolTip("Umbral de confianza")

        self.spin_nms = QDoubleSpinBox()
        self.spin_nms.setRange(0.05, 0.95)
        self.spin_nms.setSingleStep(0.05)
        self.spin_nms.setDecimals(2)
        self.spin_nms.setValue(self._args.nms)
        self.spin_nms.setToolTip("Umbral de NMS")

        self.check_cuda = QCheckBox("CUDA")
        self.check_cuda.setChecked(self._args.cuda)

        self.boton_iniciar = QPushButton("Iniciar")
        self.boton_iniciar.setDefault(True)
        self.boton_detener = QPushButton("Detener")
        self.boton_detener.setEnabled(False)

        controles = QWidget()
        fila = QVBoxLayout(controles)
        linea = QHBoxLayout()
        linea.addWidget(QLabel("Fuente:"))
        linea.addWidget(self.combo_fuente)
        linea.addWidget(self.boton_archivo)
        linea.addSpacing(16)
        linea.addWidget(QLabel("Conf:"))
        linea.addWidget(self.spin_conf)
        linea.addWidget(QLabel("NMS:"))
        linea.addWidget(self.spin_nms)
        linea.addWidget(self.check_cuda)
        linea.addStretch(1)
        linea.addWidget(self.boton_iniciar)
        linea.addWidget(self.boton_detener)
        fila.addLayout(linea)
        fila.setContentsMargins(8, 6, 8, 0)

        # --- panels ---
        self.visor = VisorVideo()
        self.panel_objetos = PanelObjetos(self._db)
        self.panel_categorias = PanelCategorias(self._db)
        self.panel_historial = PanelHistorial(self._db)

        izquierda = QSplitter(Qt.Orientation.Vertical)
        izquierda.addWidget(self.visor)
        izquierda.addWidget(self.panel_objetos)
        izquierda.setStretchFactor(0, 3)
        izquierda.setStretchFactor(1, 2)

        pestanas = QTabWidget()
        pestanas.addTab(self.panel_categorias, "Categorias")
        pestanas.addTab(self.panel_historial, "Historial")

        cuerpo = QSplitter(Qt.Orientation.Horizontal)
        cuerpo.addWidget(izquierda)
        cuerpo.addWidget(pestanas)
        cuerpo.setStretchFactor(0, 3)
        cuerpo.setStretchFactor(1, 2)
        cuerpo.setChildrenCollapsible(False)

        raiz = QWidget()
        layout = QVBoxLayout(raiz)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(controles)
        layout.addWidget(cuerpo, 1)
        self.setCentralWidget(raiz)

        self.etiqueta_estado = QLabel("Listo")
        self.statusBar().addWidget(self.etiqueta_estado)
        self.statusBar().showMessage("Presiona Iniciar para detectar objetos")

    def _conectar(self) -> None:
        self.boton_iniciar.clicked.connect(self.iniciar)
        self.boton_detener.clicked.connect(self.detener)
        self.boton_archivo.clicked.connect(self._elegir_archivo)
        self.combo_fuente.currentTextChanged.connect(self._actualizar_estado_inicial)
        self.spin_conf.valueChanged.connect(self._actualizar_estado_inicial)
        self.spin_nms.valueChanged.connect(self._actualizar_estado_inicial)
        self.panel_categorias.mapeo_cambiado.connect(self._cambio_mapeo)
        self.panel_historial.historial_vaciado.connect(self._historial_vacio)

    # --- fuente ---------------------------------------------------------

    def _elegir_archivo(self) -> None:
        ruta, _ = QFileDialog.getOpenFileName(
            self, "Elegir video", "",
            "Videos (*.mp4 *.avi *.mov *.mkv *.webm);;Todos los archivos (*)",
        )
        if ruta:
            self.combo_fuente.setCurrentText(ruta)

    def _fuente_actual(self):
        texto = self.combo_fuente.currentText().strip()
        if not texto:
            return None
        return parse_source(texto)

    # --- mapa de clases --------------------------------------------------

    def _reconstruir_mapa(self) -> None:
        """clase -> {etiqueta, categoria, categoria_id, color_bgr, color_rgb}."""
        colores = {c["nombre"]: c["color"] for c in self._db.listar_categorias()}
        self._mapa.clear()
        self._cat_id_por_clase.clear()
        for clase, datos in self._db.mapa_clases().items():
            color = colores.get(datos["categoria"], COLOR_POR_DEFECTO)
            self._mapa[clase] = {
                "categoria": datos["categoria"],
                "categoria_id": datos["categoria_id"],
                "etiqueta": datos["etiqueta"],
                "color_rgb": categorias.hex_a_rgb(color),
                "color_bgr": categorias.hex_a_bgr(color),
            }
            self._cat_id_por_clase[clase] = datos["categoria_id"]

    def _cambio_mapeo(self) -> None:
        """Cambio categoria/alias/color: al vuelo en el video, sin reiniciar."""
        self._reconstruir_mapa()
        self.panel_objetos.sincronizar()
        if self._worker is not None:
            self.visor.mostrar_banner(
                "Categorias actualizadas",
                "Los cambios ya se ven en el video.",
                COLOR_POR_DEFECTO, 3,
            )

    def _historial_vacio(self) -> None:
        self.panel_objetos.sincronizar()
        self._actualizar_estado_inicial()

    # --- arranque y parada -----------------------------------------------

    def iniciar(self) -> None:
        if self._worker is not None:
            return
        fuente = self._fuente_actual()
        if fuente is None:
            QMessageBox.warning(self, "Falta la fuente",
                                "Elegi una camara o un archivo de video.")
            return

        self._db.asegurar_datos_iniciales()
        self._reconstruir_mapa()

        self._objeto_por_track.clear()
        self._ids_ya_mostrados.clear()
        self._clases_vistas.clear()

        self._sesion_id = self._db.abrir_sesion(str(fuente))
        self.panel_objetos.iniciar_sesion(self._sesion_id, str(fuente))

        config = ConfigDeteccion(
            weights=self._args.weights,
            cfg=self._args.cfg,
            names=self._args.names,
            source=fuente,
            conf=self.spin_conf.value(),
            nms=self.spin_nms.value(),
            cuda=self.check_cuda.isChecked(),
            mapa=self._mapa,          # se comparte a proposito: ver _cambio_mapeo
        )
        self._worker = DetectorWorker(config)
        self._worker.frame_listo.connect(self.visor.mostrar_frame)
        self._worker.objetos_actualizados.connect(self._procesar_estado)
        self._worker.metricas.connect(self._mostrar_metricas)
        self._worker.log.connect(self._registrar_log)
        self._worker.error.connect(self._mostrar_error)
        self._worker.terminado.connect(self._deteccion_terminada)
        self._worker.start()

        self.boton_iniciar.setEnabled(False)
        self.boton_detener.setEnabled(True)
        self.visor.limpiar("Cargando modelo...")
        self._registrar_log(f"Sesion #{self._sesion_id} iniciada")
        self._timer_historial = QTimer(self)
        self._timer_historial.setInterval(5000)
        self._timer_historial.timeout.connect(self.panel_historial.refrescar)
        self._timer_historial.start()

    def detener(self) -> None:
        if self._worker is None:
            return
        self.statusBar().showMessage("Deteniendo...")
        self._worker.detener()
        self._worker.wait(5000)

    def _deteccion_terminada(self) -> None:
        self._cerrar_sesion()
        if self._timer_historial is not None:
            self._timer_historial.stop()
        self.boton_iniciar.setEnabled(True)
        self.boton_detener.setEnabled(False)
        self._worker = None
        self.panel_objetos.finalizar()
        self.panel_historial.refrescar()
        self._actualizar_estado_inicial()

    def _cerrar_sesion(self) -> None:
        if self._sesion_id is not None:
            self._db.cerrar_sesion(self._sesion_id)
            self._registrar_log(f"Sesion #{self._sesion_id} cerrada")
            self._sesion_id = None

    # --- datos del hilo --------------------------------------------------

    def _procesar_estado(self, estado: list[dict]) -> None:
        """Llega en el hilo principal: aca si se toca SQLite."""
        if self._sesion_id is None:
            return

        visibles = [d for d in estado if not d["desaparecida"]]
        clases_nuevas = {d["clase"] for d in visibles} - self._clases_vistas
        nuevos: list[tuple[str, float, tuple, str]] = []
        reapariciones: list[tuple[str, tuple]] = []

        for det in estado:
            anterior = self._objeto_por_track.get(det["track_id"])

            if anterior is None:
                objeto_id = self._db.registrar_objeto(
                    self._sesion_id,
                    det["track_id"],
                    det["clase"],
                    det["etiqueta"],
                    self._cat_id_por_clase.get(det["clase"]),
                    det["confianza"],
                    det["primera_vez"],
                )
                self._objeto_por_track[det["track_id"]] = {
                    "id": objeto_id, "frames": det["frames"],
                }
                self._db.registrar_evento(objeto_id, det["primera_vez"], "nueva")
                if objeto_id not in self._ids_ya_mostrados:
                    self._ids_ya_mostrados.add(objeto_id)
                    nuevos.append((det["etiqueta"], det["confianza"],
                                   det["color_rgb"], det["clase"]))
            else:
                # El detector va mas rapido que la UI: se guarda el delta de
                # fotogramas de una sola vez.
                delta = det["frames"] - anterior["frames"]
                if delta > 0:
                    self._db.actualizar_objeto(anterior["id"], det["confianza"],
                                               formato.ahora(), delta)
                    anterior["frames"] = det["frames"]

            if det["reaparecida"]:
                objeto_id = self._objeto_por_track[det["track_id"]]["id"]
                self._db.registrar_evento(objeto_id, formato.ahora(),
                                          "reaparicion")
                reapariciones.append((det["etiqueta"], det["color_rgb"]))

        self._clases_vistas.update(d["clase"] for d in visibles)

        if nuevos:
            self._banner_nuevos(nuevos, clases_nuevas)
        if reapariciones:
            self._banner_reapariciones(reapariciones)

        self.panel_objetos.sincronizar()

    def _banner_nuevos(self, nuevos: list[tuple],
                       clases_nuevas: set[str] | None = None) -> None:
        clases_nuevas = clases_nuevas or set()
        detalle = ", ".join(f"{nombre} {conf:.0%}"
                            for nombre, conf, _c, _cl in nuevos[:4])
        if len(nuevos) > 4:
            detalle += f" y {len(nuevos) - 4} mas"
        color = nuevos[0][2]
        if any(clase in clases_nuevas for _n, _c, _co, clase in nuevos):
            titulo = "Nuevo tipo de objeto"
        elif len(nuevos) == 1:
            titulo = "Deteccion nueva"
        else:
            titulo = f"{len(nuevos)} detecciones nuevas"
        self.visor.mostrar_banner(titulo, detalle, color, 5)

    def _banner_reapariciones(self, reapariciones: list[tuple]) -> None:
        detalle = ", ".join(nombre for nombre, _ in reapariciones[:4])
        self.visor.mostrar_banner("Volvio a aparecer", detalle,
                                  reapariciones[0][1], 4)

    # --- estado de la barra ---------------------------------------------

    def _mostrar_metricas(self, metricas: dict) -> None:
        self.etiqueta_estado.setText(
            f"{metricas['visibles']} visibles · "
            f"{metricas['objetos']} en esta sesion · "
            f"{metricas['fps']:.1f} FPS"
        )

    def _registrar_log(self, texto: str) -> None:
        self.statusBar().showMessage(f"{formato.hora(formato.ahora())}  {texto}")

    def _mostrar_error(self, mensaje: str) -> None:
        self._registrar_log(mensaje)
        self.visor.mostrar_banner("Error", mensaje, "#F87171", 10)
        QMessageBox.critical(self, "Error de deteccion", mensaje)

    def _actualizar_estado_inicial(self) -> None:
        r = self._db.resumen()
        self.etiqueta_estado.setText(
            f"{r['sesiones']} sesion(es) · {r['objetos']} objeto(s) · "
            f"{r['categorias']} categoria(s)"
        )

    # --- cierre ----------------------------------------------------------

    def closeEvent(self, event) -> None:
        if self._worker is not None:
            self._worker.detener()
            self._worker.wait(5000)
            self._worker = None
        if self._timer_historial is not None:
            self._timer_historial.stop()
        self._cerrar_sesion()
        self.panel_historial.refrescar()
        self._db.cerrar()
        event.accept()


def ejecutar_app(args) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Detector de objetos")

    db = Database(args.db)
    ventana = VentanaPrincipal(db, args)
    ventana.show()
    return app.exec()


def _crear_app_offscreen():
    """QApplication con el plugin 'offscreen', para pruebas sin pantalla."""
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance() or QApplication(sys.argv)
    return app


def autocomprobacion_ui(args) -> int:
    """Arma la ventana sin camara ni deteccion: sirve para smoke tests."""
    app = _crear_app_offscreen()
    db = Database(":memory:")
    ventana = VentanaPrincipal(db, args)
    ventana.resize(1360, 860)
    ventana.show()

    # Datos sinteticos para ver las tablas con contenido.
    sesion = db.abrir_sesion("camara 0")
    db.registrar_objeto(sesion, 1, "person", "Persona", 1, 0.91,
                        formato.ahora() - 3600)
    db.registrar_objeto(sesion, 2, "dog", "Perro", 2, 0.83, formato.ahora())
    db.actualizar_objeto(db.objeto_por_track(sesion, 2)["id"], 0.9,
                         formato.ahora(), 42)
    ventana.panel_objetos.iniciar_sesion(sesion, "camara 0")
    ventana._sesion_id = sesion
    ventana.panel_objetos.sincronizar()
    ventana.panel_historial.refrescar()
    ventana._banner_nuevos([("Perro", 0.83, (34, 197, 94), "dog")], {"dog"})
    ventana._banner_reapariciones([("Perro", (34, 197, 94))])
    # Guard de regresion: el banner tiene que aceptar "#RRGGBB" y tupla RGB.
    # Antes el hex reventaba con "QColor.__init__(): too many arguments".
    ventana.visor.mostrar_banner("Error", "Falta el modelo", "#F87171", 10)
    ventana.visor.mostrar_banner("Acepta hex", (34, 197, 94), "#22C55E", 5)
    ventana._mostrar_metricas({"visibles": 2, "objetos": 2, "fps": 7.4})

    app.processEvents()
    destino = os.path.join(os.environ.get("TEMP", "."), "ui_smoke.png")
    ventana.grab().save(destino)

    filas_objetos = ventana.panel_objetos.tabla.rowCount()
    filas_historial = ventana.panel_historial.tabla.rowCount()
    filas_clases = ventana.panel_categorias.tabla.rowCount()
    categorias_nombres = [ventana.panel_categorias.lista.item(i).text()
                          for i in range(ventana.panel_categorias.lista.count())]

    ventana.close()  # el closeEvent ya cierra la base de datos

    fallos = []
    if filas_clases != 80:
        fallos.append(f"tabla de clases con {filas_clases} filas (se esperaban 80)")
    if filas_objetos != 2:
        fallos.append(f"panel de objetos con {filas_objetos} filas (se esperaban 2)")
    if filas_historial != 2:
        fallos.append(f"historial con {filas_historial} filas (se esperaban 2)")
    if categorias_nombres[:5] != ["Personas", "Animales", "Vehiculos",
                                   "Objetos", "Otros"]:
        fallos.append(f"categorias iniciales inesperadas: {categorias_nombres}")

    print("[AUTOCOMPROBACION UI] captura:", destino)
    print("  clases COCO:", filas_clases)
    print("  categorias:", categorias_nombres)
    print("  objetos:", filas_objetos, "| historial:", filas_historial)
    if fallos:
        for f in fallos:
            print(f"  [FALLO] {f}")
        print("[AUTOCOMPROBACION UI] Resultado: FALLA")
        return 1
    print("[AUTOCOMPROBACION UI] Resultado: OK")
    return 0