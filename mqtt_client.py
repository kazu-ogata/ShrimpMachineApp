import paho.mqtt.client as mqtt

# We use "localhost" because the broker (mosquitto) is
# running on the *same machine* as this Python app.
BROKER_ADDRESS = "localhost"

class MqttClient:
    def __init__(self, client_id="ShrimpAppPython"):
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        self.client.on_connect = self.on_connect
        self.connected = False

    def on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            print("MQTT: Python client connected successfully.")
            self.connected = True
        else:
            print(f"MQTT: Python client failed to connect, code {rc}")

    def connect(self):
        try:
            self.client.connect(BROKER_ADDRESS)
            self.client.loop_start()  # Starts a background thread
        except Exception as e:
            print(f"MQTT: Could not connect to broker. Is mosquitto running? Error: {e}")

    def disconnect(self):
        self.client.loop_stop()
        self.client.disconnect()
        print("MQTT: Python client disconnected.")

    def publish(self, topic, payload):
        if self.connected:
            self.client.publish(topic, payload)
        else:
            print(f"MQTT: Not connected. Cannot publish to {topic}")
