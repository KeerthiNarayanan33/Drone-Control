# DRONE TEST REPORT

This report documents the command-by-command verification of the custom controller protocol against the physical drone hardware.

> **Status Legend:**
> - `NOT TESTED` : Awaiting physical verification with active drone Wi-Fi connection
> - `PASS` : Successfully executed on real hardware with expected physical response
> - `FAIL` : Command sent but drone failed to respond or behaved unexpectedly

---

## 1. Connection & Heartbeat Test

| Test Item | Target / Value | Status | Notes |
| :--- | :--- | :--- | :--- |
| Wi-Fi Association | Drone AP (`192.168.1.1`) | NOT TESTED | Verify controlling machine is on drone Wi-Fi |
| UDP Socket Binding | Remote `192.168.1.1:7099` | NOT TESTED | Verify socket opens without network error |
| Keep-Alive Heartbeat | `[0x01, 0x01]` at 1 Hz | NOT TESTED | Verify drone remains in connected state |
| Inbound Downlink ACK | Resolution / Status Bytes | NOT TESTED | Check if drone replies to heartbeat packets |

---

## 2. Basic Flight Controls Verification

| Command | Protocol Payload Structure | Status | Notes |
| :--- | :--- | :--- | :--- |
| **Hover / Neutral** | `Roll=128, Pitch=128, Thr=128, Yaw=128, Flags=0` | NOT TESTED | Drone stays level with sticks centered |
| **Takeoff** | `Flags Bit 5 (0x20)` | NOT TESTED | Motors arm and drone lifts off to initial altitude |
| **Land** | `Flags Bit 1 (0x02)` | NOT TESTED | Drone descends gently and cuts motors upon ground contact |
| **Emergency Stop** | `Flags Bit 2 (0x04)` | NOT TESTED | Immediate rotor power cutoff (failsafe test in safe environment) |
| **Forward** | `Pitch > 128 (e.g. 170-200)` | NOT TESTED | Drone pitches forward |
| **Backward** | `Pitch < 128 (e.g. 56-86)` | NOT TESTED | Drone pitches backward |
| **Left** | `Roll < 128 (e.g. 56-86)` | NOT TESTED | Drone rolls to the left |
| **Right** | `Roll > 128 (e.g. 170-200)` | NOT TESTED | Drone rolls to the right |
| **Up** | `Throttle > 128 (e.g. 170-200)` | NOT TESTED | Drone climbs in altitude |
| **Down** | `Throttle < 128 (e.g. 56-86)` | NOT TESTED | Drone descends in altitude |
| **Rotate Left (Yaw)** | `Yaw < 128 (e.g. 56-86)` | NOT TESTED | Drone rotates counter-clockwise |
| **Rotate Right (Yaw)**| `Yaw > 128 (e.g. 170-200)` | NOT TESTED | Drone rotates clockwise |
| **Stop / Disengage** | `[0x08, 0x01]` | NOT TESTED | Controller release / disengage signal |

---

## 3. Auxiliary & Safety Feature Tests

| Feature | Target / Value | Status | Notes |
| :--- | :--- | :--- | :--- |
| Gyro Calibration | `Flags Bit 7 (0x80)` | NOT TESTED | Triggers motor LED flash or gyro zero-point set |
| Speed Mode (Fast) | `Flags Bit 0 (0x01)` | NOT TESTED | Drone switches to high rate tilt/speed |
| Connection Loss Failsafe| Stop packet transmission | NOT TESTED | Verify drone stabilizes/auto-lands on timeout |
| RTSP Live Video | `rtsp://192.168.1.1:7070/webcam` | NOT TESTED | Video feed displays with low latency |
| Camera Switch | `[0x06, 0x01]` / `[0x06, 0x02]` | NOT TESTED | Toggles active camera sensor if equipped |
