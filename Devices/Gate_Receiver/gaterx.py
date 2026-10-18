
import time
import serial
import paho.mqtt.client as mqtt

# ==========================================
# CONFIGURATION
# ==========================================

SERIAL_PORT = "/dev/ttyAMA4"
BAUD_RATE = 9600

MQTT_BROKER = "YOURLOCALIP"
MQTT_PORT = 8883
MQTT_USERNAME = "Gate"
MQTT_PASSWORD = "PUT_YOUR_PASSWORD_HERE"

CA_CERTS = "/path_to/ca.crt"
CLIENT_CERT = "/path_toe/client.crt"
CLIENT_KEY = "/path_to/client.key"

STATE_TOPIC = "gate/gate_is_open"
ALERT_TOPIC = "gate/gate_alert"

ALERT_TIMES = (0, 15, 30)

# ==========================================
# VERIFIED RADIO PACKETS
# ==========================================

OPEN_PACKET = b"GATE|1011011101101|111011010110111\n"
CLOSED_PACKET = b"GATE_CLOSED|1011011101101|111011010110111\n"

# ==========================================
# MQTT
# ==========================================

def setup_mqtt():
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

    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()
    return client


def publish(client, topic, payload, retain=False):
    if not client.is_connected():
        return False

    try:
        result = client.publish(
            topic,
            payload,
            qos=1,
            retain=retain
        )

        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            return False

        result.wait_for_publish(timeout=5)
        return result.is_published()

    except Exception as error:
        print("MQTT ERROR:", error, flush=True)
        return False


# ==========================================
# MAIN RECEIVER
# ==========================================

def main():
    print("Starting gate receiver", flush=True)

    client = setup_mqtt()

    gate_state = None
    published_state = None

    # Current reminder sequence
    alert_started = None
    alert_index = 0

    try:
        with serial.Serial(
            SERIAL_PORT,
            BAUD_RATE,
            timeout=0.2
        ) as uart:

            uart.reset_input_buffer()
            print("Listening for gate packets", flush=True)

            while True:
                packet = uart.readline()
                now = time.monotonic()

                if packet == OPEN_PACKET:
                    if gate_state != "ON":
                        print("GATE OPEN", flush=True)

                        # A new opening starts 3 reminders
                        alert_started = now
                        alert_index = 0

                    gate_state = "ON"

                elif packet == CLOSED_PACKET:
                    if gate_state != "OFF":
                        print("GATE CLOSED", flush=True)

                    gate_state = "OFF"

                    # Do NOT cancel existing reminders

                elif packet:
                    print(
                        "INVALID PACKET:",
                        repr(packet),
                        flush=True
                    )

                # Publish physical gate state
                # Resend after an MQTT reconnect
                if not client.is_connected():
                    published_state = None

                if (
                    gate_state is not None
                    and gate_state != published_state
                ):
                    if publish(
                        client,
                        STATE_TOPIC,
                        gate_state,
                        retain=True
                    ):
                        published_state = gate_state
                        print(
                            "STATE PUBLISHED:",
                            gate_state,
                            flush=True
                        )

                # Three reminders independent
                # of whether gate has closed
                if (
                    alert_started is not None
                    and alert_index < len(ALERT_TIMES)
                ):
                    due = (
                        alert_started
                        + ALERT_TIMES[alert_index]
                    )

                    if time.monotonic() >= due:
                        number = alert_index + 1

                        if publish(
                            client,
                            ALERT_TOPIC,
                            str(number)
                        ):
                            print(
                                "ALERT",
                                number,
                                "CONFIRMED",
                                flush=True
                            )
                            alert_index += 1

                if (
                    alert_started is not None
                    and alert_index == len(ALERT_TIMES)
                ):
                    print(
                        "Three reminders completed",
                        flush=True
                    )
                    alert_started = None

    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
