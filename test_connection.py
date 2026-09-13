"""
Minimal Drone Connection Test Utility (Phase 3)
Verifies physical UDP communication and keep-alive heartbeats with the real drone.

Displays:
- Connection status
- Drone / network information
- Real-time developer log (timestamp, command, packet hex, response, error)
- Communication metrics (packets sent/received, round-trip notes)
"""

import sys
import time
import socket
import subprocess
import argparse
from datetime import datetime
from drone_comm import DroneControllerCore, DEFAULT_DRONE_IP, DEFAULT_CONTROL_PORT, HEARTBEAT_PAYLOAD

def check_local_network() -> str:
    """Detects local IPv4 addresses on the host system."""
    try:
        # Create dummy socket to find local outbound IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.168.1.1", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception:
        return "127.0.0.1 (No direct route to 192.168.1.1 detected)"

def ping_drone(ip: str, count: int = 1) -> bool:
    """Attempts ICMP ping to the drone gateway."""
    try:
        param = "-n" if sys.platform.startswith("win") else "-c"
        result = subprocess.run(
            ["ping", param, str(count), "-w", "1000", ip],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return result.returncode == 0
    except Exception:
        return False

def print_banner(drone_ip: str, port: int, local_ip: str):
    print("=" * 80)
    print("           DRONE CONNECTION & HEARTBEAT TEST (PHASE 3)")
    print("=" * 80)
    print(f"Target Drone IP   : {drone_ip}")
    print(f"Control UDP Port  : {port}")
    print(f"Local Host IP     : {local_ip}")
    print(f"Target Video RTSP : rtsp://{drone_ip}:7070/webcam")
    print(f"Heartbeat Protocol: [0x01, 0x01] (1 Hz keep-alive)")
    print("=" * 80)
    print(f"{'TIMESTAMP':<12} | {'COMMAND / EVENT':<20} | {'HEX DATA':<24} | {'STATUS / NOTES'}")
    print("-" * 80)

def main():
    parser = argparse.ArgumentParser(description="Drone Minimal Connection Test (Phase 3)")
    parser.add_argument("--ip", default=DEFAULT_DRONE_IP, help=f"Drone IP (default: {DEFAULT_DRONE_IP})")
    parser.add_argument("--port", type=int, default=DEFAULT_CONTROL_PORT, help=f"Control Port (default: {DEFAULT_CONTROL_PORT})")
    parser.add_argument("--duration", type=int, default=15, help="Test duration in seconds (default: 15)")
    args = parser.parse_args()

    local_ip = check_local_network()
    print_banner(args.ip, args.port, local_ip)

    # Initial ICMP check
    ping_ok = ping_drone(args.ip)
    ts_now = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    if ping_ok:
        print(f"{ts_now:<12} | {'ICMP Ping':<20} | {'ECHO REQUEST':<24} | PASS (Host 192.168.1.1 is reachable)")
    else:
        print(f"{ts_now:<12} | {'ICMP Ping':<20} | {'ECHO REQUEST':<24} | NOTE: Ping failed or filtered (normal on some drone firmware)")

    # Developer logger callback
    def dev_logger(level: str, msg: str, meta: dict):
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        hex_data = meta.get("hex", "")
        print(f"{ts:<12} | {level:<20} | {hex_data:<24} | {msg}")

    controller = DroneControllerCore(drone_ip=args.ip, control_port=args.port, log_callback=dev_logger)

    print(f"{datetime.now().strftime('%H:%M:%S.%f')[:-3]:<12} | {'Socket Init':<20} | {'UDP BIND':<24} | Opening UDP communication channel...")
    success = controller.connect()
    if not success:
        print("\n[ERROR] Failed to open UDP socket. Please check network permissions.")
        return

    print(f"{datetime.now().strftime('%H:%M:%S.%f')[:-3]:<12} | {'Channel Open':<20} | {'UDP ACTIVE':<24} | Emitting heartbeats & neutral stream (20Hz)...")

    start_time = time.time()
    try:
        while time.time() - start_time < args.duration:
            time.sleep(1.0)
            status = controller.get_status()
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            sent = status["packets_sent"]
            recv = status["packets_recv"]
            hb = status["heartbeats_sent"]
            last_sent = status["last_sent_hex"]
            last_recv = status["last_recv_hex"] or "Awaiting reply..."

            print(f"{ts:<12} | {'Keep-Alive Status':<20} | {last_sent:<24} | Sent: {sent} (HB: {hb}), Recv: {recv} [{last_recv}]")

    except KeyboardInterrupt:
        print("\n[TEST INTERRUPTED BY USER]")
    finally:
        controller.disconnect()

    print("\n" + "=" * 80)
    print("                           TEST SUMMARY")
    print("=" * 80)
    final_status = controller.get_status()
    print(f"Total Heartbeats Emitted : {final_status['heartbeats_sent']}")
    print(f"Total Flight Packets Sent: {final_status['packets_sent']}")
    print(f"Total Packets Received   : {final_status['packets_recv']}")
    if final_status['packets_recv'] > 0:
        print(f"Inbound Data Received    : {final_status['last_recv_hex']} (CONFIRMED BIDIRECTIONAL CONNECTION)")
    else:
        print("Inbound Data Received    : None (Standard unidirectional or drone waiting for Wi-Fi association)")
    print("=" * 80)
    print("Connection test completed.\n")

if __name__ == "__main__":
    main()
