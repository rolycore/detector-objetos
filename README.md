# Detector de objetos con YOLOv4

Aplicación de escritorio en Python que detecta objetos en tiempo real usando la cámara web o procesa un archivo de video. Usa YOLOv4 a través de OpenCV DNN y muestra las detecciones con su nombre, confianza y FPS.

Hay dos programas distintos:

| Programa | Interfaz | Para qué sirve |
| --- | --- | --- |
| `app.py` | PySide6 | La app completa: video embebido, categorías, avisos, objetos en vivo e historial. |
| `detector.py` | OpenCV (`cv2.imshow`) | El CLI liviano que ya conocías. |

## Contenido del proyecto

| Archivo / carpeta | Descripción |
| --- | --- |
| `app.py` | Aplicación gráfica (PySide6). Punto de entrada recomendado. |
| `detector.py` | Detector original con OpenCV puro: dibuja cajas y calcula FPS. |
| `ui/` | Módulos de la interfaz: ventana, worker, visor y paneles. |
| `tracker.py` | Seguimiento de objetos por IoU entre fotogramas. |
| `categorias.py` | Categorías iniciales, alias por clase y conversión de colores. |
| `database.py` | Base de datos SQLite: sesiones, objetos, eventos e historial. |
| `yolov4.cfg` | Configuración de la red YOLOv4. |
| `coco.names` | Nombres de las 80 clases de COCO. |
| `yolov4.weights` | Pesos entrenados del modelo (se descarga a mano). |

## Requisitos

- Python 3.10 o superior.
- Las dependencias de `requirements.txt`.
- Una cámara web para el modo en vivo, o un archivo de video compatible.
- El archivo `yolov4.weights`, además de `yolov4.cfg` y `coco.names`.

> La aceleración CUDA es opcional y requiere una instalación de OpenCV compilada con soporte CUDA, además de hardware y controladores compatibles. Si no tenés esa configuración, ejecutá sin `--cuda`.

## Instalación

### 1. Abrí una terminal en la carpeta del proyecto

```bash
cd ruta/a/detector-objetos
```

En Windows también podés abrir la carpeta en el Explorador, escribir `cmd` en la barra de direcciones y pulsar Enter.

### 2. (Recomendado) Creá un entorno virtual

En Windows (PowerShell):

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

En macOS o Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Si PowerShell bloquea la activación, usá `.\.venv\Scripts\activate.bat` desde `cmd`, o ejecutá Python con `.venv\Scripts\python.exe` sin activar el entorno.

### 3. Instalá las dependencias

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Instalá **`opencv-python`**, no `opencv-python-headless`: la app abre una ventana y la versión headless no trae interfaz gráfica.

### 4. Bajá los pesos del modelo

`yolov4.cfg` y `coco.names` ya están en la carpeta. Bajá los pesos si todavía no los tenés:

[Descargar yolov4.weights](https://github.com/AlexeyAB/darknet/releases/download/darknet_yolo_v4_pre/yolov4.weights)

Guardalo exactamente como `yolov4.weights` en la misma carpeta. Son ~250 MB, así que la descarga puede tardar. También podés guardarlo en otra ruta y pasarla con `--weights`.

Estructura esperada por defecto:

```text
detector-objetos/
├── app.py
├── detector.py
├── ui/
├── yolov4.cfg
├── yolov4.weights
├── coco.names
└── detector.db   # se crea solo en la primera ejecución
```

## La app gráfica (`app.py`)

```bash
python app.py
```

Se abre una ventana con el video y cuatro paneles:

- **Video**: el fotograma anotado en vivo. Cuando aparece un objeto de una categoría que todavía no viste, aparece un aviso arriba con su nombre.
- **Objetos en vivo**: los objetos detectados en la sesión actual, con su categoría, alias, confianza y tiempo visible. El contador *desde* muestra hace cuántos fotogramas apareció cada uno.
- **Historial**: todo lo registrado en sesiones anteriores, con filtros por categoría, texto y rango de fechas. Una sesión es cada vez que apretás **Iniciar**.
- **Barra de estado**: FPS, fotogramas, tiempo transcurrido y cuántos objetos hay en pantalla.

### Opciones de `app.py`

| Opción | Predeterminado | Función |
| --- | --- | --- |
| `--source` | `0` | Índice de cámara o ruta de un video. |
| `--weights` | `yolov4.weights` junto al script | Ruta a los pesos. |
| `--cfg` | `yolov4.cfg` junto al script | Ruta a la configuración del modelo. |
| `--names` | `coco.names` junto al script | Ruta a los nombres de clases. |
| `--conf` | `0.5` | Umbral mínimo de confianza, entre `0` y `1`. |
| `--nms` | `0.4` | Umbral de supresión de cajas superpuestas. |
| `--cuda` | Desactivado | Backend CUDA de OpenCV con objetivo FP16. |

Ejemplos:

```bash
python app.py --source video.mp4
python app.py --source 1
python app.py --conf 0.6 --nms 0.3
```

## Categorías

Las categorías agrupan las 80 clases de COCO y determinan el color con el que se dibuja cada detección. De fábrica hay cinco: **Personas**, **Animales**, **Vehículos**, **Objetos** y **Otros**.

En la pestaña de categorías podés:

- Crear una categoría nueva con su color.
- Editar o borrar una existente.
- Asignar cada clase de COCO a la categoría que quieras.
- Ponerle un **alias** a una clase para que se muestre con otro nombre (por ejemplo, `hot dog` → `pancho`).

Los cambios de color y alias se aplican en vivo, sin reiniciar la detección.

## Historial y base de datos

Todo lo detectado se guarda en `detector.db` (SQLite) en la carpeta del proyecto.

- **Vaciar historial** borra las detecciones pero conserva tus categorías y asignaciones.
- **Borrar** una categoría elimina también las detecciones que estaban en ella.

El archivo `detector.db` está en `.gitignore`. Si querés empezar de cero, borralo y se recrea al abrir la app.

## Autocomprobación

La app incluye dos chequeos que no necesitan cámara ni GPU:

```bash
python app.py --self-test      # categorías, tracker y base de datos
python app.py --self-test-ui   # además levanta la ventana en modo offscreen
```

El segundo guarda una captura de la ventana en la carpeta temporal del sistema para que puedas revisarla.

## El CLI (`detector.py`)

El programa original sigue funcionando igual, sin categorías ni historial:

```bash
python detector.py                  # cámara 0
python detector.py --source 1       # otra cámara
python detector.py --source video.mp4
python detector.py --conf 0.6 --nms 0.3
python detector.py --cuda
```

Abre una ventana de OpenCV con las detecciones. Presioná **q** con la ventana activa para salir, o `Ctrl+C` en la terminal.

En este programa las etiquetas se resaltan así:

- **Verde:** personas.
- **Azul:** animales (gato, perro, pájaro, caballo, oveja, vaca, elefante, oso, cebra, jirafa).
- **Rojo:** el resto.

## Solución de problemas

### No se encuentra `yolov4.weights`

Descargalo y ponelo junto al script, o indicá la ruta con `--weights`. La app avisa el archivo exacto que no encontró.

### Falta `opencv-python` o `PySide6`

Instalá las dependencias en el mismo entorno con el que ejecutás:

```bash
python -m pip install -r requirements.txt
```

### `app.py` no abre la ventana

- Verificá que instalaste `opencv-python` (no la headless).
- Confirmá que estás en un entorno de escritorio con Qt disponible.
- Probá `python app.py --self-test-ui` para ver si la interfaz carga bien.

### No se puede abrir la fuente

- Para una cámara, confirmá que esté conectada y probá otro índice con `--source 1`.
- Para un video, revisá la ruta, el nombre y el códec.
- Cerrá otras aplicaciones que puedan estar usando la cámara.

### Error al activar CUDA

Quitá `--cuda`. La opción solo funciona si tu instalación de OpenCV y tu equipo tienen soporte compatible.

### La detección es lenta

YOLOv4 puede requerir bastante cómputo. El rendimiento depende del procesador, la GPU, OpenCV y la fuente. Probá CUDA si tu instalación lo admite.

## Notas

- `coco.names` se lee **por número de línea**: reordenar o agregar líneas rompe todas las etiquetas.
- No se incluye guardado del video anotado ni exportación a CSV.
- La licencia de este proyecto y de los archivos del modelo debe revisarse según el uso previsto.
