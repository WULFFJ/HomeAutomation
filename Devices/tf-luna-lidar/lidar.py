from umqttsimple.umqttsimple import MQTTClient
import network         
import ussl as ssl          # as both ssl and ussl seem to happily work here
import utime
import time
import machine
import lidar

SSID = 'xxxxxx'
PASSWORD = 'xxxxxxxxxx'
broker_username = 'xxxxxxx' 
broker_password = 'xxxxxxxxx'
server='xxxxxxxxxx'      #machinename.local
server_port=8883
server_keepalive=60     # if you don't include a keepalive nothing works.
mqtt_topic= '#########'
local_client_name='XXXXXXXx'

class const:
    DIST_LOW = 0x00
    AMP_LOW = 0x01
    TEMP_LOW = 0x02
    VERSION_REVISION = 0x03
    FPS_LOW = 0x04
    LOW_POWER = 0x05
    ENABLE = 0x06
    SAVE = 0x07
    SHUTDOWN_REBOOT = 0x08
    RESTORE_FACTORY_DEFAULTS = 0x09
    MIN_DIST_HIGH = 0x0A
    MIN_DIST_LOW = 0x0B
    MAX_DIST_HIGH = 0x0C
    MAX_DIST_LOW = 0x0D

def connect_wifi():
    while True:
        try:
            wlan = network.WLAN(network.STA_IF)
            wlan.active(True)
            wlan.connect(SSID, PASSWORD)
            while not wlan.isconnected():
                print('Connecting to WiFi...')
                time.sleep(1)
            print('Connected to WiFi:', wlan.ifconfig())
            break
        except Exception as e:
            print("WiFi connection failed:", e)
            time.sleep(5)

def connectMQTT():
    while True:
        try:
            client = MQTTClient(
                client_id=local_client_name,
                server=server,
                port=server_port,
                user=broker_username,
                password=broker_password,
                keepalive=server_keepalive,
                ssl=True,
                ssl_params=ssl_params
            )
            client.connect()
            return client
        except Exception as e:
            print("MQTT connection failed:", e)
            time.sleep(5)

connect_wifi()

with open('/cert/ca.pem', 'rb') as f:
    ca_data = f.read()
f.close()
print('Read CA Certificate... OK')

with open('/cert/client.pem', 'rb') as f:
    user_cert = f.read()
f.close()
print('Read User Certificate... OK')

with open('/cert/client-key.pem', 'rb') as f:
    user_key = f.read()
f.close()
print('Read User Key... OK')

ssl_params = {
    'key': user_key,
    'cert': user_cert,
    'cadata': ca_data
}

client = connectMQTT()
print("Connected to MQTT Server")
i2c = machine.I2C(0, scl=machine.Pin(7), sda=machine.Pin(6))
lidar_sensor = lidar.LIDAR(i2c, 0x10)
print("LIDAR Sensor initialized")

# Set minimum and maximum distance
lidar_sensor.set_min_max(0, 800)  # Set min to 0 cm and max to 800 cm
print("Min and Max distances set")

while True:
    try:
        distance = lidar_sensor.distance()
        print("Distance: {} cm".format(distance))
        
        if distance < 240:
            client.publish(topic=mqtt_topic, msg="Invader")
            print("Published 'Invader' to topic:", mqtt_topic)
        
    except Exception as e:
        print("Error reading LIDAR sensor or publishing to MQTT:", e)
        # Attempt to reconnect to WiFi and MQTT
        connect_wifi()
        client = connectMQTT()
    
    utime.sleep(1)



