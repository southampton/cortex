#!/usr/bin/python

from cortex import app
from flask import g, url_for
import cortex.lib.netgroup
import MySQLdb as mysql
import yaml
import pypuppetdb

################################################################################

class CortexPuppetBaseAPI(pypuppetdb.BaseAPI):
	"""
	Override pypuppetdb.BaseAPI to prvoide better reporting.
	"""

	def reports(self, **kwargs):
		reports = self._query('reports', **kwargs)
		for report in reports:
			yield CortexPuppetReport( 
				api=self,
				node=report['certname'],
				hash_=report['hash'],
				start=report['start_time'],
				end=report['end_time'],
				received=report['receive_time'],
				version=report['configuration_version'],
				format_=report['report_format'],
				agent_version=report['puppet_version'],
				transaction=report['transaction_uuid'],
				environment=report['environment'],
				status=report['status'],
				noop=report.get('noop'),
				noop_pending=report.get('noop_pending'),
				metrics=report['metrics']['data'],
				logs=report['logs']['data'],
				code_id=report.get('code_id'),
				catalog_uuid=report.get('catalog_uuid'),
				cached_catalog_status=report.get('cached_catalog_status')
			)

class CortexPuppetReport(pypuppetdb.types.Report):
	"""
	Override pypuppetdb.types.Report to make the noop status available.
	"""

	def __init__(self, api, node, hash_, start, end, received, version, format_, agent_version, transaction, status=None, metrics={}, logs={}, environment=None, noop=False, noop_pending=False, code_id=None, catalog_uuid=None, cached_catalog_status=None, producer=None):
		# Call super init.
		super(CortexPuppetReport, self).__init__(api, node, hash_, start, end, received, version, format_, agent_version, transaction, status, metrics, logs, environment, noop, noop_pending, code_id, catalog_uuid, cached_catalog_status, producer)
		# Set noop
		self.noop=noop
		
def cortex_puppet_connect(host='localhost', port=8080, ssl_verify=False, ssl_key=None, ssl_cert=None, timeout=10, protocol=None, url_path='/', username=None, password=None, token=None):
	"""
	Cortex custom connect method for connecting to the PuppetDB API.
	"""
	return CortexPuppetBaseAPI(
		host=host, port=port,
		timeout=timeout, ssl_verify=ssl_verify, ssl_key=ssl_key,
		ssl_cert=ssl_cert, protocol=protocol, url_path=url_path,
		username=username, password=password, token=token
	)

################################################################################

def generate_node_config(certname):
	"""Generates a YAML document describing the configuration of a particular
	node given as 'certname'."""

	# Get a cursor to the database
	curd = g.db.cursor(mysql.cursors.DictCursor)

	# Get the Puppet node from the database
	curd.execute("SELECT `id`, `classes`, `variables`, `env`, `include_default` FROM `puppet_nodes` WHERE `certname` = %s", (certname,))
	node = curd.fetchone()

	# If we don't find the node, return nothing
	if node is None:
		return None

	# Get the system
	system = cortex.lib.systems.get_system_by_id(node['id'])

	# Get the Puppet default classes
	curd.execute("SELECT `value` FROM `kv_settings` WHERE `key` = 'puppet.enc.default'")
	default_classes = curd.fetchone()
	if default_classes is not None:
		default_classes = yaml.load(default_classes['value'])
	
		# YAML load can come back with no actual objects, e.g. comments, blank etc.
		if default_classes == None:
			default_classes = {}
		elif not isinstance(default_classes, dict):
			default_classes = {}
			app.logger.error("YAML Error: Parsing of default classes resulted in a string, did not result in a dictionary!")
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
		elif not isinstance(node_classes, dict):
			response['classes'] = {}
			app.logger.error("YAML Error: Parsing of node classes for node " + str(certname) + " did not result in a dictionary!")
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
		response['parameters']['uos_motd_sn_environment'] = 'ERROR: Not linked to ServiceNow. Visit: ' + url_for('system_edit', _external=True, id=system['id'])
		response['parameters']['uos_motd_sn_description'] = 'ERROR: Not linked to ServiceNow. Visit: ' + url_for('system_edit', _external=True, id=system['id'])
	else:
		response['parameters']['uos_motd_sn_environment'] = system['cmdb_environment']
		if system['cmdb_description'] is None or len(system['cmdb_description'].strip()) == 0:
			response['parameters']['uos_motd_sn_description'] = 'ERROR: Description not set in ServiceNow. Visit: ' + (app.config['CMDB_URL_FORMAT'] % system['cmdb_id'])
		else:
			response['parameters']['uos_motd_sn_description'] = system['cmdb_description']

	return yaml.safe_dump(response)

################################################################################

def puppetdb_connect():
	"""Connects to PuppetDB using the parameters specified in the 
	application configuration."""

	# Connect to PuppetDB
	return cortex_puppet_connect(app.config['PUPPETDB_HOST'], port=app.config['PUPPETDB_PORT'], ssl_cert=app.config['PUPPETDB_SSL_CERT'], ssl_key=app.config['PUPPETDB_SSL_KEY'], ssl_verify=app.config['PUPPETDB_SSL_VERIFY'])
	
################################################################################

def puppetdb_get_node_statuses(db=None):
	"""Gets the statuses of all the nodes"""

	if db is None:
		db = puppetdb_connect()

	# Get information about all the nodes, including their status
	nodes = db.nodes(with_status = True)

	# Iterate over nodes, counting statuses
	statuses = {}
	for node in nodes:
		statuses[node.name] = {
			'status': node.status,
			'clientnoop': node.fact('clientnoop').value
		}

	return statuses

################################################################################

def puppetdb_get_node_status(node_name, db=None):
	"""Gets the latest status of a a given node, where node_name is the Puppet certificate name"""

	if db is None:
		db = puppetdb_connect()

	# Get information about all the nodes, including their status
	nodes = db.nodes(with_status = True)

	# Iterate over nodes, looking for a specific node
	for node in nodes:
		if node.name == node_name:
			return node.status

	return None

################################################################################

def puppetdb_get_node_stats(db = None):
	"""Calculate statistics on node statuses by talking to PuppetDB"""

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

		# Check if the node is in noop.
		if node.fact('clientnoop').value:
			stats['noop'] += 1
		else:
			# Count the status types
			if node.status in stats:
				stats[node.status] += 1
			else:
				unknown += 1

	# Put the remaining stats in our dictionary
	stats['count'] = count
	stats['unknown'] = unknown

	return stats
