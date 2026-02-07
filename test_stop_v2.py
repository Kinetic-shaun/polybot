#!/usr/bin/env python3
"""
Test script to verify Ctrl+C stopping works - using thread
"""
import subprocess
import time
import signal
import sys
import os
import threading

# Change to the app directory
os.chdir('/Users/kobe/Downloads/code/gmini_test')

def run_bot():
    """Run the bot in a subprocess"""
    proc = subprocess.Popen(
        [sys.executable, 'run_bot.py', 'copy', 'continuous'],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    return proc

def send_signal_and_wait(proc, delay=2):
    """Send SIGINT and wait for process to exit"""
    time.sleep(delay)
    print(f"Sending SIGINT to PID {proc.pid}...")
    proc.send_signal(signal.SIGINT)

    # Wait for up to 5 seconds
    for i in range(10):
        time.sleep(0.5)
        if proc.poll() is not None:
            return True
    return False

print("=== Testing Ctrl+C Stop ===")
print()

# Start the bot
proc = run_bot()
print(f"Bot started with PID: {proc.pid}")

# Send signal after 2 seconds
stopped = send_signal_and_wait(proc, delay=2)

# Get output
try:
    stdout, _ = proc.communicate(timeout=3)
    print("\n=== Bot Output (last 1000 chars) ===")
    if len(stdout) > 1000:
        print("... (truncated)")
        print(stdout[-1000:])
    else:
        print(stdout)
except subprocess.TimeoutExpired:
    print("\nTimeout waiting for output")
    proc.kill()
    stdout, _ = proc.communicate()
    print(stdout[-1000:])

print()
if stopped:
    print("SUCCESS: Bot stopped gracefully!")
else:
    print("FAILED: Bot did not stop")
    print(f"Exit code: {proc.returncode}")
