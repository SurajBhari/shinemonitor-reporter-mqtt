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

            # Topic format: homeassistant/sensor/shinemonitor/<key>
            discovery_topic = f"{discovery_prefix}/sensor/shinemonitor{suffix}/{key}/config"
            state_topic = f"{base_topic}/shinemonitor{suffix}/{key}"

            if key not in discovery_sent:
                # Determine state_class based on key and unit
                if "today" in key and unit:
                    state_class = "total_increasing"
                else:
                    state_class = "measurement" if unit else "total"

                # After determining device_class, override state_class if needed
                if unit:
                    unit = unit.strip()
                    payload["unit_of_measurement"] = unit
                    device_class = unit_to_device_class.get(unit)
                    if device_class:
                        payload["device_class"] = device_class
                        # Override state_class if device_class is "energy"
                        if device_class == "energy":
                            if "today" in key:
                                state_class = "total_increasing"
                            else:
                                state_class = "total"

                
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

                # Map units to device classes
                unit_to_device_class = {
                    # Voltage
                    "V": "voltage", "mV": "voltage", "µV": "voltage", "kV": "voltage", "MV": "voltage",
                    # Current
                    "A": "current", "mA": "current", "µA": "current", "kA": "current",
                    # Power
                    "W": "power", "mW": "power", "kW": "power", "MW": "power",
                    # Energy
                    "Wh": "energy", "mWh": "energy", "kWh": "energy", "MWh": "energy",
                    # Temperature
                    "°C": "temperature", "°F": "temperature",
                    # Illuminance
                    "lux": "illuminance", "lm": "illuminance", "cd": "illuminance",
                    # Humidity-like (careful here)
                    "%": "humidity",  # You may want to override based on sensor name
                    # Gas sensors (optional, if used)
                    "ppm": "carbon_dioxide",  # adjust based on context
                    "ppb": "carbon_monoxide",  # example
                }

                # Apply to payload
                if unit:
                    unit = unit.strip()
                    payload["unit_of_measurement"] = unit
                    device_class = unit_to_device_class.get(unit)
                    if device_class:
                        payload["device_class"] = device_class

                payload["json_attributes_topic"] = state_topic
                payload["value_template"] = "{{ value_json.val }}"
                payload["json_attributes_template"] = "{{ value_json | tojson }}"
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
                    "ac": "mdi:air-conditioner"
                }

                # Default icon
                payload["icon"] = "mdi:flash"

                # Match the first key in icon_map found in `key`
                for k, v in icon_map.items():
                    if k in key:
                        payload["icon"] = v
                        break
                

                client.publish(discovery_topic, json.dumps(payload), retain=True)
                #print(f"Published discovery for {key} to {discovery_topic}")
                discovery_sent.add(key)

            print(state_topic, unit, value)
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