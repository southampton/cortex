#!/usr/bin/python

from cortex import app
import Pyro4

################################################################################

## Connects to the CortexWindowsRPC daemon for the specified environment
def connect_winrpc(env):
	# Check that we have the environment details
	if env not in app.config['WINRPC']:
		raise ValueError("No Cortex Windows RPC daemon configured for environment '" + env + "'")

	# Generate the host:port connection string
	conn_string = app.config['WINRPC'][env]['host'] + ':' + str(app.config['WINRPC'][env]['port'])

	# Connect to the appropriate Pyro4 daemon
	proxy = Pyro4.Proxy('PYRO:CortexWindowsRPC@' + conn_string)
	proxy._pyroHmacKey = app.config['WINRPC'][env]['key']
	proxy._pyroTimeout = 30	# AD can sometimes take a while to respond to this

	# Attempt to ping the proxy to check that it's up
	try:
		proxy.ping()
	except Exception as e:
		raise Exception('Failed to communicate with Cortex Windows RPC daemon at ' + conn_string + ': ' + str(e))

	return proxy

################################################################################

## Return a boolean indicating whether a computer object exists in AD in the
## specified environment with the given hostname
def is_computer_object(env, hostname):
	return connect_winrpc(env).find_computer_object(hostname)

################################################################################

## Deletes a computer object exists in AD in the specified environment with the 
## given hostname
def delete_computer_object(env, hostname):
	return connect_winrpc(env).delete_computer_object(hostname)

