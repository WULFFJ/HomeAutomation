#!/usr/bin/env python3

import RPi.GPIO as GPIO
import time

PAN_PIN = 18
PWM_FREQ = 50
PAN_CENTER = 70.5
PAN_MIN_PULSE = 500.0
PAN_MAX_PULSE = 1544.387

GPIO.setmode(GPIO.BCM)
GPIO.setup(PAN_PIN, GPIO.OUT)
pan_pwm = GPIO.PWM(PAN_PIN, PWM_FREQ)

def angle_to_duty_cycle(angle, min_pulse, max_pulse, fov):
    pulse_width = min_pulse + (angle * (max_pulse - min_pulse) / fov)
    return (pulse_width / 1000000.0) * PWM_FREQ * 100

def set_servo_angle(pwm, angle, min_pulse, max_pulse, fov):
    angle = max(0, min(angle, fov))
    duty_cycle = angle_to_duty_cycle(angle, min_pulse, max_pulse, fov)
    pwm.ChangeDutyCycle(duty_cycle)

try:
    pan_pwm.start(0)  # Start with 0% duty cycle
    time.sleep(1) # wait one second
    set_servo_angle(pan_pwm, PAN_CENTER, PAN_MIN_PULSE, PAN_MAX_PULSE, 141.0) # move to center.
    time.sleep(5) # hold the center for 5 seconds.
    pan_pwm.ChangeDutyCycle(0) #stop sending a signal.
    time.sleep(1)
    GPIO.output(PAN_PIN, GPIO.LOW) # set the pin low.
    time.sleep(1)
    print("Servo centered and stopped.")

except KeyboardInterrupt:
    pan_pwm.stop()
    GPIO.cleanup()
    print("Servo control stopped.")

finally:
    pan_pwm.stop()
    GPIO.cleanup()
