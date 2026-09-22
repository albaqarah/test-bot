#!/bin/bash
# dewa_supervisor.sh — njaga bot tetep hidup. Kalau proses mati/hang-dibunuh → restart dalam 5 detik.
cd /home/agentuser
while true; do
  echo "[supervisor] start dewa_live $(date '+%H:%M:%S')" >> dewa_supervisor.log
  python3 dewa_live.py >> dewa_loop.log 2>&1
  CODE=$?
  echo "[supervisor] dewa_live mati exit=$CODE $(date '+%H:%M:%S') — restart 5s" >> dewa_supervisor.log
  sleep 5
done
