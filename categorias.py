"""Categorias de objetos, colores y nombres visibles.

Este modulo define los datos de arranque (que categorias existen, que color
tiene cada una y a que categoria pertenece cada clase de COCO) mas los
utilidades para convertir colores. La persistencia de esos cambios vive en
`database.py`; aca vive el "default" y las reglas de conversion.
"""

from __future__ import annotations

import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_NAMES = os.path.join(SCRIPT_DIR, "coco.names")

# Colores en formato hex RGB (lo que se guarda en la base y muestra la UI).
# Ojo: OpenCV dibuja en BGR, por eso todo pasa por `hex_a_bgr`.
COLOR_PERSONAS = "#22C55E"
COLOR_ANIMALES = "#3B82F6"
COLOR_VEHICULOS = "#F59E0B"
COLOR_OBJETOS = "#A855F7"
COLOR_OTROS = "#EF4444"

ANIMALES = (
    "bird", "cat", "dog", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "giraffe",
)

VEHICULOS = (
    "bicycle", "car", "motorcycle", "airplane", "bus",
    "train", "truck", "boat",
)

# Categorias iniciales. El orden es el que ve el usuario en la lista.
CATEGORIAS_INICIALES = (
    {"nombre": "Personas", "color": COLOR_PERSONAS, "clases": ("person",)},
    {"nombre": "Animales", "color": COLOR_ANIMALES, "clases": ANIMALES},
    {"nombre": "Vehiculos", "color": COLOR_VEHICULOS, "clases": VEHICULOS},
    # "Objetos" y "Otros" se completan despues con lo que sobra.
    {"nombre": "Objetos", "color": COLOR_OBJETOS, "clases": ()},
    {"nombre": "Otros", "color": COLOR_OTROS, "clases": ()},
)


def leer_clases(names_path: str = DEFAULT_NAMES) -> list[str]:
    """Devuelve la lista de clases de COCO en orden de indice."""
    with open(names_path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def categoria_por_defecto(clase: str) -> str:
    """Nombre de la categoria inicial a la que pertenece una clase."""
    if clase == "person":
        return "Personas"
    if clase in ANIMALES:
        return "Animales"
    if clase in VEHICULOS:
        return "Vehiculos"
    return "Objetos"


def semilla_mapa(clases: list[str]) -> dict[str, dict]:
    """Construye el mapa inicial `clase -> {categoria, etiqueta}`.

    Las clases quedan asignadas a su categoria natural; el resto va a
    "Objetos". La etiqueta visible arranca vacia, lo que significa "usar el
    nombre crudo de coco.names".
    """
    mapa = {}
    for clase in clases:
        mapa[clase] = {
            "categoria": categoria_por_defecto(clase),
            "etiqueta": "",
        }
    return mapa


# --- colores --------------------------------------------------------

def hex_a_bgr(color: str) -> tuple[int, int, int]:
    """'#22C55E' -> (85, 197, 34) para que cv2 lo dibuje bien."""
    limpio = color.strip().lstrip("#")
    if len(limpio) == 3:  # forma corta #0af
        limpio = "".join(c * 2 for c in limpio)
    if len(limpio) != 6:
        return (239, 68, 68)  # rojo de "Otros" ante un valor raro
    try:
        r = int(limpio[0:2], 16)
        g = int(limpio[2:4], 16)
        b = int(limpio[4:6], 16)
    except ValueError:
        return (239, 68, 68)
    return (b, g, r)


def hex_a_rgb(color: str) -> tuple[int, int, int]:
    """'#22C55E' -> (34, 197, 94) para widgets de Qt."""
    limpio = color.strip().lstrip("#")
    if len(limpio) == 3:
        limpio = "".join(c * 2 for c in limpio)
    try:
        return (
            int(limpio[0:2], 16),
            int(limpio[2:4], 16),
            int(limpio[4:6], 16),
        )
    except (ValueError, IndexError):
        return (239, 68, 68)