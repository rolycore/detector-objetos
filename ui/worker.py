"""Hilo de deteccion.

Es el **unico** lugar del proyecto donde se corre la inferencia, y vive fuera del
hilo de la interfaz: `run()` se ejecuta en un QThread. Toda la comunicacion va por
senales, y aca no se toca ningun widget ni la base de datos.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import cv2
from PySide6.QtCore import QThread, Signal

import detector
from tracker import IoUTracker

from . import formato


@dataclass
class ConfigDeteccion:
    """Todo lo que hay que saber para arrancar una deteccion."""

    weights: str
    cfg: str
    names: str
    source: object            # int (indice de camara) o str (ruta de video)
    conf: float = 0.5
    nms: float = 0.4
    cuda: bool = False
    umbral_iou: float = 0.3
    max_perdidos: int = 15
    # cadencia con la que se avisa a la UI sobre el estado (no sobre cada frame)
    intervalo_estado: float = 0.2
    # ventana de calculo de FPS, en fotogramas
    ventana_fps: int = 10
    # cuantos fotogramas se dibuja la hora de "1a vez" junto a la caja
    frames_mostrar_primera_vez: int = 300
    mapa: dict = field(default_factory=dict)


class DetectorWorker(QThread):
    """Detecta en segundo plano y manda frames + estado a la interfaz."""

    frame_listo = Signal(object)         # np.ndarray BGR ya dibujado
    objetos_actualizados = Signal(list)  # estado de los objetos del fotograma
    log = Signal(str)
    error = Signal(str)
    metricas = Signal(dict)              # {"fps", "visibles", "objetos"}
    terminado = Signal()

    def __init__(self, config: ConfigDeteccion, parent=None):
        super().__init__(parent)
        self.config = config
        self._detenido = False

    # --- control desde el hilo principal --------------------------------

    def detener(self) -> None:
        """Pide que el bucle termine en la proxima iteracion."""
        self._detenido = True

    @property
    def detenido(self) -> bool:
        return self._detenido

    # --- bucle ---------------------------------------------------------

    def run(self) -> None:
        """Bucle de deteccion. Corre en el hilo del QThread, no en el de la UI."""
        cfg = self.config
        cap = None
        try:
            self.log.emit("Cargando modelo YOLOv4...")
            try:
                net, classes, output_layers = detector.load_yolo(
                    cfg.weights, cfg.cfg, cfg.names, cfg.cuda
                )
            except SystemExit:
                # check_file() llama a sys.exit; aca hay que convertirlo en error
                self.error.emit(
                    "Falta un archivo del modelo. Revisa --weights / --cfg / --names."
                )
                return
            except cv2.error as exc:
                self.error.emit(f"No se pudo cargar la red: {exc}")
                return

            self.log.emit(f"Modelo cargado. Abriendo fuente: {cfg.source}")
            cap = cv2.VideoCapture(cfg.source)
            if not cap.isOpened():
                self.error.emit(f"No se pudo abrir la fuente: {cfg.source}")
                return

            tracker = IoUTracker(umbral_iou=cfg.umbral_iou,
                                 max_perdidos=cfg.max_perdidos)
            mapa = cfg.mapa
            fps_inicio = time.time()
            frames_fps = 0
            fps = 0.0
            ultimo_estado = 0.0
            total_objetos = 0

            while not self._detenido and not self.isInterruptionRequested():
                ok, frame = cap.read()
                if not ok:
                    self.log.emit("Fin del archivo de video.")
                    break

                detecciones = detector.detect_objects(
                    frame, net, output_layers, cfg.conf, cfg.nms
                )
                crudas = [(caja, classes[cid], conf)
                          for caja, cid, conf in detecciones]
                seguidas = tracker.update(crudas, time.time())

                # El color y el nombre visible salen del mapa que le paso la UI.
                escala = max(0.6, min(2.0, frame.shape[1] / 640.0))
                para_dibujar = []
                estado = []
                for det in seguidas:
                    info = mapa.get(det.clase) or {}
                    etiqueta = info.get("etiqueta") or det.clase
                    # #38BDF8: mismo celeste que el banner, en ambos ordenes.
                    color_rgb = info.get("color_rgb") or (56, 189, 248)
                    color_bgr = info.get("color_bgr") or (248, 189, 56)

                    if not det.desaparecida:
                        textos = f"{etiqueta} {det.confianza:.2f}"
                        if det.frames <= cfg.frames_mostrar_primera_vez:
                            subtexto = (f"#{det.track_id} · "
                                        f"1a vez {formato.hora(det.primera_vez)}")
                        else:
                            subtexto = f"#{det.track_id}"
                        para_dibujar.append({
                            "caja": det.caja,
                            "texto": textos,
                            "subtexto": subtexto,
                            "color": color_bgr,
                        })

                    estado.append({
                        "track_id": det.track_id,
                        "clase": det.clase,
                        "etiqueta": etiqueta,
                        "color_rgb": color_rgb,
                        "color_bgr": color_bgr,
                        "caja": det.caja,
                        "confianza": det.confianza,
                        "primera_vez": det.primera_vez,
                        "frames": det.frames,
                        "nueva": det.nueva,
                        "reaparecida": det.reaparecida,
                        "desaparecida": det.desaparecida,
                    })

                if detecciones:
                    total_objetos += sum(1 for d in seguidas if d.nueva)

                detector.dibujar_objetos(frame, para_dibujar, escala)

                frames_fps += 1
                if frames_fps >= cfg.ventana_fps:
                    ahora = time.time()
                    fps = frames_fps / max(1e-6, ahora - fps_inicio)
                    fps_inicio, frames_fps = ahora, 0

                cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
                self.frame_listo.emit(frame)

                ahora = time.time()
                if ahora - ultimo_estado >= cfg.intervalo_estado:
                    ultimo_estado = ahora
                    self.objetos_actualizados.emit(estado)
                    self.metricas.emit({
                        "fps": fps,
                        "visibles": sum(1 for d in seguidas if not d.desaparecida),
                        "objetos": total_objetos,
                    })

            self.log.emit("Deteccion detenida.")
        except Exception as exc:  # noqa: BLE001 - el hilo no debe morir en silencio
            self.error.emit(f"Error durante la deteccion: {type(exc).__name__}: {exc}")
        finally:
            if cap is not None:
                cap.release()
            self.terminado.emit()