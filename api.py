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

	# Start building response
	response = {'environment': node['env']}

	# Decode YAML for classes
	if len(node['classes'].strip()) != 0:
		response['classes'] = yaml.load(node['classes'])
		if node['include_default']:
			response['classes']['uos_linux_base'] = None
	else:
		if node['include_default']:
			response['classes'] = {'uos_linux_base': None}

	# Decode YAML for environment
	variables = None
	if len(node['variables'].strip()) != 0:
		response['variables'] = yaml.load(node['variables'])

	# Make a response
	r = make_response(yaml.dump(response))
	r.headers['Content-Type'] = "application/x-yaml"

	return r
