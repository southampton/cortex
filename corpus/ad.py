#!/usr/bin/python

from cortex import app
import Pyro4

class CorpusActiveDirectory:
	
	def __init__(self, config):
		self.config = config

	## Connects to the CortexWindowsRPC daemon for the specified environment
	def connect_winrpc(self,env):
		# Check that we have the environment details
		if env not in self.config['WINRPC']:
			raise ValueError("No Cortex Windows RPC daemon configured for environment '" + env + "'")

		# Generate the host:port connection string
		conn_string = self.config['WINRPC'][env]['host'] + ':' + str(self.config['WINRPC'][env]['port'])

		# Connect to the appropriate Pyro4 daemon
		proxy = Pyro4.Proxy('PYRO:CortexWindowsRPC@' + conn_string)
		proxy._pyroHmacKey = self.config['WINRPC'][env]['key']
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
	def is_computer_object(self, env, hostname):
		return self.connect_winrpc(env).find_computer_object(hostname)

	################################################################################

	## Deletes a computer object exists in AD in the specified environment with the 
	## given hostname
	def delete_computer_object(self, env, hostname):
		return connect_winrpc(env).delete_computer_object(hostname)

