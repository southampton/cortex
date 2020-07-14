
from datetime import datetime, timedelta

import MySQLdb as mysql
import pypuppetdb
import yaml
from flask import g, session, url_for
from pypuppetdb.QueryBuilder import EqualsOperator
from pypuppetdb.utils import json_to_datetime

import cortex.lib.systems
from cortex import app

################################################################################

# pylint: disable=too-many-branches
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

	def nodes(self, unreported=2, with_status=False, **kwargs):
		nodes = self._query('nodes', **kwargs)
		now = datetime.utcnow()
		# If we happen to only get one node back it
		# won't be inside a list so iterating over it
		# goes boom. Therefor we wrap a list around it.
		if isinstance(nodes, dict):
			nodes = [nodes, ]

		if with_status:
			latest_events = self.event_counts(
				query=EqualsOperator("latest_report?", True),
				summarize_by='certname'
			)

		for node in nodes:
			node['status_report'] = None
			node['events'] = None

			if with_status:
				status = [s for s in latest_events if s['subject']['title'] == node['certname']]

				try:
					node['status_report'] = node['latest_report_status']

					if status:
						node['events'] = status[0]
				except KeyError:
					if status:
						node['events'] = status = status[0]
						if status['successes'] > 0:
							node['status_report'] = 'changed'
						if status['noops'] > 0:
							node['status_report'] = 'noop'
						if status['failures'] > 0:
							node['status_report'] = 'failed'
					else:
						node['status_report'] = 'unchanged'

				# node report age
				if node['report_timestamp'] is not None:
					try:
						last_report = json_to_datetime(
							node['report_timestamp'])
						last_report = last_report.replace(tzinfo=None)
						unreported_border = now - timedelta(hours=unreported)
						if last_report < unreported_border:
							delta = (now - last_report)
							node['unreported'] = True
							node['unreported_time'] = '{0}d {1}h {2}m'.format(
								delta.days,
								int(delta.seconds / 3600),
								int((delta.seconds % 3600) / 60)
							)
					except AttributeError:
						node['unreported'] = True

				if not node['report_timestamp']:
					node['unreported'] = True

			yield CortexPuppetNode(
				self,
				name=node['certname'],
				deactivated=node['deactivated'],
				expired=node['expired'],
				report_timestamp=node['report_timestamp'],
				catalog_timestamp=node['catalog_timestamp'],
				facts_timestamp=node['facts_timestamp'],
				status_report=node['status_report'],
				noop=node.get('latest_report_noop'),
				noop_pending=node.get('latest_report_noop_pending'),
				events=node['events'],
				unreported=node.get('unreported'),
				unreported_time=node.get('unreported_time'),
				report_environment=node['report_environment'],
				catalog_environment=node['catalog_environment'],
				facts_environment=node['facts_environment'],
				latest_report_hash=node.get('latest_report_hash'),
				cached_catalog_status=node.get('cached_catalog_status')
			)

class CortexPuppetReport(pypuppetdb.types.Report):
	"""
	Override pypuppetdb.types.Report to make the noop status available.
	"""

	# pylint: disable=dangerous-default-value
	def __init__(self, api, node, hash_, start, end, received, version, format_, agent_version, transaction, status=None, metrics={}, logs={}, environment=None, noop=False, noop_pending=False, code_id=None, catalog_uuid=None, cached_catalog_status=None, producer=None):
		# Call super init.
		super(CortexPuppetReport, self).__init__(api, node, hash_, start, end, received, version, format_, agent_version, transaction, status, metrics, logs, environment, noop, noop_pending, code_id, catalog_uuid, cached_catalog_status, producer)
		# Set noop
		self.noop = noop

class CortexPuppetNode(pypuppetdb.types.Node):
	"""
	Override pypuppetdb.types.Node to make the noop status available.
	"""

	def __init__(self, api, name, deactivated=None, expired=None, report_timestamp=None, catalog_timestamp=None, facts_timestamp=None, status_report=None, noop=False, noop_pending=False, events=None, unreported=False, unreported_time=None, report_environment='production', catalog_environment='production', facts_environment='production', latest_report_hash=None, cached_catalog_status=None):
		# Call super init.
		super(CortexPuppetNode, self).__init__(api, name, deactivated, expired, report_timestamp, catalog_timestamp, facts_timestamp, status_report, noop, noop_pending, events, unreported, unreported_time, report_environment, catalog_environment, facts_environment, latest_report_hash, cached_catalog_status)
		# Set noop.
		self.noop = noop

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
	return cortex_puppet_connect(app.config['PUPPETDB_HOST'], port=app.config['PUPPETDB_PORT'], ssl_cert=app.config['PUPPETDB_SSL_CERT'], ssl_key=app.config['PUPPETDB_SSL_KEY'], ssl_verify=app.config['PUPPETDB_SSL_VERIFY'])

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
			'clientnoop': node.noop,
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
			if node.noop:
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
