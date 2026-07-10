#!/usr/bin/env python3
"""
JetAuto Teleop GUI
Requires: pip install websocket-client Pillow
"""

import io
import json
import math
import time
import threading
import tkinter as tk
import urllib.request

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import websocket
    WS_AVAILABLE = True
except ImportError:
    WS_AVAILABLE = False

# ── Robot config ──────────────────────────────────────────────────────────────
ROBOT_IP        = "100.82.122.19"
ROSBRIDGE_PORT  = 9090
WEB_VIDEO_PORT  = 8080
CAMERA_TOPIC    = "/depth_cam/rgb/image_raw"
CMD_VEL_TOPIC   = "/cmd_vel"
SERVO_TOPIC     = "/ros_robot_controller/bus_servo/set_position"

MAX_LINEAR  = 0.50   # m/s
MAX_ANGULAR = 1.50   # rad/s

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


# ── Rosbridge client ──────────────────────────────────────────────────────────
class RosbridgeClient:
    def __init__(self, ip, port):
        self.ip, self.port = ip, port
        self.ws = None
        self.connected = False
        self._lock = threading.Lock()

    def connect(self):
        try:
            self.ws = websocket.WebSocket()
            self.ws.connect(f"ws://{self.ip}:{self.port}", timeout=5)
            self.connected = True
            self._send({"op": "advertise", "topic": CMD_VEL_TOPIC,
                        "type": "geometry_msgs/Twist"})
            self._send({"op": "advertise", "topic": SERVO_TOPIC,
                        "type": "ros_robot_controller_msgs/ServosPosition"})
        except Exception as e:
            self.connected = False
            print(f"[rosbridge] connection failed: {e}")

    def _send(self, data):
        if not self.connected or self.ws is None:
            return
        with self._lock:
            try:
                self.ws.send(json.dumps(data))
            except Exception as e:
                self.connected = False
                print(f"[rosbridge] send error: {e}")

    def cmd_vel(self, lx, ly, az):
        self._send({"op": "publish", "topic": CMD_VEL_TOPIC,
                    "msg": {"linear":  {"x": float(lx), "y": float(ly), "z": 0.0},
                            "angular": {"x": 0.0,        "y": 0.0,       "z": float(az)}}})

    def set_servo(self, positions: dict, duration=0.1):
        self._send({"op": "publish", "topic": SERVO_TOPIC,
                    "msg": {"duration": float(duration),
                            "position": [{"id": k, "position": v}
                                         for k, v in positions.items()]}})

    def disconnect(self):
        self.connected = False
        try:
            if self.ws:
                self.ws.close()
        except Exception:
            pass


# ── Virtual joystick widget ───────────────────────────────────────────────────
class Joystick(tk.Canvas):
    def __init__(self, parent, size=200, callback=None, **kw):
        super().__init__(parent, width=size, height=size, **kw)
        self.size     = size
        self.center   = size // 2
        self.radius   = size // 2 - 12
        self.thumb_r  = 22
        self.callback = callback
        self.vx = self.vy = 0.0
        self._dragging = False
        self._draw()
        self.bind("<ButtonPress-1>",   self._press)
        self.bind("<B1-Motion>",       self._drag)
        self.bind("<ButtonRelease-1>", self._release)

    def _draw(self, tx=None, ty=None):
        self.delete("all")
        cx = cy = self.center
        r = self.radius
        # Background ring
        self.create_oval(cx - r, cy - r, cx + r, cy + r,
                         fill="#0d0d1e", outline="#3a3a7e", width=2)
        # Crosshair lines
        self.create_line(cx - r, cy, cx + r, cy, fill="#2a2a5e", width=1, dash=(4, 4))
        self.create_line(cx, cy - r, cx, cy + r, fill="#2a2a5e", width=1, dash=(4, 4))
        # Direction labels
        for txt, px, py in [("FWD", cx, cy - r + 10), ("BWD", cx, cy + r - 10),
                              ("◄",  cx - r + 10, cy), ("►",  cx + r - 10, cy)]:
            self.create_text(px, py, text=txt, fill="#5555aa", font=("Helvetica", 8))
        # Thumb
        tx = tx if tx is not None else cx
        ty = ty if ty is not None else cy
        self.create_oval(tx - self.thumb_r, ty - self.thumb_r,
                         tx + self.thumb_r, ty + self.thumb_r,
                         fill=PURPLE, outline=PURPLE2, width=2)
        # Value display
        if self.vx != 0 or self.vy != 0:
            self.create_text(cx, cy + r + 14, fill=TEXT,
                             text=f"x:{self.vy:+.2f}  y:{self.vx:+.2f}",
                             font=("Helvetica", 7))

    def _clamp(self, x, y):
        cx = cy = self.center
        dx, dy = x - cx, y - cy
        d = math.hypot(dx, dy)
        if d > self.radius:
            s = self.radius / d
            x, y = cx + dx * s, cy + dy * s
        return x, y

    def _press(self, e):
        self._dragging = True
        self._update(e.x, e.y)

    def _drag(self, e):
        if self._dragging:
            self._update(e.x, e.y)

    def _release(self, e):
        self._dragging = False
        self.vx = self.vy = 0.0
        self._draw()
        if self.callback:
            self.callback(0.0, 0.0)

    def _update(self, x, y):
        tx, ty = self._clamp(x, y)
        cx = cy = self.center
        self.vx = (tx - cx) / self.radius          # lateral  → linear_y
        self.vy = -(ty - cy) / self.radius          # vertical → linear_x
        self._draw(tx, ty)
        if self.callback:
            self.callback(self.vx, self.vy)


# ── Main application ──────────────────────────────────────────────────────────
class TeleopApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("JetAuto Teleop")
        self.root.configure(bg=BG)

        self.client   = RosbridgeClient(ROBOT_IP, ROSBRIDGE_PORT)
        self.lx = self.ly = self.az = 0.0
        self.servo_vals = dict(SERVO_DEFAULTS)
        self._running = True

        self._build_ui()
        self._connect_async()
        if PIL_AVAILABLE:
            threading.Thread(target=self._camera_thread, daemon=True).start()
        self._publish_loop()
        self.root.protocol("WM_DELETE_WINDOW", self._quit)

    # ── UI construction ───────────────────────────────────────────────────────
    def _build_ui(self):
        # ── Title bar ─────────────────────────────────────────────────────────
        bar = tk.Frame(self.root, bg=ACCENT, pady=6)
        bar.pack(fill=tk.X)
        tk.Label(bar, text="  JetAuto Teleop Controller",
                 font=("Helvetica", 13, "bold"), fg=TEXT, bg=ACCENT).pack(side=tk.LEFT)
        self.status_lbl = tk.Label(bar, text="● Connecting…",
                                    font=("Helvetica", 10), fg="#ffaa00", bg=ACCENT)
        self.status_lbl.pack(side=tk.RIGHT, padx=12)

        # ── Content row ───────────────────────────────────────────────────────
        content = tk.Frame(self.root, bg=BG)
        content.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        left  = tk.Frame(content, bg=BG)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        right = tk.LabelFrame(content, text=" Servo Control ",
                               font=("Helvetica", 10, "bold"), fg=TEXT, bg=PANEL,
                               bd=2, relief=tk.GROOVE)
        right.pack(side=tk.RIGHT, fill=tk.Y, padx=(8, 0))

        # ── Camera ────────────────────────────────────────────────────────────
        cam_f = tk.LabelFrame(left, text=" Live Camera ",
                               font=("Helvetica", 10, "bold"), fg=TEXT, bg=PANEL,
                               bd=2, relief=tk.GROOVE)
        cam_f.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        cam_container = tk.Frame(cam_f, width=640, height=360, bg="#080814")
        cam_container.pack(padx=4, pady=4)
        cam_container.pack_propagate(False)
        self.cam_lbl = tk.Label(cam_container, bg="#080814")
        self.cam_lbl.pack(fill=tk.BOTH, expand=True)
        if not PIL_AVAILABLE:
            tk.Label(cam_f, text="⚠  pip install Pillow  to enable camera",
                     fg="#ff6666", bg="#080814", font=("Helvetica", 10)).pack()

        # ── Controls row ──────────────────────────────────────────────────────
        ctrl = tk.Frame(left, bg=BG)
        ctrl.pack(fill=tk.X)

        # Joystick
        joy_f = tk.LabelFrame(ctrl, text=" Drive (Drag) ",
                               font=("Helvetica", 9, "bold"), fg=TEXT, bg=PANEL,
                               bd=2, relief=tk.GROOVE)
        joy_f.pack(side=tk.LEFT, padx=(0, 8))
        self.joystick = Joystick(joy_f, size=210, callback=self._joy_cb,
                                  bg=PANEL, highlightthickness=0)
        self.joystick.pack(padx=8, pady=8)
        tk.Label(joy_f, text="Drag for X/Y drive · WASD keys also work",
                 fg="#555588", bg=PANEL, font=("Helvetica", 7)).pack(pady=(0, 4))

        # Turn + Stop
        ts_f = tk.LabelFrame(ctrl, text=" Turn / Stop ",
                              font=("Helvetica", 9, "bold"), fg=TEXT, bg=PANEL,
                              bd=2, relief=tk.GROOVE)
        ts_f.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))

        tk.Frame(ts_f, bg=PANEL, height=12).pack()

        turn_row = tk.Frame(ts_f, bg=PANEL)
        turn_row.pack(padx=10)

        bs = dict(font=("Helvetica", 22, "bold"), width=3, height=2,
                  bg=ACCENT, fg=TEXT, activebackground=ACCENT2,
                  activeforeground=TEXT, relief=tk.RAISED, bd=3, cursor="hand2")

        self.left_btn = tk.Button(turn_row, text="◄", **bs)
        self.left_btn.pack(side=tk.LEFT, padx=4)
        self.left_btn.bind("<ButtonPress-1>",   lambda e: self._set_az(MAX_ANGULAR))
        self.left_btn.bind("<ButtonRelease-1>", lambda e: self._set_az(0.0))

        self.right_btn = tk.Button(turn_row, text="►", **bs)
        self.right_btn.pack(side=tk.LEFT, padx=4)
        self.right_btn.bind("<ButtonPress-1>",   lambda e: self._set_az(-MAX_ANGULAR))
        self.right_btn.bind("<ButtonRelease-1>", lambda e: self._set_az(0.0))

        tk.Frame(ts_f, bg=PANEL, height=8).pack()
        tk.Button(ts_f, text="■  STOP", font=("Helvetica", 11, "bold"),
                  width=12, height=2, bg=RED, fg="white",
                  activebackground="#ee3333", cursor="hand2",
                  command=self._stop_all).pack(padx=10, pady=6)

        # Key hints
        hints = tk.Frame(ts_f, bg=PANEL)
        hints.pack(padx=6, pady=(0, 8))
        for txt, col in [("W/S: fwd/bwd", "#aaaaee"),
                          ("A/D: strafe",  "#aaaaee"),
                          ("Q/E: turn",    "#aaaaee"),
                          ("Space: stop",  "#ffaaaa")]:
            tk.Label(hints, text=txt, fg=col, bg=PANEL,
                     font=("Helvetica", 8)).pack(anchor="w")

        # Speed meters
        spd_f = tk.LabelFrame(ctrl, text=" Speed ",
                               font=("Helvetica", 9, "bold"), fg=TEXT, bg=PANEL,
                               bd=2, relief=tk.GROOVE)
        spd_f.pack(side=tk.LEFT, fill=tk.Y)
        self.spd_canvas = tk.Canvas(spd_f, width=90, height=210,
                                     bg=PANEL, highlightthickness=0)
        self.spd_canvas.pack(padx=6, pady=6)

        # ── Servo panel ───────────────────────────────────────────────────────
        self.servo_sliders = {}
        self.servo_val_lbl = {}

        for sid in SERVO_IDS:
            row = tk.Frame(right, bg=PANEL, pady=3)
            row.pack(fill=tk.X, padx=8)

            tk.Label(row, text=SERVO_NAMES[sid],
                     font=("Helvetica", 9, "bold"), fg=TEXT, bg=PANEL,
                     width=13, anchor="w").pack(side=tk.LEFT)

            vl = tk.Label(row, text=str(SERVO_DEFAULTS[sid]),
                           font=("Courier", 9), fg="#88ff88", bg=PANEL, width=4)
            vl.pack(side=tk.RIGHT)
            self.servo_val_lbl[sid] = vl

            # Center reset
            tk.Button(row, text="⊙", font=("Helvetica", 8), width=2,
                      bg=ACCENT, fg=TEXT, activebackground=ACCENT2, cursor="hand2",
                      command=lambda s=sid: self._center_servo(s)).pack(side=tk.RIGHT, padx=2)

            var = tk.IntVar(value=SERVO_DEFAULTS[sid])
            sl = tk.Scale(row, from_=0, to=1000, orient=tk.HORIZONTAL,
                           length=160, variable=var, showvalue=False,
                           command=lambda v, s=sid: self._servo_cb(s, int(v)),
                           bg=PANEL, fg=TEXT, troughcolor=ACCENT,
                           activebackground=PURPLE, highlightthickness=0)
            sl.set(SERVO_DEFAULTS[sid])
            sl.pack(side=tk.LEFT, padx=4)
            self.servo_sliders[sid] = sl

        tk.Frame(right, bg=PANEL, height=6).pack()

        tk.Button(right, text="Reset All Servos",
                  font=("Helvetica", 10, "bold"), bg="#006633", fg="white",
                  activebackground="#008844", cursor="hand2",
                  command=self._reset_servos).pack(padx=10, pady=(0, 10), fill=tk.X)

        # ── Keyboard bindings ─────────────────────────────────────────────────
        self.root.bind("<KeyPress-w>",     lambda e: self._key_move( MAX_LINEAR, 0, 0))
        self.root.bind("<KeyPress-s>",     lambda e: self._key_move(-MAX_LINEAR, 0, 0))
        self.root.bind("<KeyPress-a>",     lambda e: self._key_move(0, -MAX_LINEAR, 0))
        self.root.bind("<KeyPress-d>",     lambda e: self._key_move(0,  MAX_LINEAR, 0))
        self.root.bind("<KeyPress-q>",     lambda e: self._key_move(0, 0,  MAX_ANGULAR))
        self.root.bind("<KeyPress-e>",     lambda e: self._key_move(0, 0, -MAX_ANGULAR))
        self.root.bind("<KeyRelease-w>",   lambda e: self._key_stop_fwd())
        self.root.bind("<KeyRelease-s>",   lambda e: self._key_stop_fwd())
        self.root.bind("<KeyRelease-a>",   lambda e: self._key_stop_lat())
        self.root.bind("<KeyRelease-d>",   lambda e: self._key_stop_lat())
        self.root.bind("<KeyRelease-q>",   lambda e: self._set_az(0.0))
        self.root.bind("<KeyRelease-e>",   lambda e: self._set_az(0.0))
        self.root.bind("<space>",          lambda e: self._stop_all())

    # ── Connection ────────────────────────────────────────────────────────────
    def _connect_async(self):
        def _run():
            self.client.connect()
            if self.client.connected:
                self.root.after(0, lambda: self.status_lbl.config(
                    text=f"● Connected  {ROBOT_IP}", fg=GREEN))
            else:
                self.root.after(0, lambda: self.status_lbl.config(
                    text="● Disconnected — retrying…", fg=RED))
                self.root.after(4000, self._connect_async)
        threading.Thread(target=_run, daemon=True).start()

    # ── Camera thread ─────────────────────────────────────────────────────────
    def _camera_thread(self):
        url = (f"http://{ROBOT_IP}:{WEB_VIDEO_PORT}/stream"
               f"?topic={CAMERA_TOPIC}&type=mjpeg&quality=65")
        while self._running:
            try:
                req = urllib.request.urlopen(url, timeout=8)
                buf = b""
                while self._running:
                    buf += req.read(8192)
                    while True:
                        s = buf.find(b"\xff\xd8")
                        e = buf.find(b"\xff\xd9", s + 2)
                        if s == -1 or e == -1:
                            break
                        jpg  = buf[s:e + 2]
                        buf  = buf[e + 2:]
                        try:
                            img   = Image.open(io.BytesIO(jpg)).resize((640, 360), Image.LANCZOS)
                            photo = ImageTk.PhotoImage(img)
                            self.root.after(0, self._show_frame, photo)
                        except Exception:
                            pass
            except Exception as ex:
                if self._running:
                    time.sleep(2)

    def _show_frame(self, photo):
        self.cam_lbl.configure(image=photo)
        self.cam_lbl.image = photo

    # ── Control callbacks ─────────────────────────────────────────────────────
    def _joy_cb(self, vx, vy):
        self.ly = -vx * MAX_LINEAR  # lateral
        self.lx = vy * MAX_LINEAR   # forward

    def _set_az(self, val):
        self.az = val

    def _key_move(self, lx, ly, az):
        if lx != 0: self.lx = lx
        if ly != 0: self.ly = ly
        if az != 0: self.az = az

    def _key_stop_fwd(self): self.lx = 0.0
    def _key_stop_lat(self): self.ly = 0.0

    def _stop_all(self):
        self.lx = self.ly = self.az = 0.0
        self.joystick._draw()
        self.client.cmd_vel(0.0, 0.0, 0.0)

    def _servo_cb(self, sid, val):
        self.servo_vals[sid] = val
        self.servo_val_lbl[sid].config(text=str(val))
        self.client.set_servo({sid: val}, duration=0.08)

    def _center_servo(self, sid):
        self.servo_sliders[sid].set(500)

    def _reset_servos(self):
        for sid, val in SERVO_DEFAULTS.items():
            self.servo_sliders[sid].set(val)
        self.client.set_servo(SERVO_DEFAULTS, duration=1.0)

    # ── Speed meter ───────────────────────────────────────────────────────────
    def _draw_speed(self):
        c  = self.spd_canvas
        W, H = 90, 210
        c.delete("all")
        bars = [("Vx fwd", self.lx, MAX_LINEAR, GREEN),
                ("Vy lat", self.ly, MAX_LINEAR, BLUE),
                ("ω turn", self.az, MAX_ANGULAR, ORANGE)]
        for i, (label, val, mx, color) in enumerate(bars):
            y0 = 10 + i * 65
            c.create_text(W // 2, y0, text=label, fill="#9999cc",
                          font=("Helvetica", 8))
            bx, by = 10, y0 + 12
            bw, bh = W - 20, 22
            c.create_rectangle(bx, by, bx + bw, by + bh,
                                fill="#080814", outline="#2a2a5e")
            mid = bx + bw // 2
            c.create_line(mid, by, mid, by + bh, fill="#333366")
            fill = int(abs(val) / mx * (bw // 2))
            if val >= 0:
                c.create_rectangle(mid, by + 2, mid + fill, by + bh - 2, fill=color)
            else:
                c.create_rectangle(mid - fill, by + 2, mid, by + bh - 2, fill=color)
            c.create_text(W // 2, by + bh + 6, text=f"{val:+.2f}",
                          fill=color, font=("Courier", 8))

    # ── 10 Hz publish loop ────────────────────────────────────────────────────
    def _publish_loop(self):
        if self._running:
            self.client.cmd_vel(self.lx, self.ly, self.az)
            self._draw_speed()
            self.root.after(100, self._publish_loop)

    # ── Cleanup ───────────────────────────────────────────────────────────────
    def _quit(self):
        self._running = False
        self.client.cmd_vel(0.0, 0.0, 0.0)
        time.sleep(0.12)
        self.client.disconnect()
        self.root.destroy()


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    missing = []
    if not WS_AVAILABLE:
        missing.append("websocket-client")
    if not PIL_AVAILABLE:
        missing.append("Pillow")
    if missing:
        print(f"\n  Install missing packages:  pip install {' '.join(missing)}\n")
        if not WS_AVAILABLE:
            print("  websocket-client is required to connect to the robot.")
            return

    root = tk.Tk()
    root.resizable(True, True)
    TeleopApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
