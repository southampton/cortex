
import time
from urllib.parse import urljoin

import requests

# bin/neocortex modifies sys.path so these are importable.
# pylint: disable=import-error
from corpus.puppetdb_connector import PuppetDBConnector
# pylint: enable=import-error

# pylint: disable=too-many-branches,too-many-statements
def run(helper, _options):
	"""
	Sends Puppet Nodes stats to Graphite.
	I.e. the number of changed / failed unchanged nodes etc.
	"""
	# Check config for Graphite stuff.
	helper.event('sync_puppet_stats_graphite_config_check', 'Checking we have the required configuration.')
	if all(key in helper.config for key in ['GRAPHITE_URL', 'GRAPHITE_USER', 'GRAPHITE_PASS']):
		helper.end_event(description='Required config is present.')

		# Create the PuppetDB object.
		helper.event('puppetdb_connect', 'Connecting to PuppetDB.')
		puppet = PuppetDBConnector.PuppetDBConnector(
			host=helper.config['PUPPETDB_HOST'],
			port=helper.config['PUPPETDB_PORT'],
			ssl_cert=helper.config['PUPPETDB_SSL_CERT'],
			ssl_key=helper.config['PUPPETDB_SSL_KEY'],
			ssl_verify=helper.config['PUPPETDB_SSL_VERIFY'],
		)
		helper.end_event(description='Successfully connected to PuppetDB.')

		# get the environments from PuppetDB.
		helper.event('puppet_environments', 'Getting environments from PuppetDB.')
		environments = puppet.get_environments()
		helper.end_event(description='Received environments from PuppetDB.')

		# Initialise stats.
		stats = {}
		unknown = 0
		for env in environments:
			stats[env] = {
				'count': 0,
				'changed': 0,
				'unchanged': 0,
				'failed': 0,
				'unreported': 0,
				'noop': 0,
				'unknown': 0,
			}

		# Get the nodes from PuppetDB.
		helper.event('puppet_nodes', 'Getting nodes from PuppetDB.')
		nodes = puppet.get_nodes(with_status=True)
		helper.end_event(description='Received nodes from PuppetDB.')

		# Iterate over nodes.
		for node in nodes:

			env = node.report_environment

			if env in stats:
				# Count number of nodes (we can't do len(nodes) as it's a generator)
				stats[env]['count'] += 1

				if node.fact('clientnoop').value:
					stats[env]['noop'] += 1
				else:
					if node.status in stats[env]:
						stats[env][node.status] += 1
					else:
						stats[env]['unknown'] += 1
			else:
				unknown += 1

		# Graphite URL and prefix.
		url = urljoin(helper.config['GRAPHITE_URL'], '/post-graphite')
		prefix = 'uos.puppet.stats.'
		stime = str(int(time.time()))

		# Post stats to graphite.
		post_data = ''
		for env in stats:
			for status in stats[env]:
				post_data += prefix + env + '.' + status + ' ' + str(stats[env][status]) + ' ' + stime + '\n'

		post_data += prefix + 'global.unknown ' + str(unknown) + ' ' + stime + '\n'

		helper.event('post_graphite', 'Posting PuppetDB Stats to Graphite')
		try:
			requests.post(url, data=post_data, auth=(helper.config['GRAPHITE_USER'], helper.config['GRAPHITE_PASS']))
		except Exception as e:
			helper.end_event(description='Failed to post stats to Graphite. Exception: {0}'.format(str(e)), success=False)
		else:
			helper.end_event(description='Successfully posted stats to Graphite.')
	else:
		helper.end_event(description='Task failed because the required configuration keys were not found.', success=False)
