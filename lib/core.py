#!/usr/bin/python

from cortex import app
from cortex.lib.errors import fatalerr
from flask import g, abort, make_response, render_template
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
		abort(fatalerr(message="An error occured when connecting to the neocortex task engine: " + str(ex)))

	return proxy

################################################################################

def vmware_list_clusters(tag):
	"""Return a list of clusters from within a given vCenter. The tag
	parameter defines an entry in the vCenter configuration dictionary that
	is within the application configuration."""

	if tag in app.config['VMWARE']:
		# SQL to grab the clusters from the cache
		curd = g.db.cursor(mysql.cursors.DictCursor)
		curd.execute("SELECT * FROM `vmware_cache_clusters` WHERE `vcenter` = %s", (app.config['VMWARE'][tag]['hostname'],))
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

def task_get(id):
	# Get a cursor to the database
	curd = g.db.cursor(mysql.cursors.DictCursor)

	# Get the task
	curd.execute("SELECT `id`, `module`, `username`, `start`, `end`, `status`, `description` FROM `tasks` WHERE id = %s", (id,))
	task = curd.fetchone()

	return task

################################################################################

def task_render_status(task, template):
	# Get the events for the task
	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute("SELECT `id`, `source`, `related_id`, `name`, `username`, `desc`, `status`, `start`, `end` FROM `events` WHERE `related_id` = %s AND `source` = 'neocortex.task' ORDER BY `start`", (task['id'],))
	events = curd.fetchall()

	return make_response((render_template(template, id=task['id'], task=task, events=events, title="Task Status"), 200, {'Cache-Control': 'no-cache'}))

################################################################################

def log(source, name, desc, username=None, related_id=None):
	if username is None:
		username = session.get('username', None)
	try:
		cur = g.db.cursor()
		stmt = 'INSERT INTO `events` (`source`, `related_id`, `name`, `username`, `desc`, `status`, `start`, `end`) VALUES (%s, %s, %s, %s, %s, 2, NOW(), NOW())'
		params = (source, related_id, name, username, desc)
		cur.execute(stmt, params)
		g.db.commit()
	except Exception as e:
		pass
