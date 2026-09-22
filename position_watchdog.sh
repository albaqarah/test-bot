#!/bin/bash
# Watchdog posisi terbuka: cek tiap 20 detik — SL/TP/BE real-time + notif exit instan
while true; do
  cd /home/agentuser
  python3 dewa_live.py --watch >> /home/agentuser/dewa_watchdog.log 2>&1
  sleep 20
done
