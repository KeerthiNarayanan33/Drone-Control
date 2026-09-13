"""
Interactive Step-by-Step Flight Controls Verification Tool (Phase 4)
Safely tests manual flight commands one at a time on real drone hardware
and records PASS / FAIL results directly into DRONE_TEST_REPORT.md.
"""

import time
import re
import argparse
from datetime import datetime
from drone_comm import (
    DroneControllerCore,
    NEUTRAL_STICK_VALUE,
    DEFAULT_DRONE_IP,
    DEFAULT_CONTROL_PORT,
    FLAG_UNLOCK_TAKEOFF,
    FLAG_FAST_DROP,
    FLAG_EMERGENCY_STOP
)

TEST_COMMANDS = [
    {
        "id": "hover",
        "name": "Stop / Hover (Neutral)",
        "desc": "Sticks neutral (128, 128, 128, 128, 0)",
        "duration": 2.0,
        "action": lambda c: c.set_sticks(128, 128, 128, 128)
    },
    {
        "id": "takeoff",
        "name": "Takeoff",
        "desc": "Motors arm & auto-takeoff (Flags Bit 5: 0x20)",
        "duration": 1.5,
        "action": lambda c: c.trigger_takeoff()
    },
    {
        "id": "land",
        "name": "Land",
        "desc": "Auto-land / descent (Flags Bit 1: 0x02)",
        "duration": 2.0,
        "action": lambda c: c.trigger_land()
    },
    {
        "id": "emergency",
        "name": "Emergency Stop",
        "desc": "Instant rotor kill switch (Flags Bit 2: 0x04)",
        "duration": 1.0,
        "action": lambda c: c.trigger_emergency_stop()
    },
    {
        "id": "forward",
        "name": "Forward",
        "desc": "Pitch forward pulse (Pitch = 170, 1.5s)",
        "duration": 1.5,
        "action": lambda c: c.set_sticks(128, 170, 128, 128)
    },
    {
        "id": "backward",
        "name": "Backward",
        "desc": "Pitch backward pulse (Pitch = 86, 1.5s)",
        "duration": 1.5,
        "action": lambda c: c.set_sticks(128, 86, 128, 128)
    },
    {
        "id": "left",
        "name": "Left",
        "desc": "Roll bank left pulse (Roll = 86, 1.5s)",
        "duration": 1.5,
        "action": lambda c: c.set_sticks(86, 128, 128, 128)
    },
    {
        "id": "right",
        "name": "Right",
        "desc": "Roll bank right pulse (Roll = 170, 1.5s)",
        "duration": 1.5,
        "action": lambda c: c.set_sticks(170, 128, 128, 128)
    },
    {
        "id": "up",
        "name": "Up",
        "desc": "Throttle rise pulse (Throttle = 170, 1.5s)",
        "duration": 1.5,
        "action": lambda c: c.set_sticks(128, 128, 170, 128)
    },
    {
        "id": "down",
        "name": "Down",
        "desc": "Throttle descend pulse (Throttle = 86, 1.5s)",
        "duration": 1.5,
        "action": lambda c: c.set_sticks(128, 128, 86, 128)
    },
    {
        "id": "rotate_left",
        "name": "Rotate Left",
        "desc": "Yaw counter-clockwise (Yaw = 86, 1.5s)",
        "duration": 1.5,
        "action": lambda c: c.set_sticks(128, 128, 128, 86)
    },
    {
        "id": "rotate_right",
        "name": "Rotate Right",
        "desc": "Yaw clockwise (Yaw = 170, 1.5s)",
        "duration": 1.5,
        "action": lambda c: c.set_sticks(128, 128, 128, 170)
    }
]

def update_report(command_name: str, status: str, notes: str):
    """Updates DRONE_TEST_REPORT.md with verified result."""
    report_file = "DRONE_TEST_REPORT.md"
    try:
        with open(report_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Regex replace table line
        pattern = rf"(\|\s*\*\*?{re.escape(command_name)}\*\*?\s*\|)([^|]+)(\|)([^|]*)(\|)"
        replacement = rf"\1 {status:<10} \3 {notes:<30} \5"
        new_content = re.sub(pattern, replacement, content, flags=re.IGNORECASE)

        with open(report_file, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"[REPORT UPDATED] Marked '{command_name}' as {status} in {report_file}")
    except Exception as e:
        print(f"[WARNING] Could not update {report_file}: {e}")

def run_single_test(controller: DroneControllerCore, test_item: dict):
    print("\n" + "-" * 70)
    print(f"COMMAND TEST: {test_item['name'].upper()}")
    print(f"Description : {test_item['desc']}")
    print(f"Duration    : {test_item['duration']} seconds (then auto-neutral)")
    print("-" * 70)

    resp = input("Ready to transmit command to drone? (y/n/skip): ").strip().lower()
    if resp in ["skip", "s", "n"]:
        print("Skipped.")
        return

    print(">>> TRANSMITTING COMMAND PULSE...")
    test_item["action"](controller)

    # Let the command run for the duration
    start = time.time()
    while time.time() - start < test_item["duration"]:
        time.sleep(0.05)
        st = controller.get_status()
        print(f"\rSending: {st['last_sent_hex']} | Elapsed: {time.time()-start:.1f}s", end="")
    print("\n>>> RETURNING TO NEUTRAL FAILSAFE (128, 128, 128, 128, 0)...")
    controller.set_sticks(128, 128, 128, 128)
    controller.set_flags(0)
    time.sleep(0.5)

    result = input(f"Did '{test_item['name']}' respond correctly on real hardware? (y = PASS, n = FAIL, any key = SKIP): ").strip().lower()
    if result == "y":
        note = input("Add test note (or press Enter for default): ").strip()
        update_report(test_item["name"], "PASS", note or f"Verified on real drone ({datetime.now().strftime('%Y-%m-%d %H:%M')})")
    elif result == "n":
        note = input("Enter failure reason: ").strip()
        update_report(test_item["name"], "FAIL", note or "No expected physical movement observed")
    else:
        print("Left as NOT TESTED.")

def main():
    parser = argparse.ArgumentParser(description="Drone Flight Controls Test Runner (Phase 4)")
    parser.add_argument("--ip", default=DEFAULT_DRONE_IP, help=f"Drone IP (default: {DEFAULT_DRONE_IP})")
    parser.add_argument("--port", type=int, default=DEFAULT_CONTROL_PORT, help=f"Port (default: {DEFAULT_CONTROL_PORT})")
    args = parser.parse_args()

    print("=" * 70)
    print("      DRONE FLIGHT CONTROLS STEP-BY-STEP VERIFICATION (PHASE 4)")
    print("=" * 70)
    print("SAFETY NOTICE:")
    print("- Ensure the drone is in an open, obstacle-free space.")
    print("- Ensure propellers are clear of hands and objects.")
    print("- Keep hands ready near the physical drone or Emergency Stop.")
    print("=" * 70)

    controller = DroneControllerCore(drone_ip=args.ip, control_port=args.port)
    if not controller.connect():
        print("[ERROR] Could not establish UDP socket.")
        return

    try:
        while True:
            print("\nAvailable Commands:")
            for i, cmd in enumerate(TEST_COMMANDS, 1):
                print(f"  [{i:2d}] {cmd['name']:<20} - {cmd['desc']}")
            print("  [ A] Run All Sequentially")
            print("  [ Q] Quit")

            choice = input("\nSelect command to test (1-12, A, Q): ").strip().upper()
            if choice == "Q":
                break
            elif choice == "A":
                for cmd in TEST_COMMANDS:
                    run_single_test(controller, cmd)
            elif choice.isdigit() and 1 <= int(choice) <= len(TEST_COMMANDS):
                run_single_test(controller, TEST_COMMANDS[int(choice) - 1])
            else:
                print("Invalid choice.")
    finally:
        controller.disconnect()
        print("\nController disconnected. Safe power-down.")

if __name__ == "__main__":
    main()
