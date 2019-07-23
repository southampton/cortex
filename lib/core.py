#!/usr/bin/python

from cortex import app
from cortex.lib.errors import fatalerr
from flask import g, abort, make_response, render_template, request, session
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

def vmware_list_folders(tag):
	"""Return a list of folders from witihin a given vCenter. The tag
	parameter defines an entry in the vCenter configuration dictionary that
	is within the application configuration."""
	
	if tag in app.config['VMWARE']:
		curd = g.db.cursor(mysql.cursors.DictCursor)

		# SQL to grab the datacenters from the cache into a dictionary
		curd.execute("SELECT * FROM `vmware_cache_datacenters` WHERE `vcenter` = %s", (app.config['VMWARE'][tag]['hostname'],))
		result = curd.fetchall()
		dcs_dict = {dc['id']: dc for dc in result}

		# SQL to grab the clusters from the cache into a dictionary
		curd.execute("SELECT * FROM `vmware_cache_folders` WHERE `vcenter` = %s", (app.config['VMWARE'][tag]['hostname'],))
		result = curd.fetchall()
		folders_dict = {folder['id']: folder for folder in result}

		folders = []
		for folder_id in folders_dict:
			# Start the fully qualified path with the name of the folder
			fully_qualified = folders_dict[folder_id]['name']

			# Recurse up the tree
			recurse_folder = folders_dict[folder_id]
			while recurse_folder['parent'] is not None:
				try:
					recurse_folder = folders_dict[recurse_folder['parent']]
					if recurse_folder is not None:
						# Add on the parent folder name to the front
						fully_qualified = recurse_folder['name'] + "\\" + fully_qualified
				except KeyError as e:
					# We hit KeyErrors when we reach the "folder" that is the datecenter object
					break

			# Add the datacenter object name on the front
			folders_dict[folder_id]['fully_qualified_path'] = dcs_dict[folders_dict[folder_id]['did']]['name'] + "\\" + fully_qualified

			# Append this to our array
			folders.append(folders_dict[folder_id])

		return folders
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

def tasks_where_query(*args, **kwargs):
	# Build the query parts
	query_parts = []
	query_params = []
	for key in kwargs:
		if key in ['module', 'username', 'status']:
			if kwargs[key] is not None:
				query_parts.append("`" + key + "` = %s")
				query_params.append(kwargs[key])
		else:
			raise TypeError("tasks_where_query() got an unexpected keyword argument '" + key + "'")

	if len(query_parts) > 0:
		return (" WHERE " + " AND ".join(query_parts), tuple(query_params))
	else:
		return ("", ())

################################################################################

def tasks_count(*args, **kwargs):
	# Get a cursor to the database
	curd = g.db.cursor(mysql.cursors.DictCursor)

	(where_clause, query_params) = tasks_where_query(**kwargs)
	curd.execute("SELECT COUNT(*) AS `count` FROM `tasks`" + where_clause, tuple(query_params))

	return curd.fetchone()['count']

################################################################################

def tasks_get(order = None, limit_start = None, limit_length = None, *args, **kwargs):
	# Get a cursor to the database
	curd = g.db.cursor(mysql.cursors.DictCursor)

	# Build the query
	(where_clause, query_params) = tasks_where_query(**kwargs)
	query = "SELECT `id`, `module`, `username`, `start`, `end`, `status`, `description` FROM `tasks`" + where_clause

	if order in ['id', 'module', 'username', 'start', 'end', 'status', 'description']:
		query = query + " ORDER BY `" + order + "`"

	if limit_start is not None and limit_length is not None:
		query = query + " LIMIT " + str(int(limit_start)) + "," + str(int(limit_length))

	# Get the task
	curd.execute(query, tuple(query_params))
	return curd.fetchall()

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
	curd.execute("SELECT `id`, `source`, `related_id`, `name`, `username`, `desc`, `status`, `start`, `end` FROM `events` WHERE `related_id` = %s AND `source` = 'neocortex.task' ORDER BY `start`, `id`", (task['id'],))
	events = curd.fetchall()

	return make_response((render_template(template, id=task['id'], task=task, events=events, title="Task Status"), 200, {'Cache-Control': 'no-cache'}))

################################################################################

def log(source, name, desc, username=None, related_id=None, success=True):
	"""
	Record a message in the 'events' table, i.e. generate a log record

	Args:
		source: The name of the function generating this log event. Use __name__
		name: The name of the event that has taken place
		desc: A description
		username: The username. Defaults to None, which will use the username from session.
		related_id: An ID of the element in a table this event refers to. Defaults to None.
		success: Was this 'event' succcessful? Generally, you don't need to use this. Defaults to True.

	Returns:
		Nothing

	Raises:
		Nothing
	"""

	if not source.startswith("cortex."):
		source = "cortex." + source

	if username is None:
		username = session.get('username', None)

	if success:
		status = 1
	else:
		status = 2

	app.logger.info(str(source) + ',' + str(related_id) + ',' + str(name) + ',' + str(username) + ',' + str(desc))

	try:
		cur    = g.db.cursor()
		stmt   = 'INSERT INTO `events` (`source`, `related_id`, `name`, `username`, `desc`, `status`, `ipaddr`, `start`, `end`) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), NOW())'
		params = (source, related_id, name, username, desc, status, request.remote_addr)
		cur.execute(stmt, params)
		g.db.commit()
	except Exception as e:
		pass
