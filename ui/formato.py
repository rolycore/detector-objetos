"""Formateo de fechas para la interfaz. Sin Qt: lo usan la UI y el worker."""

from __future__ import annotations

import time

SEGUNDOS_POR_DIA = 86400


def ahora() -> float:
    return time.time()


def hora(ts: float | None) -> str:
    if not ts:
        return "-"
    return time.strftime("%H:%M:%S", time.localtime(ts))


def fecha_hora(ts: float | None) -> str:
    if not ts:
        return "-"
    return time.strftime("%d/%m/%Y %H:%M:%S", time.localtime(ts))


def hace_cuanto(ts: float | None) -> str:
    """Texto corto de 'hace cuanto': 'hace 2 h 5 min', 'ayer', 'hace 3 dias'."""
    if not ts:
        return "-"
    delta = max(0.0, time.time() - ts)
    if delta < SEGUNDOS_POR_DIA:
        return f"hace {int(delta // 3600)} h {int((delta % 3600) // 60)} min"
    if delta < 2 * SEGUNDOS_POR_DIA:
        return "ayer"
    return f"hace {int(delta // SEGUNDOS_POR_DIA)} dias"


def plural(n: int, singular: str, plural_: str) -> str:
    return singular if n == 1 else plural_