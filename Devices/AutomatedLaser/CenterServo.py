#!/usr/bin/env python3

import time
import board
###Fixed servo center to custom value###
import busio
from adafruit_pca9685 import PCA9685

# ——— Configuration ——————————————————————————————————
CHANNEL      = 1       # change to your servo channel (0–15)
CENTER_US    = 1600    # microseconds for electrical center
FREQUENCY_HZ = 50      # standard servo PWM frequency

# ——— Helper: convert µs → 16-bit duty cycle ——————————————————
def us_to_duty(us: int, freq: int) -> int:
    # (us * freq * 65535) / 1_000_000
    return int(us * freq * 65535 // 1_000_000)

# ——— Main ————————————————————————————————————————
def main():
    # init I2C + PCA9685
    i2c = busio.I2C(board.SCL, board.SDA)
    pca = PCA9685(i2c)
    pca.frequency = FREQUENCY_HZ

    # drive center pulse
    duty = us_to_duty(CENTER_US, FREQUENCY_HZ)
    print(f"Writing {CENTER_US} µs → duty_cycle={duty}")
    pca.channels[CHANNEL].duty_cycle = duty

    # hold for a bit so you can re-mount horn
    time.sleep(2.0)

    # stop output cleanly
    pca.channels[CHANNEL].duty_cycle = 0
    pca.deinit()
    print("Done.")

if __name__ == "__main__":
    main()
