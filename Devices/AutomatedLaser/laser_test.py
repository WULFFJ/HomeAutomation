#!/usr/bin/env python3
import RPi.GPIO as GPIO
import time
import signal

LASER_PIN = 21
running = True

GPIO.setmode(GPIO.BCM)
GPIO.setup(LASER_PIN, GPIO.OUT)
GPIO.output(LASER_PIN, GPIO.LOW)

def handle_shutdown(signum, frame):
    global running
    print("\nShutdown signal received...")
    running = False

signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)

print("Laser test: 1 second ON / 1 second OFF")
print("Press Ctrl+C to stop safely")

try:
    i = 1
    while running and i <= 100:
        print(f"Cycle {i}/100 - ON")
        GPIO.output(LASER_PIN, GPIO.HIGH)
        time.sleep(1)

        print(f"Cycle {i}/100 - OFF")
        GPIO.output(LASER_PIN, GPIO.LOW)
        time.sleep(1)

        i += 1

finally:
    print("Turning laser OFF and cleaning up GPIO...")
    GPIO.output(LASER_PIN, GPIO.LOW)
    GPIO.cleanup()
    print("GPIO cleaned up. Exiting.")
