import _thread
import json
import threading
import time
import traceback
from requests.exceptions import ConnectionError
from collections import OrderedDict
from datetime import datetime
from time import sleep

from paho.mqtt import client as mqtt
from tzlocal import get_localzone

import config
from get_data import get_token, get_generation_latest
from utils import log
from collections import OrderedDict
from datetime import datetime
# -----------------------------------------------------------------------------
#  Sensor Definitions
# -----------------------------------------------------------------------------

PAYLOAD_NAME = 'info'
SHINE_MONITOR = 'shine_monitor'
GRID_VOLTAGE = 'grid_voltage'
PV_INPUT_VOLTAGE = 'pv1_input_voltage'
PV_INPUT_POWER = 'pv_input_power'
BATTERY_VOLTAGE = 'battery_voltage'
BATTERY_CAPACITY = 'battery_capacity_percent'
BATTERY_DISCHARGE_CURRENT = 'battery_discharge_current'
BATTERY_CHARGE_CURRENT = 'battery_charge_current'
AC_OUTPUT_VOLTAGE = 'ac_output_voltage'
OUTPUT_LOAD = 'output_load_percent'
AC_OUTPUT_ACTIVE_POWER = 'ac_output_active_power'
TODAY_GENERATION = 'today_generation'
MONTH_GENERATION = 'month_generation'
YEAR_GENERATION = 'year_generation'
TOTAL_GENERATION = 'total_generation'

detectors = OrderedDict([
    (SHINE_MONITOR, dict(
        title='Shine Monitor',
        topic_category='sensor',
        device_class='timestamp',
        device_ident="ShineMonitor-{}".format(config.sensor_name),
        icon='mdi:meter-electric-outline',
        json_attr='yes',
        json_value='timestamp',
    )),
    (GRID_VOLTAGE, dict(
        title='Grid Voltage',
        topic_category='sensor',
        device_class='voltage',
        state_class='measurement',
        unit='V',
        icon='mdi:gauge',
        json_value=GRID_VOLTAGE,
    )),
    (PV_INPUT_VOLTAGE, dict(
        title='PV1 Input Voltage',
        topic_category='sensor',
        device_class='voltage',
        state_class='measurement',
        unit='V',
        icon='mdi:gauge',
        json_value=PV_INPUT_VOLTAGE,
    )),
    (PV_INPUT_POWER, dict(
        title='PV1 Input Power',
        topic_category='sensor',
        device_class='power',
        state_class='measurement',
        unit='W',
        icon='mdi:solar-power',
        json_value=PV_INPUT_POWER,
    )),
    (AC_OUTPUT_ACTIVE_POWER, dict(
        title='AC output active power',
        topic_category='sensor',
        device_class='power',
        state_class='measurement',
        unit='W',
        icon='mdi:home-lightning-bolt',
        json_value=AC_OUTPUT_ACTIVE_POWER,
    )),
    (TODAY_GENERATION, dict(
        title='Today generation',
        topic_category='sensor',
        device_class='energy',
        state_class='total_increasing',
        unit='Wh',
        icon='mdi:solar-power-variant',
        json_value=TODAY_GENERATION,
    )),
    (MONTH_GENERATION, dict(
        title='Month generation',
        topic_category='sensor',
        device_class='energy',
        state_class='total_increasing',
        unit='Wh',
        icon='mdi:solar-power-variant',
        json_value=MONTH_GENERATION,
    )),
    (YEAR_GENERATION, dict(
        title='Year generation',
        topic_category='sensor',
        device_class='energy',
        state_class='total_increasing',
        unit='Wh',
        icon='mdi:solar-power-variant',
        json_value=YEAR_GENERATION,
    )),
    (TOTAL_GENERATION, dict(
        title='Total generation',
        topic_category='sensor',
        device_class='energy',
        state_class='total_increasing',
        unit='kWh',
        icon='mdi:solar-power-variant',
        json_value=TOTAL_GENERATION,
    )),

])

# -----------------------------------------------------------------------------
#  Timer for MQTT Alive Status Functions
# -----------------------------------------------------------------------------

ALIVE_TIMEOUT_IN_SECONDS = 60


def publish_alive_status():
    log('Sending alive status')
    mqtt_client.publish(lwt_sensor_topic, payload=lwt_online_val, retain=False)


def publish_shutdown_status():
    log("Publishing shutdown status to MQTT broker...")
    mqtt_client.publish(lwt_sensor_topic, payload=lwt_offline_val, retain=False)


def alive_timeout_handler():
    log('-- MQTT KeepAlive Timeout --')
    _thread.start_new_thread(publish_alive_status, ())
    start_alive_timer()


def start_alive_timer():
    global alive_timer
    global alive_timer_running_status
    stop_alive_timer()
    alive_timer = threading.Timer(ALIVE_TIMEOUT_IN_SECONDS, alive_timeout_handler)
    alive_timer.start()
    alive_timer_running_status = True
    log('Started MQTT timer - every {} seconds'.format(ALIVE_TIMEOUT_IN_SECONDS))


def stop_alive_timer():
    global alive_timer
    global alive_timer_running_status
    alive_timer.cancel()
    alive_timer_running_status = False
    log('Stopped MQTT timer')


def is_alive_timer_running():
    global alive_timer_running_status
    return alive_timer_running_status


alive_timer = threading.Timer(ALIVE_TIMEOUT_IN_SECONDS, alive_timeout_handler)
alive_timer_running_status = False


# -----------------------------------------------------------------------------
#  MQTT Client Functions
# -----------------------------------------------------------------------------


def on_connect(client, userdata, flags, rc):
    global mqtt_client_connected
    if rc == 0:
        print("Connected to MQTT Broker!")
        mqtt_client_connected = True
    else:
        print("Failed to connect, return code %d\n", rc)
        exit(1)


def on_disconnect(client, userdata, mid):
    global mqtt_client_connected
    mqtt_client_connected = False
    log("MQTT connection lost - disconnected.")
    pass


def connect_mqtt():
    print("Connecting to MQTT broker ...")

    client = mqtt.Client()
    # hook up MQTT callbacks
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

    client.will_set(lwt_sensor_topic, payload=lwt_offline_val, retain=True)

    try:
        client.connect(config.hostname, port=config.port, keepalive=60)
    except:
        print('MQTT connection error. Please check your settings in the configuration file "config.py"')
        exit(1)
    else:
        client.publish(lwt_sensor_topic, payload=lwt_online_val, retain=False)
        client.loop_start()

        while not mqtt_client_connected:  # wait in loop
            sleep(1.0)  # some slack to establish the connection

        # Publish alive status again (in case above one published before connect)
        client.publish(lwt_sensor_topic, payload=lwt_online_val, retain=False)
        start_alive_timer()

    return client


def publish(topic, message, retain=False):
    log('Publishing to MQTT topic "{}, Data:{}"'.format(topic, message))
    result = mqtt_client.publish(topic, message, 1, retain=retain)
    # result: [0, 1]
    status = result[0]
    if status == 0:
        log(f"Sent `{message}` to topic `{topic}`")
    else:
        log(f"Failed to send message to topic {topic}")
    sleep(0.5)


mqtt_client_connected = False


def prepare_payload(raw_data):
    """
    Accepts either:
      • dict-of-dicts style: {"Grid voltage": {"val": "230"} …}
      • list-of-dicts style: [{"title": "Grid voltage", "val": "230"} …]
    and returns {PAYLOAD_NAME: OrderedDict(…)}
    """
    global prev_total_generation

    # --- Normalise raw_data into dict-of-dicts --------------------------------
    if isinstance(raw_data, list):
        data = {}
        for item in raw_data:
            title = item.get("title", "")
            if title:                         # ignore items missing a title
                # Keep the last duplicate we see; feel free to reverse() if you
                # prefer the first.
                data[title] = {"val": item.get("val", "")}
    elif isinstance(raw_data, dict):
        data = raw_data
    else:
        raise TypeError("raw_data must be a dict or a list of dicts")

    # --- Helpers --------------------------------------------------------------
    def safe_get(*keys):
        """Return the first non-empty .val for keys, else ''."""
        for k in keys:
            v = data.get(k, {}).get("val", "")
            if v not in ("", None):
                return v
        return ""

    def safe_float(*keys):
        try:
            return float(safe_get(*keys))
        except (ValueError, TypeError):
            return ""

    def safe_int(*keys):
        try:
            return int(float(safe_get(*keys)))   # handles '28.0' as well
        except (ValueError, TypeError):
            return ""

    # --- Build payload --------------------------------------------------------
    p = OrderedDict()

    # plain strings
    p["id"]                 = safe_get("id")
    p["sn"]                 = safe_get("SN")
    p["machine_type"]       = safe_get("Machine type", "Equipment type")

    # timestamp
    ts_raw = safe_get("Timestamp")
    try:
        p["timestamp"] = (
            datetime.strptime(ts_raw, "%Y-%m-%d %H:%M:%S")
            .astimezone()     # converts from naïve-local to aware-local
            .replace(microsecond=0)
            .isoformat()
        )
    except Exception:
        p["timestamp"] = ""

    # numeric fields ─ use first matching key in each alias list
    p[GRID_VOLTAGE]             = safe_float("Grid voltage",
                                             "Grid R voltage")
    p["grid_frequency"]         = safe_float("Grid frequency")
    p[PV_INPUT_VOLTAGE]         = safe_float("PV1 Input voltage",
                                             "PV1 voltage")
    p[PV_INPUT_POWER]           = safe_int  ("PV1 Input Power",
                                             "Output Power")
    p[AC_OUTPUT_ACTIVE_POWER]   = safe_int  ("AC output active power",
                                             "Output Power")
    p["ac_output_apparent_power"]= safe_int ("AC output apparent power",
                                             "Output S")

    # generation / energy counters
    p[TODAY_GENERATION] = safe_int("Today generation", "Energy today")
    p[MONTH_GENERATION] = safe_int("Month generation")  # may be absent
    p[YEAR_GENERATION]  = safe_int("Year generation")   # may be absent

    # total generation with the “weird ‘-’” safeguard
    try:
        p[TOTAL_GENERATION] = float(
            safe_get("Total generation", "energy_total")
        )
        prev_total_generation = p[TOTAL_GENERATION]
    except (ValueError, TypeError):
        p[TOTAL_GENERATION] = prev_total_generation

    # last-updated stamp
    p["last_updated"] = (
        datetime.now(local_tz).replace(microsecond=0).isoformat()
    )

    # wrap and return
    payload_info            = OrderedDict()
    payload_info[PAYLOAD_NAME] = p
    return payload_info


def prepare_discovery_payload(sensor, params):
    payload = OrderedDict()
    payload['name'] = '{}'.format(params['title'].title())
    payload['uniq_id'] = '{}_{}'.format(unique_id, sensor.lower())
    if 'device_class' in params:
        payload['dev_cla'] = params['device_class']
    if 'state_class' in params:
        payload['stat_cla'] = params['state_class']
    if 'unit' in params:
        payload['unit_of_measurement'] = params['unit']
    if 'json_value' in params:
        payload['stat_t'] = values_topic_rel
        payload['val_tpl'] = '{{{{ value_json.{}.{} }}}}'.format(PAYLOAD_NAME, params['json_value'])
    payload['~'] = sensor_base_topic
    payload['avty_t'] = activity_topic_rel
    payload['pl_avail'] = lwt_online_val
    payload['pl_not_avail'] = lwt_offline_val
    if 'icon' in params:
        payload['ic'] = params['icon']
    if 'json_attr' in params:
        payload['json_attr_t'] = values_topic_rel
        payload['json_attr_tpl'] = '{{{{ value_json.{} | tojson }}}}'.format(PAYLOAD_NAME)
    if 'device_ident' in params:
        payload['dev'] = {
            'identifiers': ["{}".format(unique_id)],
            'manufacturer': 'ShineMonitor PV monitoring Open platform API',
            'name': params['device_ident'],
            'model': 'wifiapp.volfw.solarpower',
            'sw_version': "1.1.0.1"
        }
    else:
        payload['dev'] = {
            'identifiers': ["{}".format(unique_id)],
        }
    return payload


def publish_solar_data():
    log("Obtaining token and secret...")
    token, secret = get_token()
    log("Fetching data...")
    response = get_generation_latest(token, secret)
    log(f"Received response: {response}")

    if not is_alive_timer_running():
        publish_alive_status()
        start_alive_timer()

    # Convert array of dict to key: value pair for easy parsing
    response_dict = dict()
    for value in response:
        response_dict[value['title']] = value

    # To avoid logging duplicate data
    try:
        with open('last_timestamp', 'r') as file:
            last_timestamp = file.readline().strip()
            if response_dict['Timestamp']['val'] == last_timestamp:
                log("Data has not been updated, skipping this data.")
                return last_timestamp
    except FileNotFoundError:
        log("logging Timestamp in file...")
    finally:
        with open('last_timestamp', 'w') as file:
            file.write(response_dict['Timestamp']['val'])

    _thread.start_new_thread(publish, (values_topic, json.dumps(prepare_payload(response_dict))))

    return response_dict['Timestamp']['val']


def publish_discovery_topic():
    for (sensor, params) in detectors.items():
        discovery_topic = '{}/{}/{}/{}/config'.format(config.discovery_prefix, params['topic_category'],
                                                      config.sensor_name.lower(), sensor)
        publish(discovery_topic, json.dumps(prepare_discovery_payload(sensor, params)), retain=True)


local_tz = get_localzone()
prev_total_generation = 0.0

# -----------------------------------------------------------------------------
#  Main Function
# -----------------------------------------------------------------------------


if __name__ == '__main__':
    print("Starting ShineMonitor Reporter MQTT...")
    last_time = 0
    interval_in_seconds = (config.interval_in_minutes * 60)
    unique_id = f'ShineMonitor-{config.plant_id}-{config.pn}-{config.sn}'

    lwt_sensor_topic = '{}/sensor/{}/status'.format(config.base_topic, config.sensor_name.lower())
    lwt_online_val = 'online'
    lwt_offline_val = 'offline'

    sensor_base_topic = '{}/sensor/{}'.format(config.base_topic, config.sensor_name.lower())
    values_topic_rel = '{}/{}'.format('~', "shinemonitor")
    values_topic = '{}/{}'.format(sensor_base_topic, "shinemonitor")
    activity_topic_rel = '{}/status'.format('~')  # vs. LWT
    activity_topic = '{}/status'.format(sensor_base_topic)  # vs. LWT

    # Connect to the MQTT broker
    mqtt_client = connect_mqtt()

    # Publish discovery topic for HA
    publish_discovery_topic()

    # Set a counter for exceptions.
    exception_count = 0
    # Loop until explicitly stopped
    try:
        while True:
            try:
                current_time = time.time()
                # print(f"Current Time: {current_time}, Last Updated: {last_time}")
                if current_time > last_time + interval_in_seconds:
                    print("Updating status...")
                    last_time = datetime.strptime(publish_solar_data(), '%Y-%m-%d %H:%M:%S').timestamp()
                    exception_count = 0  # reset exception counter if successfully executed
                    # print(f"Last Updated set to {last_time}")

                # Sleep the program so we don't query everytime
                sleep(30)
            # For cases where internet is down, log the error once and shut down the sensors until online.
            except ConnectionError:
                # TODO issue with not reconnecting on restart
                log("Exception Found: " + traceback.format_exc())
                if is_alive_timer_running():
                    with open('error_log.txt', 'a') as file:
                        formatted_time = datetime.fromtimestamp(time.time())
                        file.write(f'{formatted_time}\t{traceback.format_exc()}\n')
                    mqtt_client.publish(lwt_sensor_topic, payload=lwt_offline_val, retain=False)
                    stop_alive_timer()
            # Any exceptions log and keep and retry at least 3 times before shutting down
            except Exception:
                exception_count += 1
                log("Exception Found: " + traceback.format_exc())
                with open('error_log.txt', 'a') as file:
                    formatted_time = datetime.fromtimestamp(time.time())
                    file.write(f'{formatted_time}\t{traceback.format_exc()}\n')
                if exception_count >= 3:
                    raise
    finally:
        publish_shutdown_status()
        mqtt_client.disconnect()
        print("MQTT disconnected")
        stop_alive_timer()
        print("ShineMonitor Reporter MQTT has terminated.")
        exit(0)
