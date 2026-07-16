# Robot Teleop — JetAuto Ball Detection & Pickup

Teleop GUI for the Hiwonder JetAuto: while **I drive manually**, the app
**detects the red/green/blue balls** (the ones shipped with the robot) on the
live camera feed and labels them by color. When a ball is at the arm's sweet
spot, I press **Grab**: driving locks, a **pre-recorded servo pose sequence**
picks the ball up, then driving unlocks. An Abort button stops the arm.

Explicitly **not** in scope: autonomous driving/navigation (the human is the
navigation system), inverse kinematics, and reinforcement learning — the grab
is a deterministic scripted choreography, replayed the same way every time.
The human closing the loop (driving until the ball sits in the aiming zone)
is what makes a fixed script sufficient.

> **Project history:** this started as soda-can brand detection ("Robot Teleop
> Cans"). A YOLO11n model was trained on a Roboflow soda dataset and worked
> live (`models\cans_v1.pt`, still usable) — but the stock gripper can't open
> wide enough for a 66 mm can, so the target switched to the Hiwonder balls,
> which the gripper was designed for. The YOLO pipeline below stays documented
> as the scaling path for future custom objects.

---

## Hardware / robot facts

- **Robot:** Hiwonder JetAuto — Jetson Nano onboard, ROS, mecanum wheels (can strafe)
- **Arm:** 5 servos + gripper — IDs `1` (base rotate), `2` (shoulder), `3` (elbow),
  `4` (wrist pitch), `5` (gripper rotation), `10` (grip)
- **Targets:** Hiwonder red/green/blue balls (shipped with robot, sized for the gripper)
- **Camera:** depth cam, RGB topic `/depth_cam/rgb/image_raw`, MJPEG via
  web_video_server on port `8080`
- **Comms:** rosbridge websocket on port `9090`; robot reached over Tailscale at
  `100.82.122.19`
- **Topics used:** `/cmd_vel` (geometry_msgs/Twist),
  `/ros_robot_controller/bus_servo/set_position` (ros_robot_controller_msgs/ServosPosition)
- **Dev PC:** Windows, RTX 3080 10 GB, Python 3.12 venv

---

## Architecture decisions

| Question | Decision |
|---|---|
| How are balls detected? | **Classic HSV color detection** (OpenCV threshold + contours) — uniform-color objects need no ML. No dataset, no training, deterministic. Color = label (`red_ball`, ...) |
| Why not the YOLO model? | YOLO earns its keep on objects color can't separate (soda brands). For three solid-color balls it's pure overhead. The `Detector`/`ColorBallDetector` classes share one interface — `detect(pil_img) → [(label, conf, (x1,y1,x2,y2))]` — so swapping is a config change |
| How does the grab work? | No IK, no RL. A fixed **aiming rectangle** on the camera feed marks the arm's sweet spot (camera is rigid to chassis, so screen position ≡ position relative to arm). Drive until the ball's box sits in it → press **Grab** → movement locks (zero cmd_vel, inputs ignored) → replay a **pre-recorded servo pose sequence** (home → reach → close → lift) → unlock. Abort freezes the arm |
| Why scripted, not learned? | The human guarantees the ball is always at the same spot relative to the arm before pressing Grab; a grasp that is identical every time is a script. RL would need thousands of physical trials or a simulator — a research project, not a feature |
| Pose sequences | Recorded by hand with the servo sliders; stored as JSON (steps of `{positions, duration, pause}`) in `poses\` — data, not code. Every sequence starts with a **home pose** (servo commands are absolute, so this normalizes any starting state) |
| Balls roll | Grab approaches from **above** (cage the ball) rather than the side (nudges it away) |

---

## Folder layout

```
Robot_Teleop_Cans\
├── .venv\                   <- Python env (gitignored)
├── requirements.txt
├── README.md                <- this file
├── app\
│   ├── teleop.py            <- tkinter GUI: joystick, sliders, feed, overlay; the only module that reads config
│   ├── config.py            <- robot IP, topics, model path, zone coords, colors
│   ├── ros_client.py        <- RosbridgeClient (generic: topics injected via constructor)
│   ├── camera.py            <- MjpegCamera: URL in, full-res PIL frames out via callback; no tkinter
│   ├── detector.py          <- YOLO wrapper (kept for custom-object scaling path)
│   ├── color_detector.py    <- HSV ball detector, same interface as detector.py
│   └── grab.py              <- pose sequence load/replay/abort + movement lock
├── training\                <- YOLO-era artifacts (dataset & runs gitignored)
├── models\
│   └── cans_v1.pt           <- trained soda-brand model (works; gripper didn't)
└── poses\
    └── grab_ball.json       <- recorded arm choreography
```

---

## Environment setup (one-time)

```powershell
cd $HOME\Desktop\Robot_Teleop_Cans
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126
pip install -r requirements.txt
python -c "import torch; print(torch.cuda.is_available())"   # True, else reinstall torch
```

(Torch/CUDA only matter for the YOLO path; the ball detector needs just
opencv + numpy, which ride along with ultralytics.)

In VS Code: **Python: Select Interpreter → `.venv\Scripts\python.exe`** — one
project, one interpreter; running with another Python is the classic
"module not found / import could not be resolved" trap here.

Run the app (venv active): `python app\teleop.py`

---

## Status

**Done**
1. Scaffold — venv, requirements, module split (`config` / `ros_client` / `camera` / `teleop`)
2. YOLO pipeline proven end-to-end — GPU inference verified, soda model trained
   (`cans_v1.pt`), live overlay working in the GUI
3. Pivot decision: balls + HSV (gripper can't fit cans)

**Remaining (time-boxed plan)**
4. `color_detector.py` + config switch — live RGB ball overlay *(≈30 min)*
5. **G1 (hardware, no code):** find the grab choreography with the servo
   sliders — ball hand-placed at a reachable spot; record servo values per
   pose and the placement tolerance *(person-with-robot task)*
6. `grab.py` + `poses\grab_ball.json` from the G1 values; bench-test replay 5×
7. Integration: aiming rectangle on the feed (placed where the ball's box sits
   at the G1 spot), always-enabled Grab button, movement lock during replay,
   Abort *(cut from v1: dwell timer / auto-enable — stretch goal)*

**YOLO scaling path (later):** new object → Roboflow dataset → local train
(`yolo train model=yolo11n.pt data=training\dataset\data.yaml epochs=100 imgsz=640`)
→ promote `best.pt` to `models\<name>_vN.pt` → point `MODEL_PATH` at it.
