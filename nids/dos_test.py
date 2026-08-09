import socket
import threading
import time

# Apne local system ki IP ya Loopback target karein
TARGET_IP = "192.168.29.47"  
TARGET_PORT = 80             # Kisi bhi open/closed port par bhej sakte hain
NUM_THREADS = 50             # Parallel connections count

payload = b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n"

def send_traffic():
    while True:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.05)
            s.connect((TARGET_IP, TARGET_PORT))
            s.send(payload)
            s.close()
        except Exception:
            pass

print(f"🚀 Starting High-Volume Traffic Surge on {TARGET_IP}:{TARGET_PORT}...")
print("Press Ctrl+C in terminal to stop.")

# Multi-threaded execution for traffic burst
for i in range(NUM_THREADS):
    t = threading.Thread(target=send_traffic, daemon=True)
    t.start()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\n🛑 Traffic simulation stopped.")