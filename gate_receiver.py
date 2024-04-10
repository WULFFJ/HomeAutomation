#Gate receiver fro SRX882 connected to Rock PI 5
#Uses mraa for to open up SPIDEV
#If synch is detected and then the passcode is detected, this script uses MQTT to send a topic to Home Assistant.

import mraa
import time
import spidev
import threading
import paho.mqtt.client as mqtt

# Create a SpiDev object
spi = spidev.SpiDev()
spi.open(1, 1)
pin_GDO0 = 33
pin33 = mraa.Gpio(pin_GDO0)
pin33.dir(mraa.DIR_IN)
sync  = 'synch being sent from transmitter'
check = 'passcode from transmitter'
codes = ''
countx = 0
# MQTT setup
broker = "Name of your machine"
port = 8883 # change it to your broker's SSL port
username = "AccountName" #This is setup in HomeAssistant
password = "Gate46239$"
CA_CERTS = "/path/to/ca.crt"
CERTFILE = "/path/to/client.crt"
KEYFILE = "/path/to/client.key"
client = mqtt.Client()
client.username_pw_set(username, password) #homeassistant account setup for mqtt purposes
client.tls_set(CA_CERTS, certfile=CERTFILE, keyfile=KEYFILE)

def bitthread():
    global codes
    last_received = time.time()

    while True:
        time.sleep(0.002)
        bit = str(pin33.read())
        if bit != '':
            codes += bit
            last_received = time.time()
        elif time.time() - last_received > TIMEOUT:
            codes = ''
        if len(codes) >= 16:
            codes = codes[1:]

thread = threading.Thread(target=bitthread)
thread.start()

while True:
    time.sleep(0.001)
    print(codes)
    if codes[0:13] != sync:
        continue
    elif codes[0:13] == sync:
        print('cracked')
        while True:
            time.sleep(0.001)
            print(codes)
            if codes[0:15] !=check:
                continue
            elif codes == check:
                countx = 0
                while countx < 3:
                    print("Sending Notifications")
                    client.connect(broker, port) # connect to broker
                    client.publish("topic", "message") # publish message
                    print(str(countx * 15) + "Second Alert")
                    time.sleep(countx * 15)
                    countx += 1
                    if countx == 3:
                        client.disconnect() # disconnect from broker
                        break
            if countx == 3 and codes[0:15] == '000000000000000':
                break
