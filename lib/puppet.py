import MySQLdb as mysql
import pypuppetdb
import yaml
from flask import g, session, url_for

import cortex.lib.systems
from cortex import app

################################################################################

def get_puppet_environments(enviroment_type=None, environment_permission=None, user=None, include_default=False, order_by="id"):
	"""Return a list of the Puppet environments defined in `puppet_environments`"""
	query = "SELECT * FROM `puppet_environments`"
	params = ()

	if enviroment_type is not None:
		query += " WHERE `type`=%s"
		params += (enviroment_type,)
	if environment_permission is not None:
		if enviroment_type is not None:
			query += " AND "
		else:
			query += " WHERE "

		# Get the username or use the one present in the session.
		username = user or session.get("username")
		if username is None:
			return []

		if include_default:
			query += "( `environment_name`=%s OR ("
			params += (app.config["PUPPET_DEFAULT_ENVIRONMENT"],)

		query += "`id` IN (SELECT `environment_id` FROM `p_puppet_perms_view` WHERE `perm`=%s AND ((`who_type`=0 AND `who`=%s) OR (`who_type`=1 AND `who` IN (SELECT `group` FROM `ldap_group_cache` WHERE `username`=%s))))"
		params += (environment_permission, username, username)

		if include_default:
			query += "))"

	if order_by:
		query += " ORDER BY `{field}` ASC".format(field=order_by)

	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute(query, params)
	return curd.fetchall()

################################################################################

def get_puppetdb_environments(db=None, whitelist=None):
	"""Get Puppet environments from the PuppetDB, if `whitelist` is set then
	this will whitelist against these environment names"""

	if db is None:
		db = puppetdb_connect()

	if whitelist is not None and not isinstance(whitelist, list):
		whitelist = [whitelist]

	return [e["name"] for e in db.environments() if whitelist is None or e["name"] in whitelist]

################################################################################

# pylint: disable=too-many-branches,too-many-statements
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
		default_classes = yaml.safe_load(default_classes['value'])

		# YAML load can come back with no actual objects, e.g. comments, blank etc.
		if default_classes is None:
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
		node_classes = yaml.safe_load(node['classes'])

		# YAML load can come back with no actual objects, e.g. comments, blank etc.
		if node_classes is None:
			response['classes'] = {}
		elif not isinstance(node_classes, dict):
			response['classes'] = {}
			app.logger.error("YAML Error: Parsing of node classes for node " + str(certname) + " did not result in a dictionary!")
		else:
			response['classes'] = node_classes
	else:
		response['classes'] = {}

	if node['include_default']:
		# Load in global default classes too, unless we already loaded settings for those class names
		for classname in default_classes:
			if not classname in response['classes']:
				response['classes'][classname] = default_classes[classname]

	# Decode YAML for environment (Puppet calls them parameters, but we call them [global] variables)
	if len(node['variables'].strip()) != 0:
		params = yaml.safe_load(node['variables'])

		if not params is None:
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
		# The 'uos_environment' will default to Production
		response['parameters']['uos_environment'] = 'Production'
	else:
		response['parameters']['uos_motd_sn_environment'] = system['cmdb_environment']
		if system['cmdb_description'] is None or len(system['cmdb_description'].strip()) == 0:
			response['parameters']['uos_motd_sn_description'] = 'ERROR: Description not set in ServiceNow. Visit: ' + (app.config['CMDB_URL_FORMAT'] % system['cmdb_id'])
		else:
			response['parameters']['uos_motd_sn_description'] = system['cmdb_description']
		# The 'uos_environment' will become 'cmdb_environment'
		response['parameters']['uos_environment'] = system['cmdb_environment']

	return yaml.safe_dump(response, sort_keys=True)

################################################################################

def puppetdb_connect():
	"""Connects to PuppetDB using the parameters specified in the
	application configuration."""

	# Connect to PuppetDB
	return pypuppetdb.connect(app.config['PUPPETDB_HOST'], port=app.config['PUPPETDB_PORT'], ssl_cert=app.config['PUPPETDB_SSL_CERT'], ssl_key=app.config['PUPPETDB_SSL_KEY'], ssl_verify=app.config['PUPPETDB_SSL_VERIFY'])

################################################################################

def puppetdb_query(endpoint, db=None, **kwargs):
	"""Peform direct queries against the PuppetDB"""

	if db is None:
		db = puppetdb_connect()

	# pylint: disable=protected-access
	return db._query(endpoint, **kwargs)

################################################################################

def puppetdb_get_node_statuses(db=None):
	"""Gets the statuses of all the nodes"""

	if db is None:
		db = puppetdb_connect()

	# Get information about all the nodes, including their status
	nodes = db.nodes(with_status=True)

	# Iterate over nodes, counting statuses
	statuses = {}
	for node in nodes:
		statuses[node.name] = {
			'status': node.status,
			'clientnoop': bool(node.fact("clientnoop").value),
			'latest_report_hash': node.latest_report_hash,
		}

	return statuses

################################################################################

def puppetdb_get_node_status(node_name, db=None):
	"""Gets the latest status of a a given node, where node_name is the Puppet certificate name"""

	if db is None:
		db = puppetdb_connect()

	# Get information about all the nodes, including their status
	nodes = db.nodes(with_status=True)

	# Iterate over nodes, looking for a specific node
	for node in nodes:
		if node.name == node_name:
			return node.status

	return None

################################################################################

def puppetdb_get_node_stats(db=None, whitelist=None):
	"""Calculate statistics on node statuses by talking to PuppetDB"""

	if db is None:
		db = puppetdb_connect()

	# Get information about all the nodes, including their status
	nodes = db.nodes(with_status=True)

	# Initialise stats
	stats = {
		'count': {},
		'changed': {},
		'unchanged': {},
		'failed': {},
		'unreported': {},
		'noop': {},
		'unknown':{}
	}

	environments = ['count',] + get_puppetdb_environments(db=db, whitelist=whitelist)

	for k in stats:
		for e in environments:
			stats[k][e] = 0

	# Iterate over nodes, counting statii
	for node in nodes:
		try:
			if bool(node.fact("clientnoop").value):
				# count all the values for noop
				stats['noop'][node.report_environment] += 1
				stats['noop']['count'] += 1
				stats['count'][node.report_environment] += 1
			else:
				# if we know the reported status, count the values
				if node.status in stats:
					stats[node.status][node.report_environment] += 1
					stats[node.status]['count'] += 1
					stats['count'][node.report_environment] += 1
				# otherwise mark it as unknown but still count the values
				else:
					stats['unknown'][node.report_environment] += 1
					stats['unknown']['count'] += 1
					stats['count'][node.report_environment] += 1
		except (AttributeError, KeyError) as ex:
			app.logger.warning('Failed to generate Puppet node stat: %s' %(ex))

	# get the total count number here
	stats['count']['count'] = sum(stats['count'].values())

	return stats
