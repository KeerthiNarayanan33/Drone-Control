"""
Custom Drone Controller Web Server & WebSocket Bridge
Serves modern aviation HUD controller, WebSocket command/telemetry streaming,
and RTSP live video forwarding.
"""

import asyncio
import json
import time
from typing import List
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from contextlib import asynccontextmanager

from drone_comm import (
    DroneControllerCore,
    DEFAULT_DRONE_IP,
    DEFAULT_CONTROL_PORT,
    RTSP_URL,
    NEUTRAL_STICK_VALUE,
    FLAG_FAST_FLY,
    FLAG_FAST_DROP,
    FLAG_EMERGENCY_STOP,
    FLAG_UNLOCK_TAKEOFF,
    FLAG_GYRO_CALIBRATE
)
from video_stream import DroneVideoReceiver

# Active WebSocket clients
connected_clients: List[WebSocket] = []
dev_log_buffer: List[dict] = []

# Global controller & video instances
controller = DroneControllerCore()
video_receiver = DroneVideoReceiver()

def dev_logger(level: str, msg: str, meta: dict):
    """Captures diagnostic logs for the developer terminal."""
    log_entry = {
        "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
        "level": level,
        "message": msg,
        "meta": meta
    }
    dev_log_buffer.append(log_entry)
    if len(dev_log_buffer) > 100:
        dev_log_buffer.pop(0)

controller.log_callback = dev_logger

@asynccontextmanager
async def lifespan(app: FastAPI):
    video_receiver.start()
    asyncio.create_task(status_broadcast_loop())
    yield
    controller.disconnect()
    video_receiver.stop()

app = FastAPI(title="Drone Flight Controller API", lifespan=lifespan)

@app.get("/video_feed")
async def video_feed():
    """Returns multipart MJPEG video stream."""
    return StreamingResponse(
        video_receiver.mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

@app.get("/api/status")
async def get_status():
    status = controller.get_status()
    status["video"] = {
        "streaming": video_receiver.is_streaming,
        "fps": round(video_receiver.current_fps, 1),
        "resolution": f"{video_receiver.width}x{video_receiver.height}" if video_receiver.width > 0 else "Offline"
    }
    return status

@app.post("/api/connect")
async def api_connect(ip: str = DEFAULT_DRONE_IP, port: int = DEFAULT_CONTROL_PORT):
    controller.drone_ip = ip
    controller.control_port = port
    ok = controller.connect()
    return {"success": ok, "status": controller.get_status()}

@app.post("/api/disconnect")
async def api_disconnect():
    controller.disconnect()
    return {"success": True, "status": controller.get_status()}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.append(websocket)
    try:
        while True:
            text = await websocket.receive_text()
            data = json.loads(text)
            handle_ws_command(data)
    except WebSocketDisconnect:
        if websocket in connected_clients:
            connected_clients.remove(websocket)
    except Exception as e:
        if websocket in connected_clients:
            connected_clients.remove(websocket)

def handle_ws_command(data: dict):
    """Processes incoming control packets from web frontend."""
    cmd_type = data.get("type")

    if cmd_type == "sticks":
        # Values range 1 - 255 (neutral 128)
        r = data.get("roll", NEUTRAL_STICK_VALUE)
        p = data.get("pitch", NEUTRAL_STICK_VALUE)
        t = data.get("throttle", NEUTRAL_STICK_VALUE)
        y = data.get("yaw", NEUTRAL_STICK_VALUE)
        controller.set_sticks(r, p, t, y)

    elif cmd_type == "connect":
        ip = data.get("ip", DEFAULT_DRONE_IP)
        port = data.get("port", DEFAULT_CONTROL_PORT)
        controller.drone_ip = ip
        controller.control_port = port
        controller.connect()

    elif cmd_type == "disconnect":
        controller.disconnect()

    elif cmd_type == "takeoff":
        controller.trigger_takeoff()

    elif cmd_type == "land":
        controller.trigger_land()

    elif cmd_type == "emergency":
        controller.trigger_emergency_stop()

    elif cmd_type == "gyro_cal":
        controller.trigger_gyro_calibration()

    elif cmd_type == "camera_switch":
        controller.switch_camera()

    elif cmd_type == "speed_mode":
        is_fast = data.get("fast", False)
        with controller._lock:
            if is_fast:
                controller.flags |= FLAG_FAST_FLY
            else:
                controller.flags &= ~FLAG_FAST_FLY

    elif cmd_type == "settings":
        # Update flight settings & safety limits
        if "speed_limit_pct" in data:
            controller.speed_limit_pct = max(10.0, min(100.0, float(data["speed_limit_pct"])))
        if "dead_zone" in data:
            controller.dead_zone = max(0, min(40, int(data["dead_zone"])))
        if "watchdog_timeout_sec" in data:
            controller.watchdog_timeout_sec = max(0.1, min(2.0, float(data["watchdog_timeout_sec"])))
        if "yaw_hardware_deadband" in data:
            controller.yaw_hardware_deadband = bool(data["yaw_hardware_deadband"])

async def status_broadcast_loop():
    """Broadcasts controller status and logs to active WebSocket clients at 20 Hz."""
    while True:
        if connected_clients:
            status = controller.get_status()
            status["type"] = "status"
            status["video"] = {
                "streaming": video_receiver.is_streaming,
                "fps": round(video_receiver.current_fps, 1),
                "resolution": f"{video_receiver.width}x{video_receiver.height}" if video_receiver.width > 0 else "Offline"
            }
            status["logs"] = list(dev_log_buffer[-10:])

            msg = json.dumps(status)
            for client in list(connected_clients):
                try:
                    await client.send_text(msg)
                except Exception:
                    if client in connected_clients:
                        connected_clients.remove(client)
        await asyncio.sleep(0.05)  # 20 Hz

# Mount web UI static files
app.mount("/", StaticFiles(directory="web", html=True), name="static")

if __name__ == "__main__":
    print("=" * 70)
    print("           CUSTOM DRONE CONTROLLER WEB APPLICATION")
    print("=" * 70)
    print("Local UI URL     : http://localhost:8080")
    print(f"Target Drone IP  : {DEFAULT_DRONE_IP}")
    print(f"Target UDP Port  : {DEFAULT_CONTROL_PORT}")
    print(f"Target RTSP URL  : {RTSP_URL}")
    print("=" * 70)
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="warning")
