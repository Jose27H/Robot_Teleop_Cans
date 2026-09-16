"""
"Follow the Can" controller.

Pure logic: latest detection boxes + frame size in, (forward, turn) command
out. Knows nothing about tkinter, ROS, or cameras, so it can be tuned or
broken without affecting the rest of the app.

All tunables are class constants — tweak them live between demo runs.
"""

import time


class FollowController:
    # ── Tunables ──────────────────────────────────────────────────────────────
    DEADBAND      = 0.10   # |center error| below this → considered centered
    TURN_GAIN     = 0.90   # fraction of max_angular applied at full off-center
    ALIGN_FIRST   = 0.40   # only drive forward once |error| is under this
    TARGET_WIDTH  = 0.35   # box width / frame width at which we stop (can is close)
    DRIVE_GAIN    = 0.55   # fraction of max_linear when the can is far away
    MIN_DRIVE     = 0.08   # m/s floor so the robot actually moves
    LOST_TIMEOUT  = 0.8    # seconds to coast on the last command after losing the can

    def __init__(self, max_linear, max_angular):
        self.max_linear  = max_linear
        self.max_angular = max_angular
        self._last_cmd   = (0.0, 0.0)
        self._last_seen  = 0.0

    @staticmethod
    def pick_target(detections):
        """Largest box = closest can. Returns a detection tuple or None."""
        if not detections:
            return None
        return max(detections,
                   key=lambda d: (d[2][2] - d[2][0]) * (d[2][3] - d[2][1]))

    def update(self, detections, frame_size):
        """Returns (linear_x, angular_z, status_text)."""
        target = self.pick_target(detections)
        now = time.monotonic()

        if target is None:
            # Brief grace period so detection flicker doesn't make it jerky
            if now - self._last_seen < self.LOST_TIMEOUT:
                lx, az = self._last_cmd
                return lx, az, "lost… coasting"
            self._last_cmd = (0.0, 0.0)
            return 0.0, 0.0, "searching for can"

        self._last_seen = now
        w, _h = frame_size
        _label, _conf, (x1, _y1, x2, _y2) = target

        cx = (x1 + x2) / 2.0
        error = (cx - w / 2.0) / (w / 2.0)      # -1 (far left) … +1 (far right)
        width_frac = (x2 - x1) / w               # grows as the can gets closer

        # Turn: can left of center → positive z (turn left), matching ◄ button
        if abs(error) < self.DEADBAND:
            az = 0.0
        else:
            az = -error * self.TURN_GAIN * self.max_angular

        # Drive: approach until the can fills TARGET_WIDTH of the frame,
        # and only while roughly aimed at it
        if width_frac >= self.TARGET_WIDTH:
            lx = 0.0
            status = "arrived ✔" if az == 0.0 else "centering…"
        elif abs(error) > self.ALIGN_FIRST:
            lx = 0.0
            status = "turning to can"
        else:
            closeness = width_frac / self.TARGET_WIDTH   # 0 far … 1 there
            lx = max(self.MIN_DRIVE,
                     (1.0 - closeness) * self.DRIVE_GAIN * self.max_linear)
            status = "approaching…"

        self._last_cmd = (lx, az)
        return lx, az, status
