# AGENTS.md

Python desktop app for real-time object detection with YOLOv4 via OpenCV DNN. Two entry points share the same detection core: `app.py` (PySide6 GUI, the recommended one) and `detector.py` (original OpenCV `cv2.imshow` CLI). No build system, no CI.

## Setup

- Deps are declared in `requirements.txt`: `opencv-python`, `numpy`, `PySide6`. Install with `python -m pip install -r requirements.txt`.
- Install **`opencv-python`, not `opencv-python-headless`**. Both entry points open a window; headless has no GUI backend.
- **PySide6 is only needed for `app.py`.** `detector.py` and `python app.py --self-test` must keep working without it, so Qt is imported lazily inside `main()`, never at module top level.
- `yolov4.weights` (~250 MB) is **gitignored** but required at runtime. Never commit it and never assume it exists — `load_yolo` calls `check_file` and exits if missing.
- `detector.db` and `*.db` are gitignored. The SQLite file is created on first run.
- Model path defaults resolve against `SCRIPT_DIR`, not the CWD, so both entry points work from any directory for `--weights/--cfg/--names`.

## Commands

```bash
python app.py                                     # GUI, camera 0
python app.py --source video.mp4                  # GUI on a video file
python app.py --conf 0.6 --nms 0.3                # thresholds, both in (0, 1]
python detector.py                                # original CLI, camera 0
python detector.py --source 1 --cuda
```

- `--source` is parsed by `detector.parse_source`: all-digit becomes an **int camera index**, anything else stays a **string path**. A video named e.g. `2024` is misparsed as camera 2024.
- `--source` paths are resolved by `cv2.VideoCapture` against the **current working directory**, unlike model paths. This asymmetry is easy to get wrong.
- `parse_source` and `unit_range` live in `detector.py` and are re-exported by `app.py`. Do not re-implement them; duplicate validation drifts.
- `--cuda` sets `DNN_TARGET_CUDA_FP16` and only works with an OpenCV build compiled for CUDA. CPU is the default and correct for most setups.
- `app.py` adds `--db` for the SQLite path.

## Verification

There is no pytest suite, linter, formatter, or type checker, and adding one is out of scope unless asked.

```bash
python -m compileall -q app.py detector.py tracker.py categorias.py database.py ui
python app.py --self-test        # categorias, tracker, SQLite. No camera, no Qt.
python app.py --self-test-ui     # also builds the window offscreen, saves a PNG
python detector.py --help        # cheapest CLI smoke check
```

- `--self-test-ui` sets `QT_QPA_PLATFORM=offscreen` **before** constructing `QApplication`, seeds a temp DB, injects synthetic detections and asserts row counts. It writes `%TEMP%\ui_smoke.png`.
- Real detection needs a webcam or video file plus a GUI session. It cannot be verified headlessly; say so rather than claiming the detector was tested.
- `detector.py` guards the OpenCV import with a friendly message and `SystemExit(1)`; keep that guard.

## Architecture

- `detector.py` — model loading, `detect_objects`, and `dibujar_objetos(frame, objetos, escala)`. `objetos` is a list of dicts with `caja` (`[x, y, w, h]`), `texto`, `subtexto` and `color` (BGR tuple). The GUI reuses this so drawing logic is not duplicated.
- `ui/worker.py` — `ConfigDeteccion` dataclass and `DetectorWorker(QThread)`. **The worker never touches widgets or SQLite.** It only reads config, runs inference, and emits signals: `frame_listo`, `objetos_actualizados`, `log`, `error`, `metricas`, `terminado`.
- `ui/app_window.py` — `MainWindow` owns all widgets, timers and DB writes. `ejecutar_app(args)` and `autocomprobacion_ui(args)` are the entry points called from `app.py`.
- `tracker.py` — `IoUTracker.update(detecciones, timestamp)`. Emits `nueva`, `reaparecida`, `desaparecida` flags and a monotonic `frames` counter.
- `categorias.py` — 5 seed categories, per-class aliases, `hex_a_bgr` / `hex_a_rgb` (RGB is stored, OpenCV draws in BGR).
- `database.py` — `Database` class; every method is wrapped by `_conexion()` so `check_same_thread=False` is safe for reads from the GUI thread. Do not cache `self.conn` across calls.
- `ui/formato.py` — timestamps and duration formatting. All DB timestamps are `REAL` epoch seconds.

## Threading rules

These are the easiest things to break:

- All SQLite writes and **all widget access happen in the GUI thread**. The worker emits data; `MainWindow` persists it.
- `objetos_actualizados` fires on a timer (~0.2 s) but `frames` increases every frame. Persist with a **delta** (`frames - frames_ya_guardados`), not with the raw counter, or detection counts explode.
- Call `worker.wait()` before destroying the `QThread`, or the process aborts. `closeEvent` must stop and wait.
- `VisorVideo` keeps a reference to the frame buffer it converts to `QImage`; without it the array is freed and the display goes blank.

## Code conventions and gotchas

- Class labels come from `coco.names` **by line index** (`classes[class_id]`). Reordering or inserting lines silently corrupts every label. Keep the file exactly as shipped.
- `draw_labels` in `detector.py` hardcodes an animal color set (`cat, dog, bird, horse, sheep, cow, elephant, bear, zebra, giraffe`) and mutates the frame in place. It is legacy for the CLI only; the GUI uses `dibujar_objetos` with DB colors.
- The `try/except (IndexError, TypeError)` around `getUnconnectedOutLayers()` normalizes OpenCV's two return shapes. Do not remove it as dead code.
- Model input is hardcoded to 416x416, scale `1/255.0`, `swapRB=True`. Changing input size means changing `yolov4.cfg` too.
- `track_id` is **only stable within a session**. The history stores class/alias, not physical identity across sessions.
- Deleting a category cascades its class mappings and leaves `objetos.categoria_id` as `NULL`. `vaciar_historial()` deliberately keeps categories and mappings.
- `Database.mapa_clases()` returns no color; `ui/app_window.py` joins it with `listar_categorias()` to build the full display map.
- Avoid the PySide6 enum pitfall: `self.etiqueta.sizePolicy().Expanding` raises `AttributeError`. Use `QSizePolicy.Policy.Expanding`.
- User-facing output and `README.md` are **Spanish (Rioplatense — "Probá", "Presioná")**. Match that in print statements, `argparse` help, banners and docs.
- In PowerShell, redirect native output with `2>&1` or stderr surfaces as a `NativeCommandError` record instead of failing the command.

## Scope

- Out of scope unless explicitly requested: saving annotated video, exporting to CSV, or adding a video-output flag. The README states these do not exist.
