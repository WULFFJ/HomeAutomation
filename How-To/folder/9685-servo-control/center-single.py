# center_servo.py
import time
from adafruit_pca9685 import PCA9685
import busio
from board import SCL, SDA

# I2C + PCA9685 @ 50 Hz
i2c = busio.I2C(SCL, SDA)
pca = PCA9685(i2c)
pca.frequency = 50

# Channel & 1500 µs center pulse
CH = 1
CENTER_US = 1500

# Convert µs → 16-bit duty cycle
def us_to_duty(us):
    return int(us * pca.frequency * 65535 / 1_000_000)

print("Driving 1500 µs (center). Reposition horn, then Ctrl-C to exit.")
pca.channels[CH].duty_cycle = us_to_duty(CENTER_US)
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pca.channels[CH].duty_cycle = 0
    print("Done. Horn should now be at mid-travel.")
