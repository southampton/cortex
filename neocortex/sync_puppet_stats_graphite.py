
import time
from urllib.parse import urljoin

import MySQLdb as mysql
import requests

# bin/neocortex modifies sys.path so these are importable.
# pylint: disable=import-error
from corpus.puppetdb_connector import PuppetDBConnector
# pylint: enable=import-error

def run(helper, _options):
	"""
	Sends Puppet Nodes stats to Graphite.
	I.e. the number of changed / failed unchanged nodes etc.
	"""

	# Template for stats
	stats_template = {"count": 0, "unchanged": 0, "changed": 0, "noop": 0, "failed": 0, "unreported": 0, "unknown": 0}

	# Check config for Graphite stuff.
	helper.event('sync_puppet_stats_graphite_config_check', 'Checking we have the required configuration.')
	if all(key in helper.config for key in ['GRAPHITE_URL', 'GRAPHITE_USER', 'GRAPHITE_PASS']):
		helper.end_event(description='Required config is present.')

		# Create the PuppetDB object.
		helper.event('puppetdb_connect', 'Connecting to PuppetDB.')
		puppet = PuppetDBConnector(
			host=helper.config['PUPPETDB_HOST'],
			port=helper.config['PUPPETDB_PORT'],
			ssl_cert=helper.config['PUPPETDB_SSL_CERT'],
			ssl_key=helper.config['PUPPETDB_SSL_KEY'],
			ssl_verify=helper.config['PUPPETDB_SSL_VERIFY'],
		)
		helper.end_event(description='Successfully connected to PuppetDB.')

		# Initialise stats
		stats = {}

		# get the environments from the Cortex DB (Only select infra and service environments).
		helper.event('puppet_environments', 'Getting environments from PuppetDB.')
		curd = helper.db.cursor(mysql.cursors.DictCursor)
		curd.execute("SELECT `environment_name` FROM `puppet_environments` WHERE `type` < 2")
		environments = [row["environment_name"] for row in curd.fetchall()]
		helper.end_event(description='Received environments from PuppetDB.')

		for env in environments:
			stats[env] = stats_template.copy()

		# Query PuppetDB to get all node statuses
		helper.event('puppet_nodes', 'Getting nodes from PuppetDB.')
		node_statuses = puppet.query('nodes', query='["extract", ["certname", "report_environment", "latest_report_status", "latest_report_noop", "latest_report_hash"]]')
		helper.end_event(description='Received nodes from PuppetDB.')

		# Iterate over nodes, counting per-environment statistics
		for node in node_statuses:
			env = node["report_environment"]
			# Ensure the environment is in the stats dict
			if env not in stats:
				stats[env] = stats_template.copy()

			try:
				stats[env]["count"] += 1
				# use clientnoop fact to determine noop state
				if node["latest_report_noop"]:
					stats[env]["noop"] += 1
				# if we know the reported status, count the values
				elif node["latest_report_status"] in stats[env]:
					stats[env][node["latest_report_status"]] += 1
				# otherwise mark it as unknown but still count the values
				else:
					stats[env]["unknown"] += 1
			except (AttributeError, KeyError) as ex:
				helper.flash("Failed to generate Puppet node stat: %s" %(ex))

		# Graphite URL and prefix.
		url = urljoin(helper.config['GRAPHITE_URL'], '/post-graphite')
		prefix = 'uos.puppet.stats.'
		stime = str(int(time.time()))

		# Post stats to graphite.
		post_data = ''
		for env in stats:
			for status in stats[env]:
				post_data += prefix + env + '.' + status + ' ' + str(stats[env][status]) + ' ' + stime + '\n'

		helper.event('post_graphite', 'Posting PuppetDB Stats to Graphite')
		try:
			requests.post(url, data=post_data, auth=(helper.config['GRAPHITE_USER'], helper.config['GRAPHITE_PASS']))
		except Exception as e:
			helper.end_event(description='Failed to post stats to Graphite. Exception: {0}'.format(str(e)), success=False)
		else:
			helper.end_event(description='Successfully posted stats to Graphite.')
	else:
		helper.end_event(description='Task failed because the required configuration keys were not found.', success=False)
