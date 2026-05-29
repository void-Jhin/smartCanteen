import json
import os
import time
from urllib import request

try:
    import serial
except ImportError:
    serial = None

SERIAL_PORT = "COM3"
BAUD_RATE = 9600
SCAN_API_URL = os.environ.get("SCAN_API_URL", "http://127.0.0.1:8000/api/scan/")


def send_latest_uid(uid: str):
    data = json.dumps({"uid": uid}).encode("utf-8")
    req = request.Request(
        SCAN_API_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=5) as response:
        response.read()


def normalize_uid(raw_uid: str) -> str:
    return raw_uid.strip().replace("\r", "").replace("\n", "")


def main():
    if serial is None:
        print("pyserial is not installed. Run: pip install pyserial")
        return

    print("Starting RFID bridge...")
    print(f"Listening on {SERIAL_PORT} at {BAUD_RATE} baud")
    print(f"Sending scans to {SCAN_API_URL}")

    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        time.sleep(2)
        print("RFID bridge connected.")

        while True:
            if ser.in_waiting > 0:
                raw = ser.readline().decode("utf-8", errors="ignore")
                uid = normalize_uid(raw)

                if uid:
                    print(f"Card detected: {uid}")
                    try:
                        send_latest_uid(uid)
                    except Exception as e:
                        print("Could not send scan:", e)

            time.sleep(0.1)

    except serial.SerialException as e:
        print("Serial error:", e)
    except KeyboardInterrupt:
        print("RFID bridge stopped.")


if __name__ == "__main__":
    main()
