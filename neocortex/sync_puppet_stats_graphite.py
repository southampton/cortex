#!/usr/bin/python

from corpus import PuppetDBConnector
from urlparse import urljoin
import requests
import time

def run(helper, options):
	"""
	Sends Puppet Nodes stats to Graphite.
	I.e. the number of changed / failed unchanged nodes etc.
	"""

	# Create the PuppetDB object.
	helper.event('puppetdb_connect', 'Connecting to PuppetDB')
	puppet = PuppetDBConnector.PuppetDBConnector(
		host = helper.config['PUPPETDB_HOST'],
		port = helper.config['PUPPETDB_PORT'],
		ssl_cert = helper.config['PUPPETDB_SSL_CERT'],
		ssl_key = helper.config['PUPPETDB_SSL_KEY'],
		ssl_verify = helper.config['PUPPETDB_SSL_VERIFY'],
	)
	helper.end_event(description='Successfully connected to PuppetDB')

	# Get the nodes from PuppetDB.
	helper.event('puppet_nodes', 'Getting nodes from PuppetDB')
	nodes = puppet.get_nodes(with_status = True)
	helper.end_event(description='Received nodes from PuppetDB')

	# Initialise stats.
	count = 0
	unknown = 0
	stats = {
		'changed': 0,
		'unchanged': 0,
		'failed': 0,
		'unreported': 0,
		'noop': 0,
	}

	# Iterate over nodes.
	for node in nodes:
		# Count number of nodes (we can't do len(nodes) as it's a generator)
		count += 1

		if node.status in stats:
			stats[node.status] += 1
		else:
			unknown += 1

	# Put the remaining stats in our dictionary
	stats['count'] = count
	stats['unknown'] = unknown
	
	# Graphite URL and prefix.
	url = urljoin(helper.config['GRAPHITE_URL'],'/post-graphite')
	prefix = 'uos.puppet.stats.'
	stime = " " + str(int(time.time()))

	# Post stats to graphite.
	for key in stats:
		helper.event('post_graphite', 'Posting PuppetDB stat "{0}" to Graphite'.format(key))
		try:
			requests.post(url, data=(prefix + key + ' ' + str(stats[key]) + stime), auth=(helper.config['GRAPHITE_USER'], helper.config['GRAPHITE_PASS'])) 
		except Exception as e:
			helper.end_event(description='Failed to post "{0}" stat to Graphite. Exception: {1}'.format(key, str(e)), success=False)
		else:
			helper.end_event(description='Successfully sent "{0}" value {1} stat to Graphite.'.format(key, stats[key]))

