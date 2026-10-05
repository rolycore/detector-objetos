try:
    import cv2
except ImportError:
    print("[ERROR] Falta el paquete 'opencv-python'. Instálalo con:")
    print("        pip install opencv-python")
    raise SystemExit(1)

import numpy as np
import argparse
import time
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_WEIGHTS = os.path.join(SCRIPT_DIR, "yolov4.weights")
DEFAULT_CFG = os.path.join(SCRIPT_DIR, "yolov4.cfg")
DEFAULT_NAMES = os.path.join(SCRIPT_DIR, "coco.names")

# --- UTILS --------------------------------------------------

def check_file(path: str):
    if not os.path.isfile(path):
        print(f"[ERROR] No se encontró el archivo: {path}")
        if path.endswith(".weights"):
            print("        Descarga yolov4.weights desde:")
            print("        https://github.com/AlexeyAB/darknet/releases/download/darknet_yolo_v4_pre/yolov4.weights")
        sys.exit(1)

def load_yolo(weights_path, cfg_path, names_path, use_cuda=False):
    # Verifica archivos
    for p in (weights_path, cfg_path, names_path):
        check_file(p)

    net = cv2.dnn.readNet(weights_path, cfg_path)
    if use_cuda:
        net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
        net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA_FP16)
    layer_names = net.getLayerNames()
    try:
        output_layers = [layer_names[i[0] - 1] for i in net.getUnconnectedOutLayers()]
    except (IndexError, TypeError):
        output_layers = [layer_names[i - 1] for i in net.getUnconnectedOutLayers()]

    # Carga nombres de clases
    with open(names_path, "r") as f:
        classes = [line.strip() for line in f.readlines()]

    return net, classes, output_layers

def detect_objects(frame, net, output_layers, conf_threshold, nms_threshold):
    h, w = frame.shape[:2]
    blob = cv2.dnn.blobFromImage(frame, 1/255.0, (416, 416),
                                 swapRB=True, crop=False)
    net.setInput(blob)
    outs = net.forward(output_layers)

    boxes, confidences, class_ids = [], [], []
    for out in outs:
        for det in out:
            scores = det[5:]
            class_id = int(np.argmax(scores))
            conf = float(scores[class_id])
            if conf > conf_threshold:
                box = det[0:4] * np.array([w, h, w, h])
                cx, cy, bw, bh = box.astype("int")
                x, y = int(cx - bw/2), int(cy - bh/2)
                boxes.append([x, y, int(bw), int(bh)])
                confidences.append(conf)
                class_ids.append(class_id)

    idxs = cv2.dnn.NMSBoxes(boxes, confidences, conf_threshold, nms_threshold)
    return [(boxes[i], class_ids[i], confidences[i]) for i in idxs.flatten()]

def dibujar_objetos(frame, objetos, escala=1.0):
    """Dibuja en el frame los objetos ya armados para mostrar.

    Es la función genérica: la app arma cada objeto con su propio color, su
    nombre visible y la hora de primera detección. `objetos` es una lista de
    diccionarios con:
        {"caja": [x, y, w, h], "texto": str, "subtexto": str, "color": (b, g, r)}
    `escala` agranda la tipografía junto con el tamaño del video.
    """
    grosor = max(2, int(round(2 * escala)))
    fuente = max(0.4, 0.5 * escala)
    for obj in objetos:
        x, y, w, h = obj["caja"]
        color = obj["color"]
        cv2.rectangle(frame, (x, y), (x + w, y + h), color, grosor)

        texto = obj.get("texto", "")
        subtexto = obj.get("subtexto", "")
        # dy arranca arriba de la caja y sube si hay lineas adicionales
        dy = int(round(22 * escala))
        if texto:
            cv2.putText(frame, texto, (x, y - dy), cv2.FONT_HERSHEY_SIMPLEX,
                        fuente, color, grosor)
            dy += int(round(20 * escala))
        if subtexto:
            cv2.putText(frame, subtexto, (x, y - dy), cv2.FONT_HERSHEY_SIMPLEX,
                        fuente * 0.85, color, max(1, grosor - 1))

def draw_labels(frame, detections, classes):
    # Define categoría animales
    animals = {"cat","dog","bird","horse","sheep","cow",
               "elephant","bear","zebra","giraffe"}
    objetos = []
    for (box, class_id, conf) in detections:
        label = classes[class_id]
        # Elige color
        if label == "person":
            color = (0,255,0)
        elif label in animals:
            color = (255,0,0)
        else:
            color = (0,0,255)
        objetos.append({"caja": box, "texto": f"{label}: {conf:.2f}",
                        "subtexto": "", "color": color})
    dibujar_objetos(frame, objetos)

# --- MAIN ---------------------------------------------------

def run(weights, cfg, names, source, conf, nms, use_cuda):
    print("[INFO] Cargando modelo...")
    print(f"       weights: {weights}")
    print(f"       cfg:     {cfg}")
    print(f"       names:   {names}")
    print(f"       backend: {'CUDA' if use_cuda else 'CPU'}")
    net, classes, output_layers = load_yolo(weights, cfg, names, use_cuda)

    print(f"[INFO] Fuente: {source} | conf={conf} | nms={nms}")
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        print(f"[ERROR] No se puede abrir la fuente: {source}")
        if isinstance(source, int) or (isinstance(source, str) and source.isdigit()):
            print("        ¿Índice de cámara incorrecto? Probá con --source 1, --source 2, etc.")
        else:
            print("        Verificá que la ruta del video/imagen exista y el formato sea soportado.")
        return

    print("[INFO] Iniciando detección. Presioná 'q' para salir.")

    fps_start = time.time()
    frame_count = 0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            detections = detect_objects(frame, net, output_layers, conf, nms)
            draw_labels(frame, detections, classes)

            frame_count += 1
            if frame_count >= 10:
                fps_end = time.time()
                fps = frame_count / (fps_end - fps_start)
                fps_start, frame_count = fps_end, 0
            else:
                fps = 0.0

            cv2.putText(frame, f"FPS: {fps:.1f}", (10,30),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,255), 2)
            cv2.imshow("YOLOv4 Object Detection", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    except KeyboardInterrupt:
        print("\n[INFO] Interrumpido por el usuario.")
    finally:
        cap.release()
        cv2.destroyAllWindows()
        print("[INFO] Listo.")

def parse_source(value):
    """Permite pasar un índice de cámara (0, 1, ...) o una ruta de archivo."""
    if value.isdigit():
        return int(value)
    return value

def unit_range(value):
    f = float(value)
    if not (0.0 < f <= 1.0):
        raise argparse.ArgumentTypeError(f"debe estar entre 0 y 1 (recibido: {value})")
    return f

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Detector de objetos con YOLOv4",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Ejemplos:
  python detector.py                          # usa la cámara 0 y los archivos del modelo en esta carpeta
  python detector.py --source video.mp4        # detecta sobre un archivo de video
  python detector.py --source 1 --cuda         # usa la cámara 1 con aceleración CUDA
  python detector.py --conf 0.6 --nms 0.3       # ajusta umbrales de confianza y NMS
""")
    parser.add_argument("--weights", default=DEFAULT_WEIGHTS,
                        help=f"Ruta a yolov4.weights (default: {DEFAULT_WEIGHTS})")
    parser.add_argument("--cfg", default=DEFAULT_CFG,
                        help=f"Ruta a yolov4.cfg (default: {DEFAULT_CFG})")
    parser.add_argument("--names", default=DEFAULT_NAMES,
                        help=f"Ruta a coco.names (default: {DEFAULT_NAMES})")
    parser.add_argument("--source", default=0, type=parse_source,
                        help="Índice de cámara o ruta de video (default: 0)")
    parser.add_argument("--conf", type=unit_range, default=0.5,
                        help="Umbral de confianza, entre 0 y 1 (default: 0.5)")
    parser.add_argument("--nms", type=unit_range, default=0.4,
                        help="Umbral de NMS, entre 0 y 1 (default: 0.4)")
    parser.add_argument("--cuda", action="store_true",
                        help="Usar backend CUDA (si disponible)")
    args = parser.parse_args()

    run(args.weights, args.cfg, args.names,
        args.source, args.conf, args.nms, args.cuda)