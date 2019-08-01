#!/bin/env python

import Pyro4
import os
import imp
import sys
import yaml
import json


config = { 'WINRPC': { 'devdomain': { 'host': 'srv02391.devdomain.soton.ac.uk', 'port': 1888, 'key': 'chang3me' } } }
env = 'devdomain'


#######################################################

def dsc_connect():
	proxy = Pyro4.Proxy('PYRO:CortexWindowsRPC@' + str(config['WINRPC'][env]['host']) + ':' + str(config['WINRPC'][env]['port']))
	proxy._pyroHmacKey = str(config['WINRPC'][env]['key'])
	try:
		proxy.ping()
	except Pyro4.errors.PyroError as e:
		raise e

	return proxy

######################################################

def dsc_generate_files(proxy, name, details):
	proxy.generate_json_file(name, details)
	proxy.generate_yaml_file(name, yaml.dump(json.loads(details)))

######################################################

def get_roles(proxy):
	return proxy.get_roles()

