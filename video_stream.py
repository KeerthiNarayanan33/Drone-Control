"""
Live RTSP Video Stream Manager (Phase 9)
Streams video from the drone's RTSP endpoint: rtsp://192.168.1.1:7070/webcam
Provides live JPEG frames, measured FPS, and resolution metrics.
"""

import cv2
import time
import threading
import numpy as np
from typing import Optional, Tuple, Generator

class DroneVideoReceiver:
    """Manages background OpenCV RTSP stream capture and JPEG encoding."""

    def __init__(self, rtsp_url: str = "rtsp://192.168.1.1:7070/webcam"):
        self.rtsp_url = rtsp_url
        self._is_running = False
        self._cap: Optional[cv2.VideoCapture] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Stream status
        self.is_streaming = False
        self.current_fps = 0.0
        self.width = 0
        self.height = 0
        self.last_frame_time = 0.0
        self._current_jpeg: Optional[bytes] = None

    def start(self):
        """Starts the background video grabber thread."""
        if self._is_running:
            return
        self._is_running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True, name="DroneVideoCapture")
        self._thread.start()

    def stop(self):
        """Stops video capture and releases video resources."""
        self._is_running = False
        if self._cap:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None
        self.is_streaming = False

    def _generate_placeholder_frame(self, message: str) -> bytes:
        """Generates an aviation style radar/standby HUD card when video is offline."""
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        # Deep blue-gray background
        img[:] = (18, 22, 28)

        # Draw grid lines
        for x in range(0, 640, 64):
            cv2.line(img, (x, 0), (x, 480), (30, 36, 45), 1)
        for y in range(0, 480, 48):
            cv2.line(img, (y, 0), (y, 480), (30, 36, 45), 1)

        # Center reticle
        cv2.circle(img, (320, 240), 60, (0, 150, 255), 1)
        cv2.line(img, (320, 160), (320, 320), (0, 150, 255), 1)
        cv2.line(img, (240, 240), (400, 240), (0, 150, 255), 1)

        # Status text
        cv2.putText(img, "RTSP VIDEO STANDBY", (190, 200), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 220, 255), 2)
        cv2.putText(img, self.rtsp_url, (150, 235), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (160, 175, 190), 1)
        cv2.putText(img, message, (170, 280), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 200, 100), 1)

        ret, buffer = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 75])
        return buffer.tobytes() if ret else b''

    def _capture_loop(self):
        """Grabs frames from RTSP stream with auto-reconnection."""
        frame_counter = 0
        fps_start = time.time()

        while self._is_running:
            try:
                if self._cap is None or not self._cap.isOpened():
                    self.is_streaming = False
                    # OpenCV with FFMPEG backend for low latency RTSP
                    self._cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
                    self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

                    if not self._cap.isOpened():
                        # Wait before retry
                        with self._lock:
                            self._current_jpeg = self._generate_placeholder_frame("Connecting to drone camera...")
                        time.sleep(2.0)
                        continue

                ret, frame = self._cap.read()
                if not ret or frame is None:
                    self.is_streaming = False
                    with self._lock:
                        self._current_jpeg = self._generate_placeholder_frame("Waiting for RTSP camera stream...")
                    time.sleep(0.5)
                    continue

                self.is_streaming = True
                self.height, self.width = frame.shape[:2]
                self.last_frame_time = time.time()

                # Calculate measured FPS
                frame_counter += 1
                if time.time() - fps_start >= 1.0:
                    self.current_fps = frame_counter / (time.time() - fps_start)
                    frame_counter = 0
                    fps_start = time.time()

                # Encode frame to JPEG
                ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                if ret:
                    with self._lock:
                        self._current_jpeg = buffer.tobytes()

                time.sleep(0.01)

            except Exception as e:
                self.is_streaming = False
                with self._lock:
                    self._current_jpeg = self._generate_placeholder_frame(f"Stream exception: {str(e)[:30]}")
                time.sleep(1.0)

    def get_latest_jpeg(self) -> bytes:
        """Returns the most recent JPEG frame bytes."""
        with self._lock:
            if self._current_jpeg:
                return self._current_jpeg
            return self._generate_placeholder_frame("Camera offline")

    def mjpeg_generator(self) -> Generator[bytes, None, None]:
        """Multipart MJPEG frame generator for HTTP response."""
        while self._is_running:
            frame = self.get_latest_jpeg()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            time.sleep(0.033)  # ~30 FPS max
