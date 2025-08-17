#!/usr/bin/env python3
import RPi.GPIO as GPIO
import time

GATE = 24       # BCM pin 24 (physical pin 18)
ON_TIME = 2.5   # seconds high
OFF_TIME = 2.5  # seconds low

GPIO.setmode(GPIO.BCM)
GPIO.setup(GATE, GPIO.OUT, initial=GPIO.LOW)

try:
    while True:
        GPIO.output(GATE, GPIO.HIGH)
        time.sleep(ON_TIME)
        GPIO.output(GATE, GPIO.LOW)
        time.sleep(OFF_TIME)
except KeyboardInterrupt:
    pass
finally:
    GPIO.cleanup()
