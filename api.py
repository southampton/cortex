from cortex import app
import cortex.core
from flask import Flask, request, session, redirect, url_for, flash, g, abort, make_response, jsonify
import os 
import re
import MySQLdb as mysql
import yaml

@app.route('/api/puppet/enc/<certname>')
def api_puppet_enc(certname):
	"""Returns the YAML associated with the given node."""

	# Get a cursor to the database
	cur = g.db.cursor(mysql.cursors.DictCursor)

	# Get the task
	cur.execute("SELECT `classes`, `variables`, `env`, `include_default` FROM `puppet_nodes` WHERE `certname` = %s", (certname,))
	node = cur.fetchone()

	cur.execute("SELECT `value` FROM `kv_settings` WHERE `key` = 'puppet.enc.default'")
	default_classes = cur.fetchone()
	if default_classes is not None:
		default_classes = yaml.load(default_classes['value'])
	
		## yaml load can come back with no actual objects, e.g. comments, blank etc.
		if default_classes == None:
			default_classes = {}
	else:
		default_classes = {}


	# Start building response
	response = {'environment': node['env']}

	# Decode YAML for classes
	if len(node['classes'].strip()) != 0:
		response['classes'] = yaml.load(node['classes'])
		if node['include_default']:

			for classname in default_classes:
				if not classname in response['classes']:
					response['classes'][classname] = default_classes[classname]

	else:
		if node['include_default']:
			response['classes'] = default_classes

	# Decode YAML for environment
	variables = None
	if len(node['variables'].strip()) != 0:
		response['variables'] = yaml.load(node['variables'])

	# Make a response
	r = make_response(yaml.dump(response))
	r.headers['Content-Type'] = "application/x-yaml"

	return r
