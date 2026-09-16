#!/usr/bin/env bash
set -euo pipefail
count="${1:-1}"
for i in $(seq 1 "$count"); do
  emulator -avd "pixel_$i" -no-window -no-audio &
done
adb wait-for-device
