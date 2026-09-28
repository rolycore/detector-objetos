# Detector de objetos con YOLOv4

Aplicación de escritorio en Python que detecta objetos en tiempo real usando la cámara web o procesa un archivo de video. Utiliza YOLOv4 a través de OpenCV DNN y muestra en pantalla las etiquetas, la confianza de cada detección y los FPS.

## Contenido del proyecto

| Archivo | Descripción |
| --- | --- |
| `detector.py` | Programa principal: carga el modelo, obtiene los fotogramas y dibuja las detecciones. |
| `yolov4.cfg` | Configuración de la red YOLOv4. |
| `coco.names` | Nombres de las clases del conjunto COCO. |
| `yolov4.weights` | Pesos entrenados del modelo. El programa espera encontrarlos en esta carpeta por defecto. |

## Requisitos

- Python 3.
- OpenCV con el módulo `dnn` (`opencv-python`).
- NumPy.
- Una cámara web para el modo en vivo, o un archivo de video compatible para procesar un video.
- El archivo `yolov4.weights`, además de `yolov4.cfg` y `coco.names`.

> La aceleración CUDA es opcional y requiere una instalación de OpenCV compilada con soporte CUDA, además de hardware y controladores compatibles. Si no tienes esa configuración, ejecuta el programa sin `--cuda`.

## Instalación y primera ejecución

### 1. Abre una terminal en la carpeta del proyecto

Entra en la carpeta que contiene `detector.py`, `yolov4.cfg` y `coco.names`:

```bash
cd ruta/a/detector-objetos
```

En Windows también puedes abrir la carpeta en el Explorador de archivos, escribir `cmd` o `powershell` en la barra de direcciones y pulsar Enter.

### 2. (Recomendado) Crea un entorno virtual

En Windows:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

En macOS o Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Si PowerShell bloquea la activación, puedes usar `.\.venv\Scripts\activate.bat` desde `cmd`, o ejecutar Python mediante `.venv\Scripts\python.exe` sin activar el entorno.

### 3. Instala las dependencias

```bash
python -m pip install --upgrade pip
python -m pip install opencv-python numpy
```

En sistemas donde el comando de Python sea `python3`, reemplaza `python` por `python3`.

### 4. Comprueba los archivos del modelo

`yolov4.cfg` y `coco.names` deben estar en la carpeta del proyecto. Descarga los pesos oficiales de YOLOv4 si `yolov4.weights` todavía no está allí:

[Descargar yolov4.weights](https://github.com/AlexeyAB/darknet/releases/download/darknet_yolo_v4_pre/yolov4.weights)

Guarda el archivo exactamente como `yolov4.weights` en la misma carpeta. Es un archivo grande, por lo que la descarga puede tardar. También puedes guardarlo en otra ruta y pasarla con `--weights`.

La estructura esperada por defecto es:

```text
detector-objetos/
├── detector.py
├── yolov4.cfg
├── yolov4.weights
└── coco.names
```

### 5. Ejecuta el detector

Para iniciar la cámara predeterminada (índice `0`):

```bash
python detector.py
```

Se abrirá una ventana con el video y las detecciones. Pulsa **q** con la ventana activa para salir. También puedes interrumpir el proceso con `Ctrl+C` en la terminal.

## Uso con videos

Pasa la ruta del video mediante `--source`:

```bash
python detector.py --source video.mp4
```

También se aceptan rutas relativas o absolutas. Si la ruta contiene espacios, escríbela entre comillas:

```bash
python detector.py --source "videos/mi video.mp4"
```

El programa muestra el video anotado en una ventana; no guarda automáticamente un archivo de salida.

## Elegir otra cámara

El valor de `--source` es el índice de la cámara. Si la cámara predeterminada no funciona, prueba con otros índices:

```bash
python detector.py --source 1
```

Puedes probar `2`, etc., según los dispositivos disponibles. Cierra otras aplicaciones que puedan estar usando la cámara.

## Opciones disponibles

| Opción | Valor predeterminado | Función |
| --- | --- | --- |
| `--source` | `0` | Índice de cámara o ruta de un video. |
| `--weights` | `yolov4.weights` junto al script | Ruta al archivo de pesos. |
| `--cfg` | `yolov4.cfg` junto al script | Ruta a la configuración del modelo. |
| `--names` | `coco.names` junto al script | Ruta al archivo de nombres de clases. |
| `--conf` | `0.5` | Umbral mínimo de confianza, entre `0` y `1`. |
| `--nms` | `0.4` | Umbral de supresión de cajas superpuestas, entre `0` y `1`. |
| `--cuda` | Desactivado | Solicita el backend CUDA de OpenCV con objetivo FP16. |

Ejemplos:

```bash
# Subir el umbral de confianza para mostrar menos detecciones
python detector.py --conf 0.6

# Ajustar ambos umbrales
python detector.py --conf 0.6 --nms 0.3

# Usar archivos del modelo en otra ubicación
python detector.py --weights modelos/yolov4.weights --cfg modelos/yolov4.cfg --names modelos/coco.names

# Solicitar CUDA (solo si OpenCV está preparado para CUDA)
python detector.py --source 0 --cuda
```

Los umbrales deben ser mayores que `0` y menores o iguales que `1`. Un valor de confianza más alto filtra detecciones menos seguras. NMS ayuda a eliminar cajas duplicadas; si cambias estos valores, el resultado puede variar.

## Clases y colores

Las etiquetas se leen desde `coco.names`. El programa resalta las detecciones así:

- **Verde:** personas (`person`).
- **Azul:** animales definidos en el script (gato, perro, pájaro, caballo, oveja, vaca, elefante, oso, cebra y jirafa).
- **Rojo:** otras clases.

Cada caja muestra el nombre de la clase y el valor de confianza. El contador de FPS se actualiza periódicamente.

## Solución de problemas

### No se encuentra `yolov4.weights`

Descarga el archivo y colócalo junto a `detector.py`, o indica su ubicación con `--weights`.

### Falta `opencv-python`

Instala las dependencias en el mismo entorno con el que ejecutas el script:

```bash
python -m pip install opencv-python numpy
```

### No se puede abrir la fuente

- Para una cámara, confirma que esté conectada y prueba otro índice con `--source 1`.
- Para un video, revisa la ruta, el nombre y que el formato/códec sea compatible con tu instalación de OpenCV.
- Comprueba que otra aplicación no esté usando la cámara.

### Error al activar CUDA

Quita `--cuda` para ejecutar con CPU. La opción CUDA solo funciona si la instalación de OpenCV y el equipo tienen soporte compatible.

### La detección es lenta

YOLOv4 puede requerir bastante capacidad de cómputo. El rendimiento depende del procesador, la GPU, OpenCV, la resolución de entrada y la fuente. Puedes probar CUDA si tu instalación lo admite.

## Notas

- La entrada de `--source` está pensada para una cámara o un archivo de video.
- El script abre una interfaz gráfica con `cv2.imshow`; requiere un entorno de escritorio.
- No se incluye una función para guardar el video anotado ni para exportar resultados.
- La licencia de este proyecto y de los archivos del modelo debe revisarse según el uso previsto.
