#Circuitpython Gate Alarm using Seed Xiao ESP32C3

import board
import digitalio
import time

# Define the contact sensor pin
contact_sensor = digitalio.DigitalInOut(board.D3)
contact_sensor.direction = digitalio.Direction.INPUT
contact_sensor.pull = digitalio.Pull.UP  # Use a pull-up resistor

pin = digitalio.DigitalInOut(board.TX)
pin.direction = digitalio.Direction.OUTPUT

message = 'xxxxxxxxxxxxx' #1's and 0's here this will server as your passcode
sync = 'xxxxxxxxxx' #1's and 0's here'   This is the small code to wake up the receiver and synch the timing

while True:
    if contact_sensor.value:
        for bit in sync:
            pin.value = True if bit == '1' else False
            time.sleep(0.002)  # Adjusted timing
            if not contact_sensor.value:  # Check if the sensor value has changed
                break

        if contact_sensor.value:  # Check again before sending the message
            for bit in message:
                pin.value = True if bit == '1' else False
                time.sleep(0.002)  # Adjusted timing
                if not contact_sensor.value:  # Check if the sensor value has changed
                    break
    else:
        # Sleep for 1 second if the sensor is not detected
        time.sleep(1)
