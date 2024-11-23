#Circuitpython Gate Alarm using Seed Xiao ESP32C3

import board
import digitalio
import time

# Define the contact sensor pin
contact_sensor = digitalio.DigitalInOut(board.D4)
contact_sensor.direction = digitalio.Direction.INPUT
contact_sensor.pull = digitalio.Pull.UP  # Use a pull-up resistor

# Define the output pin
pin = digitalio.DigitalInOut(board.D6)
pin.direction = digitalio.Direction.OUTPUT

message = 'xxxxxxx' #1's and 0's here this will server as your passcode
sync = 'xxxxxxxxxxx' #1's and 0's here'   This is the small code to wake up the receiver and synch the timing

while True:
    # Check if the contact sensor is detected
    if not contact_sensor.value:  # Changed this line
        # Send the sync signal
        for bit in sync:
            pin.value = True if bit == '1' else False
            time.sleep(0.002)  # Adjusted timing

        # Send the message
        for bit in message:
            pin.value = True if bit == '1' else False
            time.sleep(0.002)  # Adjusted timing
    else:
        # Print a message if the contact sensor is not detected
        print("Contact sensor is not detected.")
        # Sleep for 1 second if the sensor is not detected
        time.sleep(1)
    else:
        # Sleep for 1 second if the sensor is not detected
        time.sleep(1)
