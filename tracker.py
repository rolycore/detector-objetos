"""Seguimiento de objetos por IoU.

Cada deteccion que llega del detector recibe un `track_id` estable mientras el
objeto siga visible. La idea es que el usuario pueda decir "el perro #3" y que la
app sepa a cual se refiere, incluso cuando se mueve entre fotogramas.

El emparejamiento es "greedy" por IoU descendente y **solo entre detecciones de
la misma clase**: si no, un perro podria heredar el ID de una persona y el
historial quedaria contaminado.
"""

from __future__ import annotations

from dataclasses import dataclass


def iou(caja_a, caja_b) -> float:
    """IoU entre dos cajas en formato [x, y, ancho, alto]."""
    ax, ay, aw, ah = caja_a
    bx, by, bw, bh = caja_b

    ax2, ay2 = ax + aw, ay + ah
    bx2, by2 = bx + bw, by + bh

    # interseccion
    ix = max(0, min(ax2, bx2) - max(ax, bx))
    iy = max(0, min(ay2, by2) - max(ay, by))
    interseccion = ix * iy
    if interseccion == 0:
        return 0.0

    union = aw * ah + bw * bh - interseccion
    if union <= 0:
        return 0.0
    return interseccion / union


@dataclass
class Track:
    """Estado interno de un objeto seguido."""

    track_id: int
    clase: str
    caja: list
    confianza: float = 0.0
    frames_perdidos: int = 0
    frames_visto: int = 1
    primera_vez: float = 0.0
    ultima_vez: float = 0.0


@dataclass
class DeteccionSeguida:
    """Una deteccion de un fotograma, ya asociada a su objeto."""

    caja: list
    clase: str
    confianza: float
    track_id: int
    primera_vez: float
    frames: int = 0
    nueva: bool = False
    reaparecida: bool = False
    desaparecida: bool = False

    def as_dict(self) -> dict:
        return {
            "caja": list(self.caja),
            "clase": self.clase,
            "confianza": self.confianza,
            "track_id": self.track_id,
            "primera_vez": self.primera_vez,
            "frames": self.frames,
            "nueva": self.nueva,
            "reaparecida": self.reaparecida,
            "desaparecida": self.desaparecida,
        }


class IoUTracker:
    """Asigna y mantiene IDs de objeto a partir de cajas por fotograma.

    Parametros:
        umbral_iou: solapamiento minimo para considerar que es el mismo objeto.
        max_perdidos: fotogramas sin ver antes de dar el objeto por desaparecido.
    """

    def __init__(self, umbral_iou: float = 0.3, max_perdidos: int = 15):
        if not 0.0 < umbral_iou <= 1.0:
            raise ValueError("umbral_iou debe estar entre 0 y 1")
        if max_perdidos < 1:
            raise ValueError("max_perdidos debe ser >= 1")
        self.umbral_iou = umbral_iou
        self.max_perdidos = max_perdidos
        self._tracks: dict[int, Track] = {}
        self._siguiente_id = 1

    # --- estado -------------------------------------------------------

    @property
    def tracks(self) -> dict[int, Track]:
        return dict(self._tracks)

    @property
    def siguiente_id_disponible(self) -> int:
        return self._siguiente_id

    def reiniciar(self) -> None:
        """Olvida todos los objetos. Se usa al cambiar de fuente de video."""
        self._tracks.clear()
        self._siguiente_id = 1

    def olvidar(self, track_id: int) -> None:
        """Saca un objeto del seguimiento."""
        self._tracks.pop(track_id, None)

    # --- asociacion ---------------------------------------------------

    def update(self, detecciones, timestamp: float = 0.0) -> list[DeteccionSeguida]:
        """Actualiza el estado con las detecciones de un fotograma.

        `detecciones` es una lista de tuplas `(caja, clase, confianza)`.
        Devuelve una lista de `DeteccionSeguida` en el mismo orden de entrada.
        Al final agrega, si corresponde, una entrada con `desaparecida=True`.
        """
        asignaciones: dict[int, int] = {}  # indice deteccion -> track_id

        # 1) emparejar con los tracks existentes, de mayor a menor IoU
        candidatos: list[tuple[float, int, int]] = []
        for i, det in enumerate(detecciones):
            caja_det, clase_det = det[0], det[1]
            for track_id, track in self._tracks.items():
                if track.clase != clase_det:
                    continue  # nunca cruzar clases distintas
                valor = iou(caja_det, track.caja)
                if valor >= self.umbral_iou:
                    candidatos.append((valor, i, track_id))

        candidatos.sort(key=lambda c: c[0], reverse=True)
        usados_det: set[int] = set()
        usados_track: set[int] = set()
        for valor, i, track_id in candidatos:
            if i in usados_det or track_id in usados_track:
                continue
            asignaciones[i] = track_id
            usados_det.add(i)
            usados_track.add(track_id)

        # 2) crear tracks nuevos para lo que quedo sin matchear
        for i, det in enumerate(detecciones):
            if i in asignaciones:
                continue
            caja_det, clase_det, conf = det[0], det[1], det[2]
            track_id = self._siguiente_id
            self._siguiente_id += 1
            self._tracks[track_id] = Track(
                track_id=track_id,
                clase=clase_det,
                caja=list(caja_det),
                confianza=conf,
                primera_vez=timestamp,
                ultima_vez=timestamp,
            )
            asignaciones[i] = track_id

        # 3) actualizar estado y armar el resultado del fotograma
        resultado: list[DeteccionSeguida] = []
        for i, det in enumerate(detecciones):
            track = self._tracks[asignaciones[i]]
            es_nueva = track.frames_visto == 1
            # venia de estar perdido en el/los fotogramas anteriores
            reaparecida = track.frames_perdidos > 0

            track.caja = list(det[0])
            track.confianza = max(track.confianza, det[2])
            track.frames_perdidos = 0
            track.frames_visto += 1
            track.ultima_vez = timestamp

            resultado.append(
                DeteccionSeguida(
                    caja=list(det[0]),
                    clase=track.clase,
                    confianza=det[2],
                    track_id=track.track_id,
                    primera_vez=track.primera_vez,
                    frames=track.frames_visto,
                    nueva=es_nueva,
                    reaparecida=reaparecida,
                )
            )

        # 4) envejecer los tracks que no se vieron en este fotograma
        vistos = set(asignaciones.values())
        for track_id, track in sorted(self._tracks.items()):
            if track_id in vistos:
                continue
            track.frames_perdidos += 1
            if track.frames_perdidos >= self.max_perdidos:
                resultado.append(
                    DeteccionSeguida(
                        caja=list(track.caja),
                        clase=track.clase,
                        confianza=track.confianza,
                        track_id=track_id,
                        primera_vez=track.primera_vez,
                        frames=track.frames_visto,
                        desaparecida=True,
                    )
                )
                del self._tracks[track_id]

        return resultado