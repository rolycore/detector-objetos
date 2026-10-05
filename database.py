"""Base de datos de la app (SQLite de la libreria estandar).

Guarda tres cosas: las categorias y el mapeo de clases, el historial de sesiones
de deteccion, y los eventos (objeto nuevo / reaparecido / desaparecido).

Regla de oro: **solo el hilo principal de la UI toca esta base**. El hilo de
deteccion no escribe nada; manda senales y la UI decide que persiste.
"""

from __future__ import annotations

import os
import sqlite3
import time

import categorias

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB_PATH = os.path.join(SCRIPT_DIR, "detector.db")

ESQUEMA = """
CREATE TABLE IF NOT EXISTS categorias (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre   TEXT NOT NULL UNIQUE,
    color    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS clase_categoria (
    clase        TEXT PRIMARY KEY,
    categoria_id INTEGER REFERENCES categorias(id) ON DELETE CASCADE,
    etiqueta     TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS sesiones (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    inicio  REAL NOT NULL,
    fin     REAL,
    fuente  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS objetos (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    sesion_id        INTEGER NOT NULL REFERENCES sesiones(id) ON DELETE CASCADE,
    track_id         INTEGER NOT NULL,
    clase            TEXT NOT NULL,
    etiqueta         TEXT NOT NULL,
    categoria_id     INTEGER REFERENCES categorias(id) ON DELETE SET NULL,
    confianza_max    REAL NOT NULL DEFAULT 0,
    detecciones      INTEGER NOT NULL DEFAULT 1,
    primera_deteccion REAL NOT NULL,
    ultima_deteccion  REAL NOT NULL,
    UNIQUE (sesion_id, track_id)
);

CREATE TABLE IF NOT EXISTS eventos (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    objeto_id INTEGER NOT NULL REFERENCES objetos(id) ON DELETE CASCADE,
    ts        REAL NOT NULL,
    tipo      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_objetos_sesion ON objetos (sesion_id);
CREATE INDEX IF NOT EXISTS idx_objetos_clase  ON objetos (clase);
CREATE INDEX IF NOT EXISTS idx_eventos_objeto ON eventos (objeto_id);
"""


class Database:
    """Acceso a la base. Usar siempre desde el hilo principal."""

    def __init__(self, path: str = DEFAULT_DB_PATH):
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(ESQUEMA)
        self.conn.commit()

    def cerrar(self) -> None:
        try:
            self.conn.commit()
        finally:
            self.conn.close()

    # --- categorias ---------------------------------------------------

    def listar_categorias(self) -> list[dict]:
        filas = self.conn.execute(
            "SELECT id, nombre, color FROM categorias ORDER BY id"
        ).fetchall()
        return [dict(f) for f in filas]

    def crear_categoria(self, nombre: str, color: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO categorias (nombre, color) VALUES (?, ?)",
            (nombre.strip(), color),
        )
        self.conn.commit()
        return cur.lastrowid

    def actualizar_categoria(self, cat_id: int, nombre: str, color: str) -> None:
        self.conn.execute(
            "UPDATE categorias SET nombre = ?, color = ? WHERE id = ?",
            (nombre.strip(), color, cat_id),
        )
        self.conn.commit()

    def eliminar_categoria(self, cat_id: int) -> None:
        """Borra la categoria. El mapeo de clases se va con ella (CASCADE)."""
        self.conn.execute("DELETE FROM categorias WHERE id = ?", (cat_id,))
        self.conn.commit()

    # --- mapeo clase -> categoria / etiqueta --------------------------

    def mapa_clases(self) -> dict[str, dict]:
        """`{clase: {"categoria": nombre, "categoria_id": int, "etiqueta": str}}`."""
        filas = self.conn.execute(
            """
            SELECT cc.clase, cc.etiqueta, cc.categoria_id, c.nombre AS categoria
            FROM clase_categoria AS cc
            LEFT JOIN categorias AS c ON c.id = cc.categoria_id
            """
        ).fetchall()
        return {
            f["clase"]: {
                "categoria": f["categoria"] or "Otros",
                "categoria_id": f["categoria_id"],
                "etiqueta": f["etiqueta"] or "",
            }
            for f in filas
        }

    def asignar_clase(self, clase: str, categoria_id: int | None, etiqueta: str) -> None:
        """Define la categoria y el nombre visible de una clase de COCO."""
        self.conn.execute(
            """
            INSERT INTO clase_categoria (clase, categoria_id, etiqueta)
            VALUES (?, ?, ?)
            ON CONFLICT(clase) DO UPDATE SET
                categoria_id = excluded.categoria_id,
                etiqueta = excluded.etiqueta
            """,
            (clase, categoria_id, etiqueta.strip()),
        )
        self.conn.commit()

    # --- sesiones -----------------------------------------------------

    def abrir_sesion(self, fuente: str, inicio: float | None = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO sesiones (inicio, fuente) VALUES (?, ?)",
            (inicio if inicio is not None else time.time(), str(fuente)),
        )
        self.conn.commit()
        return cur.lastrowid

    def cerrar_sesion(self, sesion_id: int, fin: float | None = None) -> None:
        self.conn.execute(
            "UPDATE sesiones SET fin = ? WHERE id = ?",
            (fin if fin is not None else time.time(), sesion_id),
        )
        self.conn.commit()

    def listar_sesiones(self) -> list[dict]:
        filas = self.conn.execute(
            "SELECT * FROM sesiones ORDER BY inicio DESC"
        ).fetchall()
        return [dict(f) for f in filas]

    # --- objetos ------------------------------------------------------

    def registrar_objeto(
        self,
        sesion_id: int,
        track_id: int,
        clase: str,
        etiqueta: str,
        categoria_id: int | None,
        confianza: float,
        ts: float,
    ) -> int:
        """Da de alta un objeto nuevo en la sesion. Devuelve su `id` (numero visible)."""
        cur = self.conn.execute(
            """
            INSERT INTO objetos (sesion_id, track_id, clase, etiqueta, categoria_id,
                                 confianza_max, detecciones, primera_deteccion,
                                 ultima_deteccion)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT (sesion_id, track_id) DO NOTHING
            """,
            (sesion_id, track_id, clase, etiqueta, categoria_id,
             confianza, ts, ts),
        )
        if cur.lastrowid:
            self.conn.commit()
            return cur.lastrowid
        fila = self.conn.execute(
            "SELECT id FROM objetos WHERE sesion_id = ? AND track_id = ?",
            (sesion_id, track_id),
        ).fetchone()
        return fila["id"] if fila else 0

    def actualizar_objeto(self, objeto_id: int, confianza: float, ts: float,
                          cantidad: int = 1) -> None:
        """Suma `cantidad` detecciones al objeto y le actualiza confianza y ultima vez.

        `cantidad` permite acumular de un tirón todos los fotogramas que pasaron
        desde la ultima actualizacion: el hilo de deteccion va mas rapido que la
        UI, asi que se le pasa el delta en vez de sumar de a uno.
        """
        if cantidad <= 0:
            return
        self.conn.execute(
            """
            UPDATE objetos
               SET detecciones = detecciones + ?,
                   confianza_max = MAX(confianza_max, ?),
                   ultima_deteccion = ?
             WHERE id = ?
            """,
            (cantidad, confianza, ts, objeto_id),
        )
        self.conn.commit()

    def objeto_por_track(self, sesion_id: int, track_id: int) -> dict | None:
        fila = self.conn.execute(
            "SELECT * FROM objetos WHERE sesion_id = ? AND track_id = ?",
            (sesion_id, track_id),
        ).fetchone()
        return dict(fila) if fila else None

    def listar_objetos_sesion(self, sesion_id: int) -> list[dict]:
        filas = self.conn.execute(
            """
            SELECT o.*, c.color AS color, c.nombre AS categoria
            FROM objetos AS o
            LEFT JOIN categorias AS c ON c.id = o.categoria_id
            WHERE o.sesion_id = ?
            ORDER BY o.id
            """,
            (sesion_id,),
        ).fetchall()
        return [dict(f) for f in filas]

    def ultima_aparicion_antes(self, clase: str, ts: float) -> dict | None:
        """Ultimo objeto de esa clase visto *anteriormente*. Base del "ya lo habia visto"."""
        fila = self.conn.execute(
            """
            SELECT o.*, c.color AS color, c.nombre AS categoria
            FROM objetos AS o
            LEFT JOIN categorias AS c ON c.id = o.categoria_id
            WHERE o.clase = ? AND o.primera_deteccion < ?
            ORDER BY o.primera_deteccion DESC
            LIMIT 1
            """,
            (clase, ts),
        ).fetchone()
        return dict(fila) if fila else None

    def veces_vista(self, clase: str, hasta: float | None = None) -> int:
        """Cuantas veces se registro esa clase (en esta sesion si se pasa `hasta`)."""
        if hasta is None:
            cur = self.conn.execute(
                "SELECT COUNT(*) AS n FROM objetos WHERE clase = ?", (clase,)
            )
        else:
            cur = self.conn.execute(
                "SELECT COUNT(*) AS n FROM objetos WHERE clase = ? AND primera_deteccion < ?",
                (clase, hasta),
            )
        return cur.fetchone()["n"]

    def listar_historial(
        self,
        categoria_id: int | None = None,
        texto: str = "",
        desde: float | None = None,
        hasta: float | None = None,
        limite: int = 1000,
    ) -> list[dict]:
        sql = [
            """
            SELECT o.*, c.color AS color, c.nombre AS categoria,
                   s.inicio AS sesion_inicio, s.fuente AS fuente
            FROM objetos AS o
            LEFT JOIN categorias AS c ON c.id = o.categoria_id
            LEFT JOIN sesiones  AS s ON s.id = o.sesion_id
            WHERE 1 = 1
            """
        ]
        params: list = []
        if categoria_id is not None:
            sql.append("AND o.categoria_id = ?")
            params.append(categoria_id)
        if texto.strip():
            sql.append("AND (o.clase LIKE ? OR o.etiqueta LIKE ?)")
            patron = f"%{texto.strip()}%"
            params.extend([patron, patron])
        if desde is not None:
            sql.append("AND o.primera_deteccion >= ?")
            params.append(desde)
        if hasta is not None:
            sql.append("AND o.primera_deteccion <= ?")
            params.append(hasta)
        sql.append("ORDER BY o.primera_deteccion DESC LIMIT ?")
        params.append(limite)
        filas = self.conn.execute(" ".join(sql), params).fetchall()
        return [dict(f) for f in filas]

    def registrar_evento(self, objeto_id: int, ts: float, tipo: str) -> None:
        self.conn.execute(
            "INSERT INTO eventos (objeto_id, ts, tipo) VALUES (?, ?, ?)",
            (objeto_id, ts, tipo),
        )
        self.conn.commit()

    def eventos_de(self, objeto_id: int) -> list[dict]:
        filas = self.conn.execute(
            "SELECT * FROM eventos WHERE objeto_id = ? ORDER BY ts", (objeto_id,)
        ).fetchall()
        return [dict(f) for f in filas]

    # --- mantenimiento ------------------------------------------------

    def vaciar_historial(self) -> None:
        """Borra sesiones, objetos y eventos. **Conserva categorias y mapeos.**"""
        with self.conn:
            self.conn.execute("DELETE FROM eventos")
            self.conn.execute("DELETE FROM objetos")
            self.conn.execute("DELETE FROM sesiones")

    def resumen(self) -> dict:
        """Cifras para la barra de estado."""
        def uno(sql: str) -> int:
            return self.conn.execute(sql).fetchone()[0]

        return {
            "categorias": uno("SELECT COUNT(*) FROM categorias"),
            "objetos": uno("SELECT COUNT(*) FROM objetos"),
            "sesiones": uno("SELECT COUNT(*) FROM sesiones"),
        }

    # --- arranque -----------------------------------------------------

    def asegurar_datos_iniciales(self, clases: list[str] | None = None) -> None:
        """Crea las categorias y el mapeo por defecto la primera vez."""
        if clases is None:
            clases = categorias.leer_clases()

        existentes = {c["nombre"] for c in self.listar_categorias()}
        for cat in categorias.CATEGORIAS_INICIALES:
            if cat["nombre"] not in existentes:
                self.crear_categoria(cat["nombre"], cat["color"])

        ids = {c["nombre"]: c["id"] for c in self.listar_categorias()}
        mapa = self.mapa_clases()
        semilla = categorias.semilla_mapa(clases)

        faltantes = []
        for clase, datos in semilla.items():
            actual = mapa.get(clase)
            cat_id = ids.get(datos["categoria"], ids.get("Otros"))
            if actual is None:
                faltantes.append((clase, cat_id, datos["etiqueta"]))
            elif actual["categoria_id"] != cat_id or actual["etiqueta"] != datos["etiqueta"]:
                # el usuario habia movido la clase a otra categoria: no pisar
                continue
        if faltantes:
            self.conn.executemany(
                """
                INSERT INTO clase_categoria (clase, categoria_id, etiqueta)
                VALUES (?, ?, ?)
                ON CONFLICT(clase) DO NOTHING
                """,
                faltantes,
            )
            self.conn.commit()