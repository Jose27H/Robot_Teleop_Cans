from pathlib import Path

# ── Robot config ──────────────────────────────────────────────────────────────
ROBOT_IP        = "100.82.122.19"
ROSBRIDGE_PORT  = 9090
WEB_VIDEO_PORT  = 8080
CAMERA_TOPIC    = "/depth_cam/rgb/image_raw"
CMD_VEL_TOPIC   = "/cmd_vel"
SERVO_TOPIC     = "/ros_robot_controller/bus_servo/set_position"
CAMERA_URL = (f"http://{ROBOT_IP}:{WEB_VIDEO_PORT}/stream"
               f"?topic={CAMERA_TOPIC}&type=mjpeg&quality=65")

MAX_LINEAR  = 0.50   # m/s
MAX_ANGULAR = 1.50   # rad/s

# ── Detection ─────────────────────────────────────────────────────────────────
# Anchored on this file's location so it works from any working directory
MODEL_PATH  = Path(__file__).resolve().parent.parent / "models" / "cans_v1.pt"
DETECT_CONF = 0.5    # minimum confidence for a box to be shown

SERVO_IDS      = [1, 2, 3, 4, 5, 10]
SERVO_DEFAULTS = {1: 500, 2: 750, 3: 0, 4: 375, 5: 500, 10: 500}
SERVO_NAMES    = {
    1:  "#1 Base Rotate",
    2:  "#2 Shoulder",
    3:  "#3 Elbow",
    4:  "#4 Wrist Pitch",
    5:  "#5 Gripper Rotation",
    10: "#6 Grip",
}

# ── Colors ────────────────────────────────────────────────────────────────────
BG      = "#1a1a2e"
PANEL   = "#16213e"
ACCENT  = "#0f3460"
ACCENT2 = "#1a4a80"
TEXT    = "#e0e0ff"
GREEN   = "#00cc66"
BLUE    = "#0066cc"
ORANGE  = "#cc6600"
RED     = "#cc2222"
PURPLE  = "#6060cc"
PURPLE2 = "#8080ff"

