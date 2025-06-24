import time
import json
import threading
import paho.mqtt.client as mqtt
from config import (
    interval_in_minutes,
    hostname,
    port,
    discovery_prefix,
    base_topic,
    sensor_name,
    suffix
)
from get_data import get_token, get_generation_latest

# Format MQTT-safe keys
def slugify(text):
    return text.lower().replace(" ", "_").replace("'", "").replace("\"", "").replace("/", "_")

# MQTT Client Setup
client = mqtt.Client()
client.connect(hostname, port)
client.loop_start()

discovery_sent = set()

# Publish sensor discovery and data
def publish_sensor_data():
    global discovery_sent

    try:
        token, secret = get_token()
        data = get_generation_latest(token, secret)

        for item in data:
            key = slugify(item.get("title", "unknown"))
            value = item.get("val", None)
            unit = item.get("unit", None)
            
            if value is None:
                continue

            # Topic format: homeassistant/sensor/shinemonitor<suffix>/<key>
            discovery_topic = f"{discovery_prefix}/sensor/shinemonitor{suffix}/{key}/config"
            state_topic = f"{base_topic}/shinemonitor{suffix}/{key}"

            if key not in discovery_sent:
                if "today" in key and unit:  # energy today sensor
                    state_class = "total_increasing"
                else:
                    state_class = "measurement" if unit else "total"

                payload = {
                    "name": f"{sensor_name} {key}",
                    "state_topic": state_topic,
                    "unique_id": f"{sensor_name}_{key}",
                    "device": {
                        "identifiers": [sensor_name],
                        "name": sensor_name,
                        "manufacturer": "ShineMonitor"
                    },
                    "state_class": state_class,
                }

                if state_class == "total_increasing":
                    # Set last reset to today's date at 00:00:00 UTC
                    payload["last_reset"] = time.strftime("%Y-%m-%dT00:00:00Z", time.gmtime())

                if unit:
                    payload["unit_of_measurement"] = unit
                    payload["device_class"] = "energy"

                client.publish(discovery_topic, json.dumps(payload), retain=True)
                discovery_sent.add(key)


            # Publish the sensor value
            client.publish(state_topic, value)

    except Exception as e:
        print(f"Error fetching or publishing data: {e}")

# Background loop
interval_seconds = interval_in_minutes * 60

def run_service():
    while True:
        publish_sensor_data()
        time.sleep(interval_seconds)

if __name__ == "__main__":
    run_service()