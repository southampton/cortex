#!/usr/bin/python

from cortex import app
from flask import g, url_for
import cortex.lib.netgroup
import MySQLdb as mysql
import yaml
import pypuppetdb

################################################################################

def generate_node_config(certname):
	"""Generates a YAML document describing the configuration of a particular
	node given as 'certname'."""

	# Get a cursor to the databaseo
	curd = g.db.cursor(mysql.cursors.DictCursor)

	# Get the task
	curd.execute("SELECT `id`, `classes`, `variables`, `env`, `include_default` FROM `puppet_nodes` WHERE `certname` = %s", (certname,))
	node = curd.fetchone()

	# If we don't find the node, return nothing
	if node is None:
		return None

	# Get the system
	system = cortex.lib.systems.get_system_by_id(node['id'])

	curd.execute("SELECT `value` FROM `kv_settings` WHERE `key` = 'puppet.enc.default'")
	default_classes = curd.fetchone()
	if default_classes is not None:
		default_classes = yaml.load(default_classes['value'])
	
		# YAML load can come back with no actual objects, e.g. comments, blank etc.
		if default_classes == None:
			default_classes = {}
	else:
		default_classes = {}

	# Start building response
	response = {'environment': node['env']}

	# Decode YAML for classes from the node
	if len(node['classes'].strip()) != 0:
		node_classes = yaml.load(node['classes'])

		# YAML load can come back with no actual objects, e.g. comments, blank etc.
		if node_classes == None:
			response['classes'] = {}
		else:
			response['classes'] = node_classes
	else:
		response['classes'] = {}

	# Find all netgroups this node is a member of to load in their classes too
	curd.execute("SELECT `name`, `classes` FROM `puppet_groups` ORDER BY `name`")
	groups = curd.fetchall()

	for group in groups:
		if group['classes'] == None:
			continue

		if cortex.lib.netgroup.contains_host(certname,group['name']):

			# Convert from YAML to python types for the classes for this group
			group_classes = yaml.load(group['classes'])

			# If there are classes within that
			if not group_classes == None:
				# Get the name of each class
				for classname in group_classes:
					# And if the class hasn't already been loaded by the node...
					if not classname in response['classes']:
						# import this class and its params too
						response['classes'][classname] = group_classes[classname]

	if node['include_default']:
		# Load in global default classes too, unless we already loaded settings for those class names
		for classname in default_classes:
			if not classname in response['classes']:
				response['classes'][classname] = default_classes[classname]

	# Decode YAML for environment (Puppet calls them parameters, but we call them [global] variables)
	variables = None
	if len(node['variables'].strip()) != 0:
		params = yaml.load(node['variables'])

		if not params == None:
			response['parameters'] = params
		else:
			response['parameters'] = {}
	else:
		response['parameters'] = {}

	# Add in (and indeed potentially overwrite) some auto-generated variables
	if 'cmdb_id' not in system or system['cmdb_id'] is None or len(system['cmdb_id'].strip()) == 0:
		# Not linked to a ServiceNow entry, put in some defaults
		response['parameters']['uos_motd_sn_environment'] = 'ERROR: Not linked to ServiceNow. Visit: ' + url_for('systems_edit', _external=True, id=system['id'])
		response['parameters']['uos_motd_sn_description'] = 'ERROR: Not linked to ServiceNow. Visit: ' + url_for('systems_edit', _external=True, id=system['id'])
	else:
		response['parameters']['uos_motd_sn_environment'] = system['cmdb_environment']
		if system['cmdb_description'] is None or len(system['cmdb_description'].strip()) == 0:
			response['parameters']['uos_motd_sn_description'] = 'ERROR: Description not set in ServiceNow. Visit: ' + (app.config['CMDB_URL_FORMAT'] % system['cmdb_id'])
		else:
			response['parameters']['uos_motd_sn_description'] = system['cmdb_description']

	return yaml.dump(response)

################################################################################

def puppetdb_connect():
	"""Connects to PuppetDB using the parameters specified in the 
	application configuration."""

	# Connect to PuppetDB
	return pypuppetdb.connect(app.config['PUPPETDB_HOST'], port=app.config['PUPPETDB_PORT'], ssl_cert=app.config['PUPPETDB_SSL_CERT'], ssl_key=app.config['PUPPETDB_SSL_KEY'], ssl_verify=app.config['PUPPETDB_SSL_VERIFY'])

################################################################################

def puppetdb_get_node_stats(db = None):
	if db is None:
		db = puppetdb_connect()

	# Get information about all the nodes, including their status
	nodes = db.nodes(with_status = True)

	# Initialise stats
	count = 0
	stats = {
		'changed': 0,
		'unchanged': 0,
		'failed': 0,
		'unreported': 0,
		'noop': 0,
	}
	unknown = 0

	# Iterate over nodes, counting statii
	for node in nodes:
		# Count number of nodes (we can't do len(nodes) as it's a generator)
		count += 1

		# Count the status types
		if node.status in stats:
			stats[node.status] += 1
		else:
			unknown += 1

	# Put the remaining stats in our dictionary
	stats['count'] = count
	stats['unknown'] = unknown

	return stats
