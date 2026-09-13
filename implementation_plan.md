# Custom Drone Controller Implementation Plan

## Goal Description
Build an independent, manual drone-control system for the user's Wi-Fi drone based strictly on the confirmed reverse-engineered protocols extracted from `base.apk` (documented in [REVERSE_ENGINEERING_REPORT.md](file:///c:/Users/keert/projects/Hackathons/drone%20control/REVERSE_ENGINEERING_REPORT.md)). 

The system strictly avoids AI, autonomous missions, or tracking features. Its sole focus is reliable, safe, manual flight control, live RTSP video display, flight parameter customization, and developer diagnostic tooling.

---

## User Review Required

> [!IMPORTANT]
> **No AI or Autonomous Features:** In strict compliance with instructions, zero AI, computer vision detection, person tracking, or autonomous flight logic will be introduced.
> **No Fabricated Telemetry:** As confirmed during reverse engineering, this drone protocol does not transmit battery voltage, GPS coordinates, or barometric altitude over UDP. These will be clearly rendered as `N/A`.
> **Safety Architecture:** Emergency stop is guarded with an intentional multi-step trigger or distinct styling. If Wi-Fi communication drops, the communication layer automatically halts movement packets and drops to neutral failsafe.

---

## Open Questions

> [!NOTE]
> 1. **Testing Environment:** Are you currently connected to the drone's Wi-Fi network (default gateway `192.168.1.1`), or would you like to run Phase 3 (`test_connection.py`) as soon as you power on the drone?
> 2. **Physical Controls:** Will you be operating the controller primarily via touchscreen (phone/tablet/touch laptop), mouse/keyboard, or a physical gamepad/joystick (e.g. Xbox controller)? We can support both virtual touch joysticks and keyboard/gamepad inputs seamlessly.

---

## Proposed Architecture

```
┌────────────────────────────────────────────────────────────┐
│                    Custom Controller UI                    │
│    (Touch Joysticks, HUD, Flight Settings, Dev Terminal)   │
└──────────────────────────────┬─────────────────────────────┘
                               │ WebSocket (Commands & Telemetry)
┌──────────────────────────────▼─────────────────────────────┐
│                   Safety & Limit Manager                   │
│   (App Limits, Rate Limiting, Deadzone, Neutral Failsafe)  │
└──────────────────────────────┬─────────────────────────────┘
                               │
┌──────────────────────────────▼─────────────────────────────┐
│                 Drone Communication Layer                  │
│       (Heartbeat 1Hz, Control 20Hz, Socket Manager)        │
└───────────────┬────────────────────────────┬───────────────┘
                │ UDP 7099                   │ RTSP 7070
                ▼                            ▼
         Drone Control                  Drone Camera
       (192.168.1.1:7099)           (rtsp://192.168.1.1:7070)
```

---

## Proposed Implementation Phases

### Phase 1: Reverse Engineering & Protocol Verification (COMPLETED)
- Analyzed `base.apk` with `androguard`.
- Documented package, permissions, ports, packet format, and checksum calculation in [REVERSE_ENGINEERING_REPORT.md](file:///c:/Users/keert/projects/Hackathons/drone%20control/REVERSE_ENGINEERING_REPORT.md).
- Initialized [DRONE_TEST_REPORT.md](file:///c:/Users/keert/projects/Hackathons/drone%20control/DRONE_TEST_REPORT.md).

### Phase 2: Drone Communication Core Layer (`drone_comm.py`)
- Direct low-level UDP socket manager handling:
  - Target IP: `192.168.1.1` (configurable)
  - Control Port: `7099` (UDP)
  - Heartbeat generator: `[0x01, 0x01]` at 1 Hz
  - Flight packet constructor: `[0x03, 0x66, Roll, Pitch, Thr, Yaw, Flags, Checksum, 0x99]` at 20 Hz (50 ms interval)
  - XOR Checksum generator: `Roll ^ Pitch ^ Thr ^ Yaw ^ Flags`
  - Inbound packet listener: records incoming bytes (`byte[0]` resolution, `0x4D` / `0x58` hardware events)
  - Thread-safe command queue and instant disengage (`[0x08, 0x01]`).

### Phase 3: Minimal Connection Test Script (`test_connection.py`)
- Standalone CLI utility for initial hardware verification:
  - Checks network interface for `192.168.1.x` subnet.
  - Pings `192.168.1.1`.
  - Binds UDP client and emits keep-alive heartbeats.
  - Listens for responses and displays timestamped diagnostic logs (sent packets, received bytes, latency).

### Phase 4: Basic Controls CLI Verification Tool (`test_controls.py`)
- Step-by-step interactive CLI test harness:
  - Allows testing commands one by one (Hover, Takeoff, Land, Emergency Stop, Forward, Backward, Left, Right, Yaw).
  - Prompts user after each command to verify physical reaction.
  - Directly writes pass/fail results into [DRONE_TEST_REPORT.md](file:///c:/Users/keert/projects/Hackathons/drone%20control/DRONE_TEST_REPORT.md).

### Phase 5 & 6: Safety Limit Layer & Flight Settings Engine
- Safety limits implemented in software:
  - Input clamping (`1` to `255`, neutral `128`).
  - Configurable dead zones (default `[104, 152]` for yaw, customizable for pitch/roll).
  - Maximum speed ceiling scaling (reduces full stick throw to a safe configured percentage).
  - Failsafe watchdog timer: If UI stops sending input for > 200 ms, automatically center sticks to neutral (`128, 128, 128, 128, 0`).
  - Connection timeout: If Wi-Fi link drops, immediately stop packet stream.

### Phase 7 & 8: Local Bridge Server & RTSP Video (`server.py`)
- Lightweight FastAPI server:
  - Serves custom web controller.
  - WebSocket for bidirectional sub-millisecond control messages and developer logs.
  - OpenCV video capture thread fetching `rtsp://192.168.1.1:7070/webcam`, serving an MJPEG stream with FPS and resolution metrics.

### Phase 9, 10 & 11: Professional Drone Controller Web Interface (`web/`)
- Modern dark aviation cockpit HUD (deep slate/carbon black with tactical cyan/amber accents).
- High-contrast typography and clear touch targets.
- Features:
  - **Left Virtual Joystick:** Mode 2 Throttle (Y) and Yaw / Rotate (X).
  - **Right Virtual Joystick:** Mode 2 Pitch / Elevator (Y) and Roll / Aileron (X).
  - **Critical Buttons:** Clearly separated `TAKEOFF` (green highlight) and `LAND` (amber highlight).
  - **Emergency Stop:** High-visibility guarded red kill switch with confirmation modal or hold-to-activate.
  - **Flight Settings Panel:** Joystick sensitivity sliders, dead-zone control, application speed limit, calibration trigger (`0x80`).
  - **Developer Mode Drawer:** Real-time packet hex inspector, packets/sec counter, ping/latency meter, raw socket event log.
  - **HUD Telemetry Bar:** Connection status (Connected/Disconnected), Signal, Battery (`N/A`), Altitude (`N/A`), Stream FPS, Resolution.
  - **Live FPV Video Display:** Fullscreen toggle, aspect-ratio preserved background canvas.

---

## Verification Plan

### Automated Tests
1. **Packet Formatting & Checksum Unit Tests (`test_protocol.py`):**
   - Verify XOR checksum correctness against reverse-engineered samples.
   - Verify bitmask flags for Takeoff (`0x20`), Land (`0x02`), Emergency (`0x04`), Gyro (`0x80`).
   - Verify dead-band and clamping behavior.
2. **Socket Mocking Test:**
   - Run a local UDP echo server to verify heartbeat timing (1000 ms) and flight command timing (50 ms).

### Manual Verification on Real Drone
1. Connect PC / test laptop to Drone Wi-Fi hotspot.
2. Execute `python test_connection.py` to confirm basic handshake and keep-alive.
3. Execute `python test_controls.py` on real drone in an open, safe area to verify motor arm / takeoff / hover / landing.
4. Launch full Controller UI (`python server.py`), open in browser, test virtual joysticks and RTSP video feed.
5. Record physical outcomes into `DRONE_TEST_REPORT.md`.
