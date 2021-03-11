#!/bin/env python
from cortex import app
import Pyro4
import Pyro4.errors
import os
import imp
import sys
import yaml
import json


# config = { 'WINRPC': { 'devdomain': { 'host': 'srv02391.devdomain.soton.ac.uk', 'port': 1888, 'key': 'chang3me' } } }
env = app.config["DSC_ENV"]

def dsc_test_connect():
	with Pyro4.Proxy('PYRO:CortexWindowsRPC@' + str(app.config['DSC'][env]['host']) + ':' + str(app.config['DSC'][env]['port'])) as proxy:
		try:
			proxy._pyroBind()
			print("YES IS ON")
		except Pyro4.errors.CommunicationError as e:
			raise e


#######################################################

def dsc_connect():
	proxy = Pyro4.Proxy('PYRO:CortexWindowsRPC@' + str(app.config['DSC'][env]['host']) + ':' + str(app.config['DSC'][env]['port']))
	proxy._pyroHmacKey = str(app.config['DSC'][env]['key'])
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

######################################################

def send_config(proxy, name,  data):
	proxy.send_json(name, data)
	proxy.send_yaml(name, data)
	

######################################################

# To be implemented on authoring machine
def get_machine_config(proxy, name):
	return proxy.get_machine_config(name)

######################################################

def enroll_new(proxy, name, role):
	return proxy.enroll_new(name, role)
