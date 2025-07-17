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
            value = item.get("val")
            unit = item.get("unit")

            if value is None:
                continue

            is_number = False
            try:
                float(value)
                is_number = True
            except (ValueError, TypeError):
                pass

            discovery_topic = f"{discovery_prefix}/sensor/shinemonitor{suffix}/{key}/config"
            state_topic = f"{base_topic}/shinemonitor{suffix}/{key}"

            if key not in discovery_sent:
                if not is_number:
                    state_class = "measurement"
                elif "today" in key and unit:
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
                    "value_template": "{{ value_json.val }}",
                    "json_attributes_topic": state_topic,
                    "json_attributes_template": "{{ value_json | tojson }}"
                }

                if state_class == "total_increasing":
                    payload["last_reset"] = time.strftime("%Y-%m-%dT00:00:00Z", time.gmtime())

                unit_to_device_class = {
                    "V": "voltage", "mV": "voltage", "µV": "voltage", "kV": "voltage", "MV": "voltage",
                    "A": "current", "mA": "current", "µA": "current", "kA": "current",
                    "W": "power", "mW": "power", "kW": "power", "MW": "power",
                    "Wh": "energy", "mWh": "energy", "kWh": "energy", "MWh": "energy",
                    "°C": "temperature", "°F": "temperature",
                    "lux": "illuminance", "lm": "illuminance", "cd": "illuminance",
                    "%": "humidity",
                    "ppm": "carbon_dioxide", "ppb": "carbon_monoxide",
                    "HZ": "frequency", "h": "duration", "S": "duration", "VA": "apparent_power"
                }

                if is_number and unit:
                    unit = unit.strip()
                    payload["unit_of_measurement"] = unit
                    device_class = unit_to_device_class.get(unit)
                    if device_class:
                        payload["device_class"] = device_class

                if not is_number:
                    payload["device_class"] = None

                icon_map = {
                    "today": "mdi:calendar-today",
                    "yesterday": "mdi:calendar",
                    "last_week": "mdi:calendar-week",
                    "last_month": "mdi:calendar-month",
                    "last_year": "mdi:calendar-year",
                    "last_reset": "mdi:history",
                    "voltage": "mdi:flash",
                    "power": "mdi:flash",
                    "energy": "mdi:flash",
                    "current": "mdi:current-ac",
                    "temperature": "mdi:thermometer",
                    "humidity": "mdi:water-percent",
                    "illuminance": "mdi:weather-sunny",
                    "lux": "mdi:weather-sunny",
                    "gas": "mdi:gas-cylinder",
                    "pressure": "mdi:gauge",
                    "co2": "mdi:molecule-co2",
                    "pm": "mdi:air-filter",
                    "dust": "mdi:air-filter",
                    "noise": "mdi:volume-high",
                    "sound": "mdi:volume-high",
                    "battery": "mdi:battery",
                    "signal": "mdi:signal",
                    "status": "mdi:check-circle",
                    "error": "mdi:alert-circle",
                    "warning": "mdi:alert",
                    "uptime": "mdi:clock-outline",
                    "location": "mdi:map-marker",
                    "gps": "mdi:map-marker",
                    "motion": "mdi:run",
                    "door": "mdi:door",
                    "window": "mdi:door",
                    "light": "mdi:lightbulb",
                    "leak": "mdi:water-off",
                    "water": "mdi:water",
                    "switch": "mdi:toggle-switch",
                    "fan": "mdi:fan",
                    "heat": "mdi:radiator",
                    "heater": "mdi:radiator",
                    "cool": "mdi:air-conditioner",
                    "ac": "mdi:air-conditioner",
                    "manufacturer": "mdi:factory",
                    "id": "mdi:identifier",
                    "sn": "mdi:barcode",
                    "security_type": "mdi:shield",
                    "timestamp": "mdi:clock"
                }

                payload["icon"] = "mdi:flash"
                for k, v in icon_map.items():
                    if k in key:
                        payload["icon"] = v
                        break

                client.publish(discovery_topic, json.dumps(payload), retain=True)
                discovery_sent.add(key)

            print(state_topic, unit, value)
            client.publish(state_topic, json.dumps(item))

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
