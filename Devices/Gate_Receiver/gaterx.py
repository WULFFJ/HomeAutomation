### HC-12 as a Gate Receiver for HomeAssistant
import time
import serial
import paho.mqtt.client as mqtt

# ==========================================
# USER SETTINGS - EDIT THESE
# ==========================================

# Pi 5 HC-12 receiver
SERIAL_PORT = "/dev/ttyAMA4"
BAUD_RATE = 9600

# MQTT broker
MQTT_BROKER = "YOURBROKERIPLOCAL"
MQTT_PORT = 8883
MQTT_USERNAME = "Gate"
MQTT_PASSWORD = "YOURPASSWORDHERE"

# Existing MQTT certificates
CA_CERTS = "/path_to/ca.crt"
CLIENT_CERT = "/path_to/client.crt"
CLIENT_KEY = "/path_to/client.key"

# Home Assistant MQTT sensor
MQTT_TOPIC = "gate/gate_is_open"
MQTT_ON = "ON"
MQTT_OFF = "OFF"

# Three alerts: immediately, 15 sec, 30 sec
ALERT_TIMES = (0, 15, 30)

# No new alarm until radio has been quiet
# for this many seconds and all alerts finish
REARM_SILENCE = 10

# False = leave HA sensor ON after alerts
# True = send OFF after all three alerts
SEND_OFF_AFTER_ALERTS = False

# ==========================================
# VERIFIED GATE PACKET - DO NOT CHANGE
# ==========================================

EXPECTED_PACKET = (
    b"GATE|1011011101101|111011010110111\n"
)

# ==========================================
# MQTT CONNECTION
# ==========================================

def connect_mqtt():
    client = mqtt.Client(
        client_id="gate_receiver_pi5",
        protocol=mqtt.MQTTv311
    )

    client.username_pw_set(
        MQTT_USERNAME,
        MQTT_PASSWORD
    )

    client.tls_set(
        ca_certs=CA_CERTS,
        certfile=CLIENT_CERT,
        keyfile=CLIENT_KEY
    )

    client.reconnect_delay_set(
        min_delay=2,
        max_delay=30
    )

    client.connect(
        MQTT_BROKER,
        MQTT_PORT,
        keepalive=60
    )

    client.loop_start()
    return client


def publish(client, message):
    if not client.is_connected():
        return False

    try:
        result = client.publish(
            MQTT_TOPIC,
            message,
            qos=1,
            retain=False
        )

        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            return False

        result.wait_for_publish(timeout=5)
        return result.is_published()

    except Exception as error:
        print("MQTT publish error:", error, flush=True)
        return False


# ==========================================
# CONTINUOUS GATE RECEIVER
# ==========================================

def main():
    print("Starting gate receiver", flush=True)

    client = connect_mqtt()

    alarm_active = False
    alarm_started = 0
    last_packet_time = 0
    alert_index = 0
    off_sent = False
    mqtt_warning = False

    try:
        with serial.Serial(
            SERIAL_PORT,
            BAUD_RATE,
            timeout=0.25
        ) as uart:

            uart.reset_input_buffer()

            print(
                "Listening for HC-12 gate packets",
                flush=True
            )

            while True:
                packet = uart.readline()
                now = time.monotonic()

                if packet == EXPECTED_PACKET:
                    last_packet_time = now

                    if not alarm_active:
                        alarm_active = True
                        alarm_started = now
                        alert_index = 0
                        off_sent = False

                        print(
                            "VALID GATE PACKET!",
                            flush=True
                        )

                elif packet:
                    print(
                        "Ignored invalid packet:",
                        repr(packet),
                        flush=True
                    )

                # Send three scheduled alerts
                if alarm_active:
                    if alert_index < len(ALERT_TIMES):
                        due = (
                            alarm_started
                            + ALERT_TIMES[alert_index]
                        )

                        if now >= due:
                            if publish(client, MQTT_ON):
                    # Optional HA sensor reset
                    if alert_index == len(ALERT_TIMES):
                        if SEND_OFF_AFTER_ALERTS and not off_sent:
                            if publish(client, MQTT_OFF):
                                off_sent = True
                                print(
                                    "MQTT OFF confirmed",
                                    flush=True
                                )

                        finished = (
                            not SEND_OFF_AFTER_ALERTS
                            or off_sent
                        )

                        quiet = (
                            now - last_packet_time
                            >= REARM_SILENCE
                        )

                        if finished and quiet:
                            alarm_active = False

                            print(
                                "Gate receiver rearmed",
                                flush=True
                            )

    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()



                                alert_index += 1
                                mqtt_warning = False

                                print(
                                    "MQTT ALERT",
                                    alert_index,
                                    "CONFIRMED",
                                    flush=True
                                )
                            elif not mqtt_warning:
                                print(
                                    "MQTT unavailable; "
                                    "retrying pending alert",
                                    flush=True
                                )
                                mqtt_warning = True
