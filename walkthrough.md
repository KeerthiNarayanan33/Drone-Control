# Walkthrough: Custom Drone Control System

## Overview
We have completely reverse engineered `base.apk` (the original Android app for your drone) and built an independent, standalone, high-performance manual drone controller application and hardware test harness.

All discoveries were classified as `CONFIRMED`, `LIKELY`, or `UNKNOWN`, with **zero invented parameters**. In accordance with your explicit instructions, no AI, autonomous navigation, or target tracking was introduced, and all unsupported telemetry (Battery, GPS, Altitude) is strictly reported as `N/A`.

---

## 1. Reverse Engineering Findings (`REVERSE_ENGINEERING_REPORT.md`)
The full report is saved at [REVERSE_ENGINEERING_REPORT.md](file:///c:/Users/keert/projects/Hackathons/drone%20control/REVERSE_ENGINEERING_REPORT.md).

* **App Package:** `com.cooingdv.rcfpv` (RC FPV v1.8.0).
* **Wireless Medium:** **Wi-Fi only** (Bluetooth/BLE permissions are completely absent). The drone acts as a Wi-Fi Access Point (AP).
* **Network Target:** `192.168.1.1`
  * **UDP Control Port:** `7099` (CONFIRMED in `SocketClient.startUdpTask`)
  * **RTSP Video Port:** `7070` (`rtsp://192.168.1.1:7070/webcam`)
  * **FTP Port:** `21` (`ftp:ftp` for SD card file browsing)
* **Keep-Alive Heartbeat:** `[0x01, 0x01]` sent at **1 Hz** (1000 ms) via UDP to port 7099.
* **Flight Control Packet:** 9-byte packet sent at **20 Hz** (50 ms) via UDP to port 7099:
  $$\text{Packet: } [0\text{x}03, 0\text{x}66, \text{Roll}, \text{Pitch}, \text{Throttle}, \text{Yaw}, \text{Flags}, \text{Checksum}, 0\text{x}99]$$
  * `Byte 0`: `0x03` (Control channel ID / `CTP_ID_FLYING`)
  * `Byte 1`: `0x66` (Magic start byte, 102 dec)
  * `Byte 2` (Roll): $1 - 255$, Neutral = $128$
  * `Byte 3` (Pitch): $1 - 255$, Neutral = $128$
  * `Byte 4` (Throttle): $0 - 255$, Neutral = $128$ (0 for cut-off)
  * `Byte 5` (Yaw): $1 - 255$, Neutral = $128$ (Firmware dead-band: $[104, 152] \to 128$)
  * `Byte 6` (Flags):
    * Bit 0 (`0x01`): Speed Mode
    * Bit 1 (`0x02`): Auto-Land / Fast Drop
    * Bit 2 (`0x04`): Emergency Stop (kill switch)
    * Bit 3 (`0x08`): 360 Flip / Circle Turn End
    * Bit 4 (`0x10`): Headless Mode
    * Bit 5 (`0x20`): Unlock / Takeoff
    * Bit 7 (`0x80`): Gyroscope Calibration
  * `Byte 7` (Checksum): $\text{Roll} \oplus \text{Pitch} \oplus \text{Throttle} \oplus \text{Yaw} \oplus \text{Flags}$
  * `Byte 8`: `0x99` (Magic end byte, 153 dec)
* **Auxiliary Commands:**
  * Controller Disengage / Stop: `[0x08, 0x01]`
  * Camera Switch: `[0x06, 0x01]` / `[0x06, 0x02]`
  * SD Card Hardware Button ACKs: Photo `[0x09, 0x01]`, Video `[0x09, 0x02]`

---

## 2. Core Modules Implemented

### 1. Communication Layer ([drone_comm.py](file:///c:/Users/keert/projects/Hackathons/drone%20control/drone_comm.py))
- Direct UDP socket engine targeting `192.168.1.1:7099`.
- Dedicated 1 Hz heartbeat thread emitting `[0x01, 0x01]`.
- Precision 20 Hz control loop emitting 9-byte flight packets.
- Hardware deadband $[104, 152]$ handling and XOR checksum calculation.
- Safety Watchdog: auto-reverts sticks to neutral (`128, 128, 128, 128, 0`) if input ceases for $> 300\text{ ms}$.
- Clean disengage packet `[0x08, 0x01]` upon shutdown.

### 2. Protocol Unit Tests ([test_protocol.py](file:///c:/Users/keert/projects/Hackathons/drone%20control/test_protocol.py))
- 7 automated unit tests verifying checksum calculation, neutral packet structure, takeoff/land/emergency bitmask flags, stick clamping, and deadband handling.
- Result: **7/7 PASSED**.

### 3. Minimal Connection Test Tool ([test_connection.py](file:///c:/Users/keert/projects/Hackathons/drone%20control/test_connection.py))
- Standalone CLI for Phase 3 verification.
- Checks local network subnet, ICMP reachability, binds UDP socket, emits heartbeats, listens for responses, and logs timestamped hex packets.

### 4. Step-by-Step Flight Controls Verification Tool ([test_controls.py](file:///c:/Users/keert/projects/Hackathons/drone%20control/test_controls.py))
- Interactive CLI for Phase 4 command-by-command testing.
- Tests individual commands with timed pulses (Takeoff, Land, Hover, Emergency Stop, Forward, Backward, Left, Right, Up, Down, Yaw Left, Yaw Right).
- Automatically updates [DRONE_TEST_REPORT.md](file:///c:/Users/keert/projects/Hackathons/drone%20control/DRONE_TEST_REPORT.md).

### 5. Live RTSP Video Module ([video_stream.py](file:///c:/Users/keert/projects/Hackathons/drone%20control/video_stream.py))
- Low-latency RTSP capture (`rtsp://192.168.1.1:7070/webcam`) with auto-reconnection and measured FPS/resolution calculation.
- Generates a tactical standby HUD card when video is offline.

### 6. Controller Web Server ([server.py](file:///c:/Users/keert/projects/Hackathons/drone%20control/server.py))
- FastAPI backend serving static UI, `/video_feed` MJPEG stream, and `/ws` WebSocket bridge.
- Broadcasts 20 Hz live status and developer logs.

### 7. Modern Cockpit Web UI ([web/index.html](file:///c:/Users/keert/projects/Hackathons/drone%20control/web/index.html), [web/style.css](file:///c:/Users/keert/projects/Hackathons/drone%20control/web/style.css), [web/app.js](file:///c:/Users/keert/projects/Hackathons/drone%20control/web/app.js))
- **HUD Theme:** Dark carbon cockpit with tactical cyan reticle and status indicators.
- **Virtual Joysticks:** Touch and mouse pointer tracking for Mode 2 (Left = Throttle/Yaw, Right = Pitch/Roll) with auto-centering to 128.
- **Desktop Keyboard Support:** `W/S/A/D` for Throttle/Yaw, `Arrows` for Pitch/Roll.
- **Separated Action Controls:** Dedicated glowing `TAKE OFF` and `AUTO LAND` buttons.
- **Guarded Emergency Stop:** High-visibility red button with safety confirmation to prevent accidental motor cutoff.
- **Telemetry Bar:** Displays FPS, resolution, and strict `N/A` for Battery, Altitude, GPS.
- **Flight Settings Modal:** Custom application speed ceiling slider (20% to 100%), joystick deadzone, and watchdog timeout.
- **Developer Diagnostics Drawer:** Real-time hex packet inspector, packet counters (Sent, Recv, Heartbeats), and rolling live event logs.

---

## 3. How to Test on Real Hardware

### Step 1: Connect to Drone Wi-Fi
1. Power on your physical drone.
2. On your computer, open Wi-Fi settings and connect to the drone's Wi-Fi network (typically an open network starting with `RC-` or `FPV-`).
3. Verify that your machine is assigned an IP in the `192.168.1.x` subnet.

### Step 2: Run Phase 3 Minimal Connection Test
Run the connection test tool in your terminal:
```powershell
python test_connection.py
```
Observe the live log:
- Verify heartbeats `[0x01, 0x01]` are being emitted at 1 Hz.
- Check if inbound packets or camera resolution bytes are returned by the drone.

### Step 3: Run Phase 4 Command-by-Command Verification
Ensure the drone is on a flat, clear surface in an open area:
```powershell
python test_controls.py
```
1. Select commands one by one (e.g. `Takeoff`, `Hover`, `Land`).
2. After each command, the tool prompts you to confirm physical behavior and automatically updates [DRONE_TEST_REPORT.md](file:///c:/Users/keert/projects/Hackathons/drone%20control/DRONE_TEST_REPORT.md).

### Step 4: Launch the Full Web Controller
Start the web application:
```powershell
python server.py
```
Open your web browser (or mobile browser if on the same Wi-Fi) to:
```
http://localhost:8080
```
- Click **CONNECT** to start the UDP stream.
- Use touch or keyboard (`W/S/A/D`, Arrow keys) to pilot the drone.
- Monitor live hex packets in the **DEV LOG** drawer.
- Adjust stick sensitivity and speed ceilings in **SETTINGS**.
