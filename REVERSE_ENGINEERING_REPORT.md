# REVERSE ENGINEERING REPORT: base.apk (RC FPV)
**Target Application:** `base.apk`  
**Analysis Date:** 2026-09-14  
**Target Platform:** Android  
**Objective:** Deconstruct the internal architecture, network protocols, command packet structures, and video streaming mechanisms used by `base.apk` to control the drone, in order to enable independent custom controller development.

---

## 1. Android Application Analysis

### 1.1 Package & Version Metadata
* **Package Name:** `com.cooingdv.rcfpv` [CONFIRMED]
* **Application Label/Name:** `RC FPV` [CONFIRMED]
* **Version Name:** `1.8.0` [CONFIRMED]
* **Version Code:** `52` [CONFIRMED]
* **Minimum Android SDK:** `23` (Android 6.0 Marshmallow) [CONFIRMED]
* **Target Android SDK:** `35` (Android 15) [CONFIRMED]

### 1.2 Activities
The APK contains the following application activities under `com.cooingdv.rcfpv.activity`:
* `SplashActivity` — App initialization, disclaimer checks, consent flows [CONFIRMED]
* `MainActivity` — Main entry point, mode selection, socket initialization (`SocketClient.getInstance().start()`) [CONFIRMED]
* `GenericActivity` — Fragment container hosting flight interfaces [CONFIRMED]
* `BrowseFileActivity` — Local and remote SD-card photo/video browser [CONFIRMED]
* `PhotoViewActivity` — Media viewer for captured photos [CONFIRMED]
* `VideoViewActivity` — Video playback for recorded flights [CONFIRMED]
* `FirmwareActivity` — Camera and firmware settings [CONFIRMED]
* `DeclareActivity` — Legal and user agreement display [CONFIRMED]
* `MusicActivity` — Background audio selection for flight video clips [CONFIRMED]

Primary flight control fragments:
* `com.cooingdv.rcfpv.fragment.DeviceBLFragment` — Primary manual drone controller interface and HUD [CONFIRMED]
* `com.cooingdv.rcfpv.fragment.DeviceTXFragment` — Secondary device controller interface [CONFIRMED]

### 1.3 Services & Broadcast Receivers
* **Services:** No custom drone-communication background services. Network socket communication is handled directly in-process via managed threads and `java.util.Timer` tasks [CONFIRMED]. (Other services present are AndroidX WorkManager and Ad mediation SDKs).
* **Broadcast Receivers:**
  * Network state changes monitored via standard Android broadcast receivers [CONFIRMED]
  * Internal event receiver: `com.cooingdv.rcfpv_fake_resolution` for camera resolution adaptation [CONFIRMED]

### 1.4 Permissions
* `android.permission.INTERNET` [CONFIRMED]
* `android.permission.ACCESS_NETWORK_STATE` [CONFIRMED]
* `android.permission.CHANGE_NETWORK_STATE` [CONFIRMED]
* `android.permission.ACCESS_WIFI_STATE` [CONFIRMED]
* `android.permission.CHANGE_WIFI_STATE` [CONFIRMED]
* `android.permission.WAKE_LOCK` [CONFIRMED]
* `android.permission.VIBRATE` [CONFIRMED]
* `android.permission.MODIFY_AUDIO_SETTINGS` [CONFIRMED]

**Crucial Finding Regarding Wireless Medium:**
* **Bluetooth / BLE Permissions:** `android.permission.BLUETOOTH`, `android.permission.BLUETOOTH_ADMIN`, and `android.permission.BLUETOOTH_CONNECT` are **completely absent** from the manifest [CONFIRMED].
* **Conclusion:** The drone communicates **exclusively over Wi-Fi** [CONFIRMED]. Bluetooth/BLE is **NOT** used.

### 1.5 Libraries & Native Components
* **Native Libraries (`.so`):** `0` native `.so` files present in this base APK [CONFIRMED]. All socket management, packet construction, and byte serialization are executed in pure Java/Kotlin bytecode [CONFIRMED].
* **Embedded Media Frameworks:** `tv.danmaku.ijk.media` (IjkPlayer) for RTSP video stream decoding [CONFIRMED].
* **Embedded Third-party Ad SDKs:** AppLovin, ByteDance Pangle, Bigo, IronSource, Google Mobile Ads (mediation stubs present in APK) [CONFIRMED].

---

## 2. Drone Communication Architecture

### 2.1 Physical & Network Topology
* **Medium:** Wi-Fi [CONFIRMED]
* **Topology:** The drone operates as a Wi-Fi Access Point (AP / Hotspot) [CONFIRMED]. The controlling device connects as a Wi-Fi station (client).
* **Drone IP Address:** `192.168.1.1` [CONFIRMED] (`Config.SERVER_IP`, `Config.TCP_SERVER_HOST`, `Config.FTP_HOST`)
* **Transport Protocols:**
  * **UDP:** Used for keep-alive heartbeats, flight control packets, and camera control [CONFIRMED]
  * **RTSP (TCP/UDP):** Used for live video streaming [CONFIRMED]
  * **FTP (TCP Port 21):** Used for SD card file browsing (`user: ftp`, `pass: ftp`, `root: /0/`) [CONFIRMED]
  * **HTTP / WebSocket:** Not used for flight control [CONFIRMED]

### 2.2 Network Ports
* **Control Port (UDP):** `7099` [CONFIRMED] (`UdpComm.getInstance("192.168.1.1", 7099)`)
* **Video Stream Port (RTSP):** `7070` [CONFIRMED] (`rtsp://192.168.1.1:7070/webcam`)
* **FTP Port (TCP):** `21` [CONFIRMED]
* **TCP Port 5000 (`Config.TCP_SERVER_PORT`):** Present in `Config.java` constants but **not active in bytecode** for control [CONFIRMED].

---

## 3. Communication Protocol & Packet Structure

### 3.1 Keep-Alive / Heartbeat Packet
* **Frequency:** Every 1000 ms (1 Hz) [CONFIRMED] (`SocketClient$HeartBeatTask`)
* **Destination:** UDP `192.168.1.1:7099` [CONFIRMED]
* **Payload Length:** 2 bytes [CONFIRMED]
* **Payload Content:**
  ```
  [ 0x01, 0x01 ]
  ```
* **Purpose:** Informs drone firmware that an active controller application is connected.

### 3.2 Flight Control Packet
* **Frequency:** Every 50 ms (20 Hz) [CONFIRMED] (`FlyController.SEND_COMMAND_INTERVAL = 50`)
* **Destination:** UDP `192.168.1.1:7099` [CONFIRMED]
* **Payload Length:** 9 bytes [CONFIRMED] (or 8 bytes if excluding the channel prefix byte `0x03`)
* **Packet Byte Layout:**

| Byte Index | Name | Type | Value / Range | Description |
| :--- | :--- | :--- | :--- | :--- |
| **Byte 0** | `Prefix / CTP_ID` | `uint8` | `0x03` | Protocol identifier for flying control (`CTP_ID_FLYING`) |
| **Byte 1** | `Start Byte` | `uint8` | `0x66` (102 dec) | Magic frame header start byte |
| **Byte 2** | `Roll (Aileron)` | `uint8` | `1 – 255` | Left / Right lateral movement. Neutral = `128` (0x80) |
| **Byte 3** | `Pitch (Elevator)` | `uint8` | `1 – 255` | Forward / Backward tilt. Neutral = `128` (0x80) |
| **Byte 4** | `Throttle (Accelerator)`| `uint8` | `0 – 255` | Up / Down altitude power. Neutral = `128` (0x80), Idle/Cutoff = `0` |
| **Byte 5** | `Yaw (Rudder)` | `uint8` | `1 – 255` | Rotate Left / Right. Neutral = `128` (0x80) |
| **Byte 6** | `Control Flags` | `uint8` | Bitmask | Special function flags (Takeoff, Land, Stop, etc.) |
| **Byte 7** | `Checksum` | `uint8` | XOR Sum | Checksum over Bytes 2 to 6 (formula below) |
| **Byte 8** | `End Byte` | `uint8` | `0x99` (153 dec) | Magic frame footer end byte |

### 3.3 Checksum Calculation Formula
From decompiled bytecode of `FlyController$FlyControlTask.run()`:
```
checksum = (byte1 ^ byte2 ^ byte3 ^ byte4 ^ (byte5 & 0xFF)) & 0xFF
```
Where:
* `byte1` = Roll (`Byte 2`)
* `byte2` = Pitch (`Byte 3`)
* `byte3` = Throttle (`Byte 4`)
* `byte4` = Yaw (`Byte 5`)
* `byte5` = Control Flags (`Byte 6`)

The checksum byte is placed in `Byte 7`.

### 3.4 Control Flags Bitmask (`Byte 6` / `byte5`)
From decompiled bytecode in `FlyControlTask.run()`:

| Bit | Hex | Dec | Function | Behavior in Original App |
| :--- | :--- | :--- | :--- | :--- |
| **Bit 0** | `0x01` | 1 | `isFastFly` | High speed mode switch |
| **Bit 1** | `0x02` | 2 | `isFastDrop` | Auto-landing / Fast descend command |
| **Bit 2** | `0x04` | 4 | `isEmergencyStop` | Immediate rotor power cutoff (kill switch) |
| **Bit 3** | `0x08` | 8 | `isCircleTurnEnd` | 360-degree flip / roll stunt trigger |
| **Bit 4** | `0x10` | 16 | `isNoHeadMode` | Headless mode toggle |
| **Bit 5** | `0x20` | 32 | `isUnLock` | Motor arm / Auto Take-off trigger |
| **Bit 6** | `0x40` | 64 | Reserved | Unused (0) |
| **Bit 7** | `0x80` | 128 | `isGyroCorrection` | Accelerometer / Gyroscope zero-point calibration |

### 3.5 Neutral / Idle Flight Packet Example
When sticks are centered (neutral) and no button is pressed:
* Roll (`byte1`): `128` (`0x80`)
* Pitch (`byte2`): `128` (`0x80`)
* Throttle (`byte3`): `128` (`0x80`)
* Yaw (`byte4`): `128` (`0x80`)
* Flags (`byte5`): `0` (`0x00`)
* Checksum (`byte6`): `128 ^ 128 ^ 128 ^ 128 ^ 0` = `0` (`0x00`)
* Complete 9-byte packet:
  ```
  [ 0x03, 0x66, 0x80, 0x80, 0x80, 0x80, 0x00, 0x00, 0x99 ]
  ```

### 3.6 Auxiliary Control Packets
* **Controller Disengage / Stop Command:**
  When control mode is deactivated, the app sends:
  ```
  [ 0x08, 0x01 ]  (2 bytes via UDP 7099) [CONFIRMED]
  ```
* **Camera Switch Command:**
  When toggling front/bottom cameras:
  ```
  [ 0x06, 0x01 ] or [ 0x06, 0x02 ]  (2 bytes via UDP 7099) [CONFIRMED]
  ```
* **Event Acknowledgment Responses:**
  When the drone hardware sends a button event:
  * Photo trigger ACK: `[ 0x09, 0x01 ]` [CONFIRMED]
  * Video trigger ACK: `[ 0x09, 0x02 ]` [CONFIRMED]

---

## 4. Inbound Drone Telemetry & Downlink Packets

### 4.1 Downlink Packet Structure (Received on UDP 7099)
When receiving packets from `192.168.1.1:7099`:
* `byte[0]` — Camera Resolution Index (Maps to resolution configurations in `WifiIdUtils`) [CONFIRMED]
* `byte[1]` — Camera Switch / State flag [CONFIRMED]
* `byte[2]` — Event Signature byte:
  * `'M'` (`0x4D`, 77 dec) — Drone hardware photo button pressed [CONFIRMED]. The app parses `byte[3]` as hex photo count and returns `[0x09, 0x01]` ACK.
  * `'X'` (`0x58`, 88 dec) — Drone hardware video button pressed [CONFIRMED]. The app parses `byte[4]` as hex video count and returns `[0x09, 0x02]` ACK.

### 4.2 Telemetry Status
* **Battery Level:** [NOT PRESENT / UNKNOWN] — The original APK has **no battery decoding routine** in any bytecode class. The protocol does not send battery voltage/percentage.
* **Altitude / GPS / Speed Telemetry:** [NOT PRESENT / UNKNOWN] — No MAVLink, GPS, or barometer telemetry parsing exists in the codebase.
* **Conclusion:** All telemetry not provided by the drone (Battery, GPS, Barometer Altitude) **must be marked as `N/A`** and cannot be fabricated, adhering strictly to user guidelines.

---

## 5. Live Video Streaming Analysis

* **Stream Protocol:** RTSP (Real-Time Streaming Protocol) [CONFIRMED]
* **Stream URL:** `rtsp://192.168.1.1:7070/webcam` [CONFIRMED]
* **Video Player Engine in Original App:** `IjkVideoView` (FFmpeg-based player) [CONFIRMED]
* **Decoding / Frame Capture:**
  * For local photo capture without an SD card: the app captures the active bitmap frame from the video renderer [CONFIRMED]
  * For local video recording without an SD card: the app encodes incoming frames into an AVI/MP4 container locally [CONFIRMED]

---

## 6. Classification Summary Table

| Feature / Discovery | Value | Classification |
| :--- | :--- | :--- |
| Physical Medium | Wi-Fi 802.11 (Drone is AP) | **CONFIRMED** |
| Bluetooth / BLE | Not used (no permissions or code) | **CONFIRMED** |
| Drone IP Address | `192.168.1.1` | **CONFIRMED** |
| Drone UDP Control Port | `7099` | **CONFIRMED** |
| Drone RTSP Video Port | `7070` (`rtsp://192.168.1.1:7070/webcam`) | **CONFIRMED** |
| Drone FTP Port | `21` (user: `ftp`, pass: `ftp`) | **CONFIRMED** |
| Keep-Alive Heartbeat | `[0x01, 0x01]` every 1000 ms via UDP | **CONFIRMED** |
| Flight Packet Interval | 50 ms (20 Hz) | **CONFIRMED** |
| Flight Packet Format | `[0x03, 0x66, Roll, Pitch, Thr, Yaw, Flags, Checksum, 0x99]` | **CONFIRMED** |
| Control Stick Range | 1 to 255, Neutral = 128 | **CONFIRMED** |
| Yaw Center Deadband | [104, 152] mapped to 128 | **CONFIRMED** |
| Takeoff Command Flag | Bit 5 (`0x20` = 32) in Flags byte | **CONFIRMED** |
| Land Command Flag | Bit 1 (`0x02` = 2) in Flags byte | **CONFIRMED** |
| Emergency Stop Flag | Bit 2 (`0x04` = 4) in Flags byte | **CONFIRMED** |
| High Speed Flag | Bit 0 (`0x01` = 1) in Flags byte | **CONFIRMED** |
| Gyro Calibration Flag | Bit 7 (`0x80` = 128) in Flags byte | **CONFIRMED** |
| Checksum Formula | `Roll ^ Pitch ^ Thr ^ Yaw ^ Flags` | **CONFIRMED** |
| Disengage Packet | `[0x08, 0x01]` | **CONFIRMED** |
| Camera Switch Packet | `[0x06, 0x01]` / `[0x06, 0x02]` | **CONFIRMED** |
| SD Card Button ACKs | `[0x09, 0x01]` / `[0x09, 0x02]` | **CONFIRMED** |
| Battery Telemetry | Not supported by drone protocol | **UNKNOWN / UNAVAILABLE** |
| GPS / Altitude Telemetry | Not supported by drone protocol | **UNKNOWN / UNAVAILABLE** |
