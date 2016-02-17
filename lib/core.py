#!/usr/bin/python

from cortex import app
from flask import g
import MySQLdb as mysql
import Pyro4
import re

################################################################################

def get_environments():
	return app.config['ENVIRONMENTS']

def get_puppet_environments():
	return [e for e in app.config['ENVIRONMENTS'] if e['puppet']]

def get_cmdb_environments():
	return [e for e in app.config['ENVIRONMENTS'] if e['cmdb']]

def get_environments_as_dict():
	return dict((e['id'], e) for e in app.config['ENVIRONMENTS'])

################################################################################

def neocortex_connect():
	"""This function connects to the neocortex job daemon using the Pyro4
	Remote Procedure Call (RPC) library."""

	# Connect, and perform some set up, including setting up a pre-shared
	# message signing key
	proxy = Pyro4.Proxy('PYRO:neocortex@localhost:1888')
	proxy._pyroHmacKey = app.config['NEOCORTEX_KEY']
	proxy._pyroTimeout = 5

	# Ping the server to ensure it's alive
	proxy.ping()

	return proxy

################################################################################

def vmware_list_clusters(tag):
	"""Return a list of clusters from within a given vCenter. The tag
	parameter defines an entry in the vCenter configuration dictionary that
	is within the application configuration."""

	if tag in app.config['VMWARE']:
		## SQL to grab the clusters from the cache
		cur = g.db.cursor(mysql.cursors.DictCursor)
		cur.execute("SELECT * FROM `vmware_cache_clusters` WHERE `vcenter` = %s", (app.config['VMWARE'][tag]['hostname']))
		return cur.fetchall()
	else:
		raise Exception("Invalid VMware tag")

################################################################################

def is_valid_hostname(hostname):
	"""Determines if a given hostname is valid"""

	if len(hostname) > 255:
		return False

	if hostname[-1] == ".":
		hostname = hostname[:-1]

	allowed = re.compile("(?!-)[A-Z\d-]{1,63}(?<!-)$", re.IGNORECASE)
	return all(allowed.match(x) for x in hostname.split("."))

################################################################################

def fqdn_strip_domain(fqdn):
	# n.b split always returns a list with 1 entry even if the seperator isnt found
	return fqdn.split('.')[0]

