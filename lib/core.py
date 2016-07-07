#!/usr/bin/python

from cortex import app
from flask import g
import MySQLdb as mysql
import Pyro4
import re
import ldap

################################################################################

def get_environments():
	"""Get all the information about all the environments."""

	return app.config['ENVIRONMENTS']

def get_puppet_environments():
	"""Get all the information about all the environments that have a 
	Puppet environment."""

	return [e for e in app.config['ENVIRONMENTS'] if e['puppet']]

def get_cmdb_environments():
	"""Get all the information about all the environments that have a 
	ServiceNow environment."""

	return [e for e in app.config['ENVIRONMENTS'] if e['cmdb']]

def get_environments_as_dict():
	"""Get all the information about all the environments but as a 
	dictionary keyed on the environment rather than an ordered list"""

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
	try:
		proxy.ping()
	except Pyro4.errors.PyroError as ex:
		app.fatal_error("task engine error","An error occured when connecting to the neocortex task engine: " + str(ex))

	return proxy

################################################################################

def vmware_list_clusters(tag):
	"""Return a list of clusters from within a given vCenter. The tag
	parameter defines an entry in the vCenter configuration dictionary that
	is within the application configuration."""

	if tag in app.config['VMWARE']:
		# SQL to grab the clusters from the cache
		curd = g.db.cursor(mysql.cursors.DictCursor)
		curd.execute("SELECT * FROM `vmware_cache_clusters` WHERE `vcenter` = %s", (app.config['VMWARE'][tag]['hostname']))
		return curd.fetchall()
	else:
		raise Exception("Invalid VMware tag")

################################################################################

def is_valid_hostname(hostname):
	"""Determines if a given hostname is valid"""

	if len(hostname) > 255:
		return False

	# Trim off any trailing dot
	if hostname[-1] == ".":
		hostname = hostname[:-1]

	# Build a regex to match on valid hostname components
	allowed = re.compile("(?!-)[A-Z\d-]{1,63}(?<!-)$", re.IGNORECASE)

	# Return true if all the parts of the hostname match the regex
	return all(allowed.match(x) for x in hostname.split("."))

################################################################################

def fqdn_strip_domain(fqdn):
	"""Strips the domain from a fully-qualified domain name, returning just
	the hostname name component"""

	# n.b split always returns a list with 1 entry even if the seperator isnt found
	return fqdn.split('.')[0]

################################################################################

def connect():
	# Connect to LDAP and turn off referrals
	conn = ldap.initialize(app.config['LDAP_URI'])
	conn.set_option(ldap.OPT_REFERRALS, 0)

	 # Bind to the server either with anon or with a defined user/pass in the config
	try:
		if app.config['LDAP_ANON_BIND']:
			conn.simple_bind_s()
		else:
			conn.simple_bind_s( (app.config['LDAP_BIND_USER']), (app.config['LDAP_BIND_PW']) )
	except ldap.LDAPError as e:
		flash('Internal Error - Could not connect to LDAP directory: ' + str(e), 'alert-danger')
		app.logger.error("Could not bind to LDAP: " + str(e))
		abort(500)

	return conn

