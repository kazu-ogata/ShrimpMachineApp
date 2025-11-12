import paho.mqtt.client as mqtt

def on_connect(client, userdata, flags, rc, properties=None):
    print("Fake-ESP32: Connected to broker and listening...")
    # Subscribe to all the topics we care about
    client.subscribe("shrimp/pump/command")
    client.subscribe("shrimp/servo1/command")
    client.subscribe("shrimp/servo2/command")
    client.subscribe("shrimp/servo3/command")

def on_message(client, userdata, msg):
    # This function runs every time a message is received
    # Prints one clean line as requested
    print(f"FAKE ESP32 RECEIVED:  {msg.payload.decode()}")

# --- Main script ---
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="FakeESP32")
client.on_connect = on_connect
client.on_message = on_message

try:
    client.connect("localhost")
except Exception as e:
    print("ERROR: Could not connect to broker. Is mosquitto running?")
    print("Try running: sudo systemctl status mosquitto")
    exit()

print("Fake ESP32 is listening... (Press Ctrl+C to stop)")
client.loop_forever() # This blocks and just listens
