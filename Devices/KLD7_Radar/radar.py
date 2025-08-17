import os
import time
import math
import json
import logging
import threading
from queue import Queue, Empty
from datetime import datetime
from collections import deque
from kld7 import KLD7, Target
import numpy as np
from sklearn.cluster import DBSCAN
import smbus2
import paho.mqtt.client as mqtt
from paho.mqtt.client import CallbackAPIVersion

# MQTT setup
broker = "xxx.xxx.x.xxx"
port = 8883
client_id = "radar_light"
username = "radar"
password = "P@ssword"
client_key = "/home/radar/certs/client.key"
client_crt = "/home/radar/certs/client.crt"
ca_crt = "/home/radar/certs/ca.crt"

# Logging setup
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# MQTT client setup
client = mqtt.Client(client_id=client_id, callback_api_version=CallbackAPIVersion.VERSION1)
client.username_pw_set(username, password)
client.tls_set(ca_certs=ca_crt, certfile=client_crt, keyfile=client_key)
client.keepalive = 60

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connected to MQTT broker")
        publish_availability(client, "radar/data/point_0/available", "online")
        publish_availability(client, "radar/data/point_1/available", "online")
        publish_availability(client, "radar/data/point_2/available", "online")
        publish_availability(client, "radar/data/point_3/available", "online")
        publish_availability(client, "radar/data/availability", "online")
    else:
        print(f"Connect returned code {rc}")

def on_disconnect(client, userdata, rc):
    if rc != 0:
        print("Unexpected disconnection, retrying...")
        while True:
            try:
                client.tls_set(ca_certs=ca_crt, certfile=client_crt, keyfile=client_key)
                client.reconnect()
                break
            except Exception as e:
                print(f"Reconnection failed: {e}, retrying in 5 seconds...")
                time.sleep(5)

client.on_connect = on_connect
client.on_disconnect = on_disconnect

def publish_availability(client, topic, state):
    payload = {"state": state}
    client.publish(topic, json.dumps(payload), qos=1)

def convert_to_cartesian(distance, angle):
    x = distance * math.cos(math.radians(angle))
    y = distance * math.sin(math.radians(angle))
    return y, x

def calculate_distance(x1, y1, x2, y2):
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)

def average_targets(targets):
    num_targets = len(targets)
    avg_distance = sum(target.distance for target in targets) / num_targets
    avg_angle = sum(target.angle for target in targets) / num_targets
    avg_magnitude = sum(target.magnitude for target in targets) / num_targets
    return Target(avg_distance, targets[0].speed, avg_angle, avg_magnitude)

def process_targets(targets):
    if len(targets) <= 1:
        return targets

    target_coords = np.array([convert_to_cartesian(t.distance, t.angle) for t in targets])

    dbscan = DBSCAN(eps=1, min_samples=2)
    clusters = dbscan.fit_predict(target_coords)

    smoothed_targets = []
    for cluster_id in np.unique(clusters):
        if cluster_id == -1:
            continue
        cluster_points = target_coords[clusters == cluster_id]
        cluster_targets = [targets[i] for i, c in enumerate(clusters) if c == cluster_id]

        if len(cluster_points) > 0:
            avg_distance = np.mean([target.distance for target in cluster_targets])
            avg_angle = np.mean([target.angle for target in cluster_targets])
            avg_magnitude = np.mean([target.magnitude for target in cluster_targets])
            smoothed_targets.append(Target(avg_distance, cluster_targets[0].speed, avg_angle, avg_magnitude))
    return smoothed_targets

def normalize_coordinates(x, y):
    x_normalized = x * (100 / 20) + 50
    y_normalized = -y * (50 / 20) + 95
    return x_normalized, y_normalized

def set_servo_angle(bus, channel, angle, history):
    history.append(angle)
    smoothed_angle = sum(history) / len(history)
    duty_cycle = ((-1/27) * smoothed_angle) + 7.5  # Original pan formula
    pulse_width_us = duty_cycle * 20_000 / 100  # Convert duty cycle to microseconds (50Hz = 20ms period)
    pulse_width_12bit = int(pulse_width_us * 4096 / 20_000)  # Scale to 12-bit for PCA9685
    bus.write_word_data(0x40, 0x06 + 4 * channel, 0)  # LEDx_ON_L = 0
    bus.write_word_data(0x40, 0x08 + 4 * channel, pulse_width_12bit)  # LEDx_OFF_L

# PCA9685 setup using smbus2
bus = smbus2.SMBus(3)  # Use I2C Bus 4 (SCL=GPIO1_2, SDA=GPIO1_3)
bus.write_byte_data(0x40, 0x00, 0x01)  # MODE1: Enable auto-increment, sleep
freq_hz = 50
prescale = int(round(25_000_000 / (4096 * freq_hz)) - 1)
bus.write_byte_data(0x40, 0xFE, prescale)  # Set prescaler for 50Hz
bus.write_byte_data(0x40, 0x00, 0x11)  # MODE1: Enable, no sleep
time.sleep(0.01)  # Wait for oscillator to stabilize

# Connect to MQTT broker with retry logic
connected = False
while not connected:
    try:
        client.connect(broker, port)
        connected = True
    except ConnectionRefusedError:
        print("Connection refused, retrying in 5 seconds...")
        time.sleep(5)
    except Exception as e:
        print(f"Connection failed: {e}, retrying in 5 seconds...")
        time.sleep(5)

client.loop_start()

kld7 = KLD7('/dev/ttyUSB0')

RETURN_HOME_DELAY = 5.0
HOME_PAN_ANGLE = 0.0
HOME_TILT_ANGLE = 0.0  # Placeholder, adjust later
last_seen = time.time() - 100
homed = True
pan_history = deque(maxlen=5)
tilt_history = deque(maxlen=5)

try:
    param_values = {
        "ANTH": 0,
        "MARA": 100,
        "MASP": 100,
        "MISP": 0,
        "RATH": 0,
        "MAAN": 90,
        "DEDI": 2,
        "RRAI": 2,  # Change to 3 for 100m
        "RSPI": 1,
        "MIRA": 0,
        "MIAN": -90,
        "HOLD": 1,
        "MIDE": 1,
        "MIDS": 4,
        "RBFR": 1,
        "TRFT": 0,
        "VISU": 2,
        "THOF": 30,
        "SPTH": 0,
    }
    for name, value in param_values.items():
        kld7.set_param(name, value)
    logging.info("KLD7 parameters set via 'set_param' for each field.")
except Exception as e:
    logging.error(f"Failed to set KLD7 parameters: {e}")


try:
    while True:
        try:
            now = time.time()
            data = kld7.read_PDAT()
            if data:
                logging.info(f"Received data: {data}")
                processed_targets = process_targets(data)

                for i, target in enumerate(processed_targets[:4]):
                    x_cartesian, y_cartesian = convert_to_cartesian(target.distance, target.angle)
                    x_normalized, y_normalized = normalize_coordinates(x_cartesian, y_cartesian)
                    payload = {"x": x_normalized, "y": y_normalized}
                    logging.info(f"Publishing to radar/data/point_{i}: {payload}")
                    client.publish(f"radar/data/point_{i}", json.dumps(payload), qos=1)

                if processed_targets:
                    last_seen = now
                    homed = False
                    pan_angle = processed_targets[0].angle
                    set_servo_angle(bus, 0, pan_angle, pan_history)
                    tilt_angle = 0.0  # Placeholder for tilt calculation (e.g., based on distance, speed, etc.)
                    set_servo_angle(bus, 1, tilt_angle, tilt_history)

            if now - last_seen > RETURN_HOME_DELAY:
                if not homed:
                    set_servo_angle(bus, 0, HOME_PAN_ANGLE, pan_history)
                    set_servo_angle(bus, 1, HOME_TILT_ANGLE, tilt_history)
                    homed = True

        except OSError as e:
            logging.error(f"Serial port error: {e}")
            publish_availability(client, "radar/data/availability", "offline")
            time.sleep(5)
            try:
                kld7 = KLD7('/dev/ttyUSB0')
            except Exception as e:
                logging.error(f"Failed to reinitialize kld7: {e}")
                pass
        except Exception as e:
            logging.error(f"General exception: {e}")
            publish_availability(client, "radar/data/availability", "offline")

        time.sleep(0.2)

except KeyboardInterrupt:
    logging.info("Script interrupted by user")
finally:
    client.loop_stop()
    client.disconnect()
    bus.close()
