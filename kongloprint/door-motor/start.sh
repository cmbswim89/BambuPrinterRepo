#!/usr/bin/env bash
set -euo pipefail

echo "[start] ensure /dev nodes exist"
modprobe vcio 2>/dev/null || true
for _ in $(seq 1 60); do
  [ -e /dev/gpiomem ] && [ -e /dev/vcio ] && break
  sleep 0.25
done
ls -l /dev/gpiomem /dev/vcio || true

echo "[start] start pigpio daemon"
pkill pigpiod 2>/dev/null || true
pigpiod -g -p 8888

echo "[start] verify daemon"
python3 - <<'PY'
import time, pigpio, sys
ok=False
for _ in range(10):
    pi=pigpio.pi()  # localhost:8888
    if pi.connected:
        ok=True; pi.stop(); break
    time.sleep(0.3)
print("daemon_connected:", ok)
sys.exit(0 if ok else 1)
PY

echo "[start] launch app"
exec python3 /usr/src/app/door-motor.py
