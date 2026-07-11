import json
import threading

import websocket


class RosbridgeClient:
    def __init__(self, ip, port, cmd_vel_topic, servo_topic):
        self.ip, self.port = ip, port
        self.cmd_vel_topic = cmd_vel_topic
        self.servo_topic = servo_topic
        self.ws = None
        self.connected = False
        self._lock = threading.Lock()

    def connect(self):
        try:
            self.ws = websocket.WebSocket()
            self.ws.connect(f"ws://{self.ip}:{self.port}", timeout=5)
            self.connected = True
            self._send({"op": "advertise", "topic": self.cmd_vel_topic,
                        "type": "geometry_msgs/Twist"})
            self._send({"op": "advertise", "topic": self.servo_topic,
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
        self._send({"op": "publish", "topic": self.cmd_vel_topic,
                    "msg": {"linear":  {"x": float(lx), "y": float(ly), "z": 0.0},
                            "angular": {"x": 0.0,        "y": 0.0,       "z": float(az)}}})

    def set_servo(self, positions: dict, duration=0.1):
        self._send({"op": "publish", "topic": self.servo_topic,
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