#MicroPython
#Generic reed switch test
#Reed switch between ground and GPIO5
#Prints 1s or 0s depending on the state of the switch using a magnet
#Using a Wemos D1 Mini

import machine
import time

# Setup a GPIO Pin for the reed switch
reed_switch = machine.Pin(5, machine.Pin.IN)

while True:
    # read reed switch
    switch_state = reed_switch.value()
    
    # print switch state
    print("Reed Switch State: ", switch_state)
    
    # delay between reads
    time.sleep(1)
