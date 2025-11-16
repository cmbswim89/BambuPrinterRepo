#!/usr/bin/env bash
set -euo pipefail

echo "[pigpio] ensuring devices exist"
modprobe vcio 2>/dev/null || true

# wait for /dev nodes after boot
for _ in $(seq 1 60); do
  [[ -e /dev/gpiomem && -e /dev/vcio ]] && break
  sleep 0.25
done
ls -l /dev/gpiomem /dev/vcio || true

echo "[pigpio] starting pigpiod on 0.0.0.0:8888 (using gpiomem)"
pkill pigpiod 2>/dev/null || true
pigpiod -g -p 8888

echo "[pigpio] running"
sleep infinity
