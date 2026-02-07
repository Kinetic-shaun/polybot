#!/usr/bin/env python3
"""
Test script to verify Ctrl+C stopping works
"""
import subprocess
import time
import signal
import sys
import os

# Change to the app directory
os.chdir('/Users/kobe/Downloads/code/gmini_test')

# Start the bot in the background
print("Starting bot...")
proc = subprocess.Popen(
    [sys.executable, 'run_bot.py', 'copy', 'continuous'],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1
)

# Wait for bot to start
time.sleep(3)

print("Sending SIGINT to stop the bot...")
proc.send_signal(signal.SIGINT)

# Wait for the process to stop
try:
    stdout, _ = proc.communicate(timeout=10)
    print("\n=== Bot Output ===")
    print(stdout)
    print(f"\nExit code: {proc.returncode}")
    if proc.returncode == 0 or proc.returncode == -2:  # -2 is SIGINT
        print("SUCCESS: Bot stopped gracefully!")
    else:
        print("FAILED: Bot did not stop gracefully")
except subprocess.TimeoutExpired:
    print("FAILED: Bot did not stop within 10 seconds")
    proc.kill()
