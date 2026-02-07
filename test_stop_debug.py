#!/usr/bin/env python3
"""
Debug test script to check signal handling
"""
import subprocess
import time
import signal
import sys
import os

# Change to the app directory
os.chdir('/Users/kobe/Downloads/code/gmini_test')

print("=== Signal Check ===")
print(f"Python PID: {os.getpid()}")
print(f"SIGINT handler: {signal.getsignal(signal.SIGINT)}")
print()

# Start the bot in the background
print("Starting bot in background...")
proc = subprocess.Popen(
    [sys.executable, 'run_bot.py', 'copy', 'continuous'],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1
)

bot_pid = proc.pid
print(f"Bot PID: {bot_pid}")
print()

# Wait for bot to start
time.sleep(3)

# Check what signals are being handled
print(f"Checking signal handler for bot (PID {bot_pid})...")
import ctypes
libc = ctypes.CDLL("libc.dylib", use_errno=True)

# Try to read the signal handler (this is tricky on macOS)
print("Sending SIGINT...")
proc.send_signal(signal.SIGINT)

# Give it a moment
time.sleep(2)

# Check if process is still running
if proc.poll() is None:
    print(f"Process still running after 2 seconds")

    # Send another signal
    print("Sending SIGINT again...")
    proc.send_signal(signal.SIGINT)
    time.sleep(2)

    if proc.poll() is None:
        print("Still running, sending SIGTERM...")
        proc.send_signal(signal.SIGTERM)
        time.sleep(2)

        if proc.poll() is None:
            print("Still running, force killing...")
            proc.kill()
            print("Process killed")
else:
    print(f"Process exited with code: {proc.returncode}")

# Get output
try:
    stdout, _ = proc.communicate(timeout=5)
    print("\n=== Bot Output ===")
    # Only print last 500 chars
    if len(stdout) > 500:
        print("... (truncated)")
        print(stdout[-500:])
    else:
        print(stdout)
except:
    print("(No output available)")
