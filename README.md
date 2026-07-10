# Robot Teleop Cans — JetAuto Soda-Can Detection & Pickup

Project plan from brainstorming session (2026-07-09). Goal: extend the existing
JetAuto teleop GUI so that while **I drive manually**, the app **detects soda
cans on the live camera feed, identifies which soda it is**, and — when a can
is inside the arm's reach zone — enables a **Grab button** that locks movement
and picks up the can with the arm.

Explicitly **not** in scope: autonomous driving/navigation. The human is the
navigation system.

---

## Hardware / robot facts

- **Robot:** Hiwonder JetAuto — Jetson Nano onboard, ROS, mecanum wheels (can strafe)
- **Arm:** 5 servos + gripper — IDs `1` (base rotate), `2` (shoulder), `3` (elbow),
  `4` (wrist pitch), `5` (gripper rotation), `10` (grip)
- **Camera:** depth cam, RGB topic `/depth_cam/rgb/image_raw`, MJPEG via
  web_video_server on port `8080`
- **Comms:** rosbridge websocket on port `9090`; robot reached over Tailscale at
  `100.82.122.19`
- **Topics used:** `/cmd_vel` (geometry_msgs/Twist),
  `/ros_robot_controller/bus_servo/set_position` (ros_robot_controller_msgs/ServosPosition)
- **Training PC:** Windows, RTX 3080 10 GB (plenty for local YOLO training),
  Python 3.13 default / 3.12 available

Existing code: `jetauto_teleop.py` (copied into this folder from Downloads) —
tkinter GUI with virtual joystick, WASD keys, servo sliders, live MJPEG view,
10 Hz cmd_vel publish loop. It already solves the plumbing: frames in,
commands out. The project evolves this script rather than starting over.

---

## Architecture decisions (agreed)

| Question | Decision |
|---|---|
| What model? | YOLO nano (e.g. `yolo11n`) — a CNN object detector; one model does detection **and** brand ID via multi-class training (`coke`, `pepsi`, `sprite`, ...) |
| Training data? | **No manual collection.** Use a pre-labeled soda-can dataset from Roboflow Universe (YOLO export format). Accept some accuracy loss from viewpoint mismatch; patch later with 30–50 own photos only if needed |
| Where does training run? | **This PC** (RTX 3080), in a venv. ~15–30 min per run |
| Where does the model file live? | On the PC, loaded by the app; inference runs PC-side against the MJPEG stream. Moving onto the Jetson (TensorRT export) is optional later polish |
| How does the grab work? | No inverse kinematics. A fixed **target zone** rectangle drawn on the camera feed = arm's reach envelope. Drive until the can's box sits in the zone (steady ~1 s) → Grab button enables → movement locks (zero cmd_vel, inputs ignored) → replay a **pre-recorded servo pose sequence** (reach → open → close → lift) → unlock. Abort button freezes the arm |
| Pose sequences | Recorded by hand using the existing servo sliders; stored as JSON (list of {servo: position} poses + timings) in `poses\` — data, not code |
| Known hard case | Coke vs Diet/Zero from the back of the can. Fallback: merge into one `coke` class. Backup oracle: send the cropped box to a vision-LLM API on demand for exact brand |
| Depth camera | Optional polish only (e.g. sanity-check grab distance) |

---

## Target folder layout

```
Robot_Teleop_Cans\
├── .venv\                  <- Python env (gitignored)
├── requirements.txt
├── README.md               <- this file
├── app\
│   ├── teleop.py           <- evolved from jetauto_teleop.py
│   ├── detector.py         <- thin YOLO wrapper (load model, frame -> boxes)
│   ├── grab.py             <- pose recording/replay + movement lock
│   └── config.py           <- robot IP, topics, model path, target-zone coords
├── training\
│   ├── dataset\            <- unzipped Roboflow download (gitignored)
│   └── runs\               <- YOLO training output (gitignored)
├── models\
│   └── cans_v1.pt          <- hand-promoted "known good" models, versioned
└── poses\
    └── grab_floor_can.json <- recorded arm sequences
```

Key idea: `models\` is the handoff point — training produces `best.pt` deep in
`runs\`; only copy it to `models\cans_vN.pt` when it beats the previous one.
The app points at `models\` via `config.py`, so rollback = edit one path.

---

## Environment setup (one-time)

```powershell
cd $HOME\Desktop\Robot_Teleop_Cans
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126
pip install ultralytics websocket-client pillow
python -c "import torch; print(torch.cuda.is_available())"   # MUST print True
```

If that last line prints `False`, the CPU-only PyTorch got installed and
training would take hours — reinstall torch with the cu126 index URL.

---

## Training workflow

1. Download a soda-can dataset from Roboflow Universe ("YOLO" export), unzip
   into `training\dataset\`. Open its `data.yaml` once — check class names,
   fix folder paths if needed.
2. Train (venv active):
   `yolo train model=yolo11n.pt data=training\dataset\data.yaml epochs=100 imgsz=640`
3. Eyeball results:
   `yolo predict model=<path to best.pt> source=training\dataset\test\images`
   and flip through the annotated images it saves.
4. Good enough → copy `best.pt` to `models\cans_v1.pt`.
5. Retrain only when the model disappoints (different dataset, merged classes,
   or a small folder of patch photos of the failure cases).

Inference in the app is ~3 lines:

```python
from ultralytics import YOLO
model = YOLO("models/cans_v1.pt")
results = model(frame)   # frame = the JPEG the teleop script already decodes
```

---

## Phased plan

1. **Scaffold** — folder tree above, venv, git init (`.gitignore`: `.venv/`,
   `training/dataset/`, `training/runs/`), copy teleop script into `app\`.
2. **Model v1** — Roboflow dataset → local training → `models\cans_v1.pt`.
3. **Live overlay** — YOLO boxes + brand + confidence drawn on the camera feed
   in the GUI. ("Tells us which soda it is" ✓)
4. **Target zone + Grab button** — fixed rectangle on the feed; can's box
   inside it steady ~1 s → Grab enables.
5. **Grab sequence** — add record/replay buttons; choreograph the pickup with
   the servo sliders over a real can; Grab = lock driving → replay → unlock;
   plus Abort.
6. **Tune** — adjust zone size until "box in zone" reliably means "grab
   succeeds"; patch the model if brand ID misfires.
7. *(Optional later)* — TensorRT export, run inference on the Jetson itself.

## Open items

- Which sodas/brands to recognize (drives dataset choice)
- Pick a specific Roboflow dataset
- SSH into the Jetson at some point to inventory Hiwonder's pre-installed
  packages (their color-block pick demos may be reusable)
