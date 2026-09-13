"""
Unit tests for Drone Protocol & Communication Layer.
Verifies packet construction, checksum math, bitmask flags, and safety limits.
"""

import unittest
from drone_comm import (
    DroneControllerCore,
    NEUTRAL_STICK_VALUE,
    FLAG_UNLOCK_TAKEOFF,
    FLAG_FAST_DROP,
    FLAG_EMERGENCY_STOP,
    FLAG_GYRO_CALIBRATE,
    FLAG_FAST_FLY,
    MAGIC_BYTE_PREFIX,
    MAGIC_BYTE_START,
    MAGIC_BYTE_END
)

class TestDroneProtocol(unittest.TestCase):

    def setUp(self):
        self.controller = DroneControllerCore()

    def test_checksum_calculation(self):
        # 128 ^ 128 ^ 128 ^ 128 ^ 0 = 0
        cs1 = DroneControllerCore.calculate_checksum(128, 128, 128, 128, 0)
        self.assertEqual(cs1, 0)

        # 100 ^ 150 ^ 128 ^ 200 ^ 0x20
        # 100 = 0x64, 150 = 0x96, 128 = 0x80, 200 = 0xC8, 0x20 = 32
        # 0x64 ^ 0x96 = 0xF2
        # 0xF2 ^ 0x80 = 0x72
        # 0x72 ^ 0xC8 = 0xBA
        # 0xBA ^ 0x20 = 0x9A = 154
        cs2 = DroneControllerCore.calculate_checksum(100, 150, 128, 200, 0x20)
        self.assertEqual(cs2, 154)

    def test_neutral_flight_packet(self):
        packet = self.controller.build_flight_packet(128, 128, 128, 128, 0)
        self.assertEqual(len(packet), 9)
        self.assertEqual(packet[0], MAGIC_BYTE_PREFIX)  # 0x03
        self.assertEqual(packet[1], MAGIC_BYTE_START)   # 0x66
        self.assertEqual(packet[2], 128)                # Roll
        self.assertEqual(packet[3], 128)                # Pitch
        self.assertEqual(packet[4], 128)                # Throttle
        self.assertEqual(packet[5], 128)                # Yaw
        self.assertEqual(packet[6], 0)                  # Flags
        self.assertEqual(packet[7], 0)                  # Checksum
        self.assertEqual(packet[8], MAGIC_BYTE_END)     # 0x99

    def test_takeoff_packet(self):
        packet = self.controller.build_flight_packet(128, 128, 128, 128, FLAG_UNLOCK_TAKEOFF)
        self.assertEqual(packet[6], 0x20)
        self.assertEqual(packet[7], 0x20)  # Checksum = 0 ^ 0x20 = 0x20
        self.assertEqual(packet[8], 0x99)

    def test_land_packet(self):
        packet = self.controller.build_flight_packet(128, 128, 128, 128, FLAG_FAST_DROP)
        self.assertEqual(packet[6], 0x02)
        self.assertEqual(packet[7], 0x02)

    def test_emergency_stop_packet(self):
        packet = self.controller.build_flight_packet(128, 128, 0, 128, FLAG_EMERGENCY_STOP)
        # 128 ^ 128 ^ 0 ^ 128 ^ 0x04 = 128 ^ 4 = 132 (0x84)
        self.assertEqual(packet[4], 0)     # Throttle cut
        self.assertEqual(packet[6], 0x04)  # Emergency flag
        self.assertEqual(packet[7], 132)   # Checksum

    def test_stick_clamping(self):
        # Exceeding 255 should clamp to 255
        packet = self.controller.build_flight_packet(300, -50, 500, 0, 0)
        self.assertEqual(packet[2], 255)
        self.assertEqual(packet[3], 1)
        self.assertEqual(packet[4], 255)
        self.assertEqual(packet[5], 1)

    def test_yaw_firmware_deadband(self):
        # Values in [104, 152] should snap to 128
        _, _, _, y1 = self.controller._apply_safety_limits(128, 128, 128, 110)
        self.assertEqual(y1, 128)
        _, _, _, y2 = self.controller._apply_safety_limits(128, 128, 128, 150)
        self.assertEqual(y2, 128)
        # Value outside deadband should not snap to 128
        _, _, _, y3 = self.controller._apply_safety_limits(128, 128, 128, 180)
        self.assertNotEqual(y3, 128)

if __name__ == '__main__':
    unittest.main()
