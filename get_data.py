#!/usr/bin/python3
import hashlib
import sys
import time as time_  # make sure we don't override time
from datetime import datetime, timedelta
import urllib

import requests

import config
from utils import log

# API Reference: http://api.shinemonitor.com/


def get_salt():
    return int(round(time_.time() * 1000))


def get_token():
    try:
        with open('token', 'r') as file:
            log("Using tokenfile credentials")

            token = file.readline().strip()
            secret = file.readline().strip()
            expiry = file.readline().strip()

            # Check if token expired
            d = datetime.now().today()
            e = datetime.strptime(expiry, '%Y-%m-%d %H:%M:%S.%f')

            log("Datetime now:  " + str(d))
            log("Expires:       " + str(e))

            if d > e:
                log("Expired")
                raise FileNotFoundError
            else:
                log("Not expired")

    except FileNotFoundError:
        log("Logging in using credentials")

        token, secret, expiry = generate_token(get_salt())

        with open('token', 'w') as file:
            file.write(token + '\n')
            file.write(secret + '\n')
            file.write(str(expiry))

    return token, secret

def sha1_to_lower(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest().lower()

def generate_token(salt):
    # SHA-1(pwd)
    sha1_pwd = sha1_to_lower(config.pwd.encode())

    # action string
    action = (
        "&action=auth"
        + "&usr=" + urllib.parse.quote(config.usr)
        + "&company-key=" + config.company_key
    )

    # SHA-1(salt + SHA-1(pwd) + action)
    sign_input = (str(salt) + sha1_pwd + action).encode()
    sign = sha1_to_lower(sign_input)

    # Full request URL
    request = f"{config.base_url}?sign={sign}&salt={salt}{action}"
    r = requests.get(request)
    log(request)
    token = r.json()['dat']['token']
    secret = r.json()['dat']['secret']
    expiry = r.json()['dat']['expire']

    # Convert expiry to datetime when expiring
    today = datetime.now().today()
    expiry = today + timedelta(seconds=expiry)

    return token, secret, expiry


def build_request_url(action, salt, secret, token, devcode, pn, sn, plant_id=None, date=None):
    action = '&action=' + action
    if plant_id:
        action += '&plantid=' + plant_id
    else:
        action += '&pn=' + pn + '&devcode=' + devcode + '&sn=' + sn + '&devaddr=1'
    if date:
        action += '&date=' + date

    # need to sign entire request url with params
    secret_action = str(salt) + secret + token + action
    sign_sha1 = hashlib.sha1()
    sign_sha1.update(secret_action.encode('utf-8'))
    sign = str(sign_sha1.hexdigest())

    request_url = config.base_url + '?sign=' + sign + '&salt=' + str(salt) + '&token=' + token + action
    return request_url


def get_device_info(token, secret):
    action = '&action=webQueryCollectorInfo'
    action += f'&pn={config.pn}'

    salt = get_salt()

    # Build sign string and hash it
    sign_source = f"{salt}{secret}{token}{action}"
    sign = hashlib.sha1(sign_source.encode('utf-8')).hexdigest()

    # Final URL
    request_url = f"{config.base_url}?sign={sign}&salt={salt}&token={token}{action}"

    log(request_url)
    response = requests.get(request_url)
    data = response.json()

    if data.get('err') == 0:
        return data.get('dat')
    else:
        return None  # or raise an exception if preferred


def get_device_status(token, secret):
    action = 'queryDeviceStatus'
    action = '&action=' + action
    action += '&device=' + ','.join([config.pn, config.devcode, '1', config.sn])

    salt = get_salt()
    # need to sign entire request url with params
    secret_action = str(salt) + secret + token + action
    sign_sha1 = hashlib.sha1()
    sign_sha1.update(secret_action.encode('utf-8'))
    sign = str(sign_sha1.hexdigest())

    request_url = config.base_url + '?sign=' + sign + '&salt=' + str(salt) + '&token=' + token + action

    log(request_url)
    response = requests.get(request_url)
    errcode = response.json()['err']

    if errcode == 0:
        data = response.json()['dat']
        return data
    else:
        return '{ErrorCode: ' + str(errcode) + '}'


def update_plant_info(token, secret, parameter, value):
    action = 'editPlant'
    action = '&action=' + action
    action += '&plantid=' + config.plant_id
    action += '&' + parameter + '=' + value
    action += default_params

    salt = get_salt()
    # need to sign entire request url with params
    secret_action = str(salt) + secret + token + action
    sign_sha1 = hashlib.sha1()
    sign_sha1.update(secret_action.encode('utf-8'))
    sign = str(sign_sha1.hexdigest())

    request_url = config.base_url + '?sign=' + sign + '&salt=' + str(salt) + '&token=' + token + action

    log(request_url)
    response = requests.post(request_url)
    errcode = response.json()['err']

    if errcode == 0:
        return response
    else:
        return '{ErrorCode: ' + str(errcode) + '}'


def get_plant_info(token, secret):
    request_url = build_request_url('queryPlantInfo',
                                    str(get_salt()), secret, token,
                                    config.devcode, config.pn, config.sn,
                                    plant_id=config.plant_id,
                                    date=datetime.today().strftime('%Y-%m-%d'))

    log(request_url)
    response = requests.get(request_url)
    errcode = response.json()['err']

    if errcode == 0:
        data = response.json()['dat']
        return data
    else:
        return '{ErrorCode: ' + str(errcode) + '}'


def get_generation_latest(token, secret):
    request_url = build_request_url('queryDeviceLastData',
                                    (get_salt()), secret, token,
                                    config.devcode, config.pn, config.sn,
                                    date=datetime.today().strftime('%Y-%m-%d'))

    log(request_url)
    response = requests.get(request_url)
    errcode = response.json()['err']

    if errcode == 0:
        data = response.json()['dat']
        return data
    else:
        return '{ErrorCode: ' + str(errcode) + '}'


if __name__ == '__main__':
    token, secret = get_token()

    if len(sys.argv) > 1:
        endpoint = str(sys.argv[1])
        if endpoint == '--latest':
            print(get_generation_latest(token, secret))
        if endpoint == '--plantInfo':
            print(get_plant_info(token, secret))
        if endpoint == '--updatePlantInfo':
            print(update_plant_info(token, secret, str(sys.argv[2]), str(sys.argv[3])))
        if endpoint == '--deviceInfo':
            print(get_device_info(token, secret))
        if endpoint == '--deviceStatus':
            print(get_device_status(token, secret))
