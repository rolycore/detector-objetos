"""App de deteccion de objetos con categorias, alias e historial.

Ejemplos:
  python app.py                            # camara 0, config por defecto
  python app.py --source video.mp4          # detecta sobre un archivo de video
  python app.py --conf 0.6 --nms 0.3        # ajusta umbrales
  python app.py --self-test                # comprueba base, tracker y categorias
"""

from __future__ import annotations

import argparse
import os
import sys

import detector
from database import DEFAULT_DB_PATH, Database

# Se reusan las mismas validaciones que el CLI de detector.py para que
# ambas entradas acepten exactamente los mismos valores.
parse_source = detector.parse_source
unit_range = detector.unit_range

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_WEIGHTS = os.path.join(SCRIPT_DIR, "yolov4.weights")
DEFAULT_CFG = os.path.join(SCRIPT_DIR, "yolov4.cfg")
DEFAULT_NAMES = os.path.join(SCRIPT_DIR, "coco.names")


# --- autocomprobacion -------------------------------------------------

class AutocomprobacionFallida(Exception):
    pass


def _verificar(condicion: bool, mensaje: str) -> None:
    if not condicion:
        raise AutocomprobacionFallida(mensaje)


def _probar_categorias() -> None:
    import categorias

    clases = categorias.leer_clases()
    _verificar(len(clases) == 80, f"se esperaban 80 clases, hay {len(clases)}")
    _verificar(clases[0] == "person", f"la clase 0 deberia ser 'person', es {clases[0]!r}")

    _verificar(categorias.hex_a_bgr("#22C55E") == (94, 197, 34),
               "hex_a_bgr no convierte bien #22C55E")
    _verificar(categorias.hex_a_bgr("#fff") == (255, 255, 255),
               "hex_a_bgr no soporta la forma corta")
    _verificar(categorias.hex_a_rgb("#3B82F6") == (59, 130, 246),
               "hex_a_rgb no convierte bien #3B82F6")
    print("  [ok] categorias: 80 clases de COCO, conversion de color")


def _probar_tracker() -> None:
    from tracker import IoUTracker, iou

    # IoU basica: dos cajas identicas -> 1.0 ; separadas -> 0.0
    _verificar(abs(iou([0, 0, 10, 10], [0, 0, 10, 10]) - 1.0) < 1e-9,
               "IoU de cajas identicas deberia ser 1.0")
    _verificar(iou([0, 0, 10, 10], [100, 100, 10, 10]) == 0.0,
               "IoU de cajas separadas deberia ser 0.0")

    t = IoUTracker(umbral_iou=0.3, max_perdidos=3)

    # 1) primer fotograma: el objeto es nuevo
    r = t.update([([0, 0, 100, 100], "dog", 0.9)], 100.0)
    _verificar(len(r) == 1 and r[0].nueva, "la primera deteccion deberia ser nueva")
    _verificar(r[0].track_id == 1, f"el primer track deberia ser 1, es {r[0].track_id}")

    # 2) mismo objeto movido un poco -> mismo ID, no es nueva
    r = t.update([([10, 10, 100, 100], "dog", 0.8)], 101.0)
    _verificar(r[0].track_id == 1, "el objeto movido deberia conservar su ID")
    _verificar(not r[0].nueva, "un objeto ya visto no deberia marcarse como nuevo")
    _verificar(not r[0].reaparecida, "un objeto visto el fotograma anterior no reaparece")

    # 3) una clase distinta encima del mismo lugar -> ID aparte
    r = t.update([([0, 0, 100, 100], "person", 0.95)], 102.0)
    _verificar(r[0].track_id == 2, "otra clase en el mismo lugar debe ser otro objeto")
    _verificar(r[0].nueva, "la persona deberia ser un objeto nuevo")

    # 4) se pierde un fotograma y vuelve -> reaparecida
    r = t.update([], 103.0)
    _verificar(not r, "un fotograma sin detecciones no deberia emitir nada")
    r = t.update([([10, 10, 100, 100], "dog", 0.85)], 104.0)
    _verificar(r[0].track_id == 1, "tras un frame perdido deberia recuperar el ID 1")
    _verificar(r[0].reaparecida, "el objeto que volvio deberia marcar reaparecida")
    _verificar(not r[0].nueva, "reaparecer no es ser nuevo")

    # 5) desaparecer de verdad tras max_perdidos
    for ts in (105.0, 106.0, 107.0):
        r = t.update([([900, 900, 50, 50], "cat", 0.5)], ts)
    _verificar(r[-1].desaparecida,
               "tras max_perdidos frames deberia avisar que el objeto desaparecio")
    _verificar(r[-1].track_id == 1, "el que desaparece es el perro, no el gato")

    # 6) reiniciar olvida todo
    t.reiniciar()
    _verificar(t.siguiente_id_disponible == 1,
               "reiniciar deberia reiniciar la numeracion de IDs")

    # 7) dos objetos identicos en el mismo lugar toman IDs distintos
    t2 = IoUTracker()
    r = t2.update([([0, 0, 50, 50], "dog", 0.9), ([0, 0, 50, 50], "dog", 0.9)], 1.0)
    _verificar(r[0].track_id != r[1].track_id,
               "dos detecciones identicas deben recibir IDs distintos")
    print("  [ok] tracker: IDs estables, reapariciones, clase y desaparición")


def _probar_base() -> None:
    import tempfile

    import categorias

    with tempfile.TemporaryDirectory() as tmp:
        ruta = os.path.join(tmp, "prueba.db")
        db = Database(ruta)
        try:
            db.asegurar_datos_iniciales()
            resumen = db.resumen()
            _verificar(resumen["categorias"] == 5,
                       f"deberian crearse 5 categorias, hay {resumen['categorias']}")
            mapa = db.mapa_clases()
            _verificar(len(mapa) == 80, f"deberian mapearse 80 clases, hay {len(mapa)}")
            _verificar(mapa["person"]["categoria"] == "Personas",
                       "la clase 'person' deberia ir a Personas")
            _verificar(mapa["dog"]["categoria"] == "Animales",
                       "la clase 'dog' deberia ir a Animales")
            _verificar(mapa["car"]["categoria"] == "Vehiculos",
                       "la clase 'car' deberia ir a Vehiculos")
            _verificar(mapa["laptop"]["categoria"] == "Objetos",
                       "la clase 'laptop' deberia ir a Objetos")

            # alias + color propio
            ids = {c["nombre"]: c["id"] for c in db.listar_categorias()}
            db.asignar_clase("dog", ids["Animales"], "Perro")
            db.crear_categoria("Mascotas", "#FF00FF")
            ids = {c["nombre"]: c["id"] for c in db.listar_categorias()}
            db.asignar_clase("cat", ids["Mascotas"], "Gato")
            mapa = db.mapa_clases()
            _verificar(mapa["dog"]["etiqueta"] == "Perro", "el alias de 'dog' no se guardo")
            _verificar(mapa["cat"]["categoria"] == "Mascotas",
                       "la categoria nueva de 'cat' no se guardo")

            # sesión + objetos
            sesion = db.abrir_sesion("camara 0", inicio=1000.0)
            obj = db.registrar_objeto(sesion, 1, "dog", "Perro",
                                      ids["Animales"], 0.9, 1000.0)
            _verificar(obj > 0, "no se pudo registrar el objeto")
            db.actualizar_objeto(obj, 0.95, 1002.0)
            db.registrar_evento(obj, 1000.0, "nuevo")

            fila = db.objeto_por_track(sesion, 1)
            _verificar(fila["detecciones"] == 2,
                       f"deberia tener 2 detecciones, tiene {fila['detecciones']}")
            _verificar(abs(fila["confianza_max"] - 0.95) < 1e-9,
                       "confianza_max deberia guardar el maximo (0.95)")

            # ¿ya lo habia visto antes? (otra sesión, mismo objeto)
            sesion2 = db.abrir_sesion("video.mp4", inicio=2000.0)
            db.registrar_objeto(sesion2, 1, "dog", "Perro",
                                ids["Animales"], 0.7, 2000.0)
            anterior = db.ultima_aparicion_antes("dog", 2000.0)
            _verificar(anterior is not None, "no encontro la aparicion anterior")
            _verificar(anterior["primera_deteccion"] == 1000.0,
                       "la aparicion anterior deberia ser la de la sesion 1")
            _verificar(db.veces_vista("dog", 2000.0) == 1,
                       "deberia contar 1 aparicion previa de 'dog'")

            # historial con filtros
            _verificar(len(db.listar_historial()) == 2, "el historial deberia tener 2 filas")
            _verificar(len(db.listar_historial(texto="perro")) == 2,
                       "la busqueda por texto deberia encontrar ambos perros")
            _verificar(len(db.listar_historial(texto="gato")) == 0,
                       "la busqueda 'gato' no deberia encontrar perros")
            _verificar(len(db.listar_historial(categoria_id=ids["Mascotas"])) == 0,
                       "el filtro por categoria deberia excluir objetos sin asignar")
            _verificar(len(db.listar_historial(desde=1500.0)) == 1,
                       "el filtro por fecha deberia devolver solo la sesion 2")

            db.cerrar_sesion(sesion2, fin=2001.0)
            _verificar(len(db.listar_sesiones()) == 2, "deberian existir 2 sesiones")

            # vaciar historial conserva la configuración
            db.vaciar_historial()
            resumen = db.resumen()
            _verificar(resumen["objetos"] == 0 and resumen["sesiones"] == 0,
                       "vaciar historial deberia borrar objetos y sesiones")
            _verificar(resumen["categorias"] == 6,
                       "vaciar historial NO debe borrar las categorias")
            _verificar(len(db.mapa_clases()) == 80,
                       "vaciar historial NO debe borrar el mapeo de clases")
        finally:
            db.cerrar()
    print("  [ok] base de datos: esquema, categorias, alias, historial y filtros")


def ejecutar_autocomprobacion() -> int:
    print("[AUTOCOMPROBACION] detector objetos - sin camara, sin interfaz")
    try:
        _probar_categorias()
        _probar_tracker()
        _probar_base()
    except AutocomprobacionFallida as exc:
        print(f"  [FALLO] {exc}")
        print("[AUTOCOMPROBACION] Resultado: FALLA")
        return 1
    except Exception as exc:  # noqa: BLE001 - queremos ver cualquier error
        print(f"  [FALLO] error inesperado: {type(exc).__name__}: {exc}")
        print("[AUTOCOMPROBACION] Resultado: FALLA")
        return 1
    print("[AUTOCOMPROBACION] Resultado: OK")
    return 0


# --- interfaz --------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Detector de objetos con categorias, alias e historial",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Ejemplos:
  python app.py                            # camara 0 y configuracion por defecto
  python app.py --source video.mp4          # detecta sobre un archivo de video
  python app.py --conf 0.6 --nms 0.3        # ajusta umbrales
  python app.py --self-test                # comprueba base, tracker y categorias
  python app.py --self-test-ui             # comprueba la ventana sin camara
""",
    )
    parser.add_argument("--source", default="0", type=parse_source,
                        help="Indice de camara o ruta de video (default: 0)")
    parser.add_argument("--conf", type=unit_range, default=0.5,
                        help="Umbral de confianza, entre 0 y 1 (default: 0.5)")
    parser.add_argument("--nms", type=unit_range, default=0.4,
                        help="Umbral de NMS, entre 0 y 1 (default: 0.4)")
    parser.add_argument("--weights", default=DEFAULT_WEIGHTS,
                        help=f"Ruta a yolov4.weights (default: {DEFAULT_WEIGHTS})")
    parser.add_argument("--cfg", default=DEFAULT_CFG,
                        help=f"Ruta a yolov4.cfg (default: {DEFAULT_CFG})")
    parser.add_argument("--names", default=DEFAULT_NAMES,
                        help=f"Ruta a coco.names (default: {DEFAULT_NAMES})")
    parser.add_argument("--db", default=DEFAULT_DB_PATH,
                        help=f"Ruta de la base de datos (default: {DEFAULT_DB_PATH})")
    parser.add_argument("--cuda", action="store_true",
                        help="Usar backend CUDA (si disponible)")
    parser.add_argument("--self-test", action="store_true",
                        help="Ejecutar comprobaciones internas y salir")
    parser.add_argument("--self-test-ui", action="store_true",
                        help="Armar la ventana sin camara (offscreen) y salir")
    args = parser.parse_args(argv)

    if args.self_test:
        return ejecutar_autocomprobacion()

    try:
        if args.self_test_ui:
            from ui.app_window import autocomprobacion_ui
        else:
            from ui.app_window import ejecutar_app
    except ImportError as exc:
        print(f"[ERROR] No se pudo cargar la interfaz: {exc}")
        print("        Instala PySide6 con: python -m pip install -r requirements.txt")
        return 1

    if args.self_test_ui:
        return autocomprobacion_ui(args)
    return ejecutar_app(args)


if __name__ == "__main__":
    sys.exit(main())