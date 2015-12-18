from cortex import app
import cortex.core
from flask import Flask, request, session, redirect, url_for, flash, g, abort, make_response, jsonify
import os 
import re
import MySQLdb as mysql

@app.route('/api/puppet/enc/<certname>')
def api_puppet_enc(certname):
	"""Returns the YAML associated with the given node."""

	# The request should contain a parameter on the query string which contains
	# the authentication pre-shared key. Validate this:
	if 'auth_token' not in request.args:
		app.logger.error('auth_token missing from Puppet ENC API request (certname: ' + certname + ')')
		return abort(401)
	if request.args['auth_token'] != app.config['ENC_API_AUTH_TOKEN']:
		app.logger.error('Incorrect auth_token on request to Puppet ENC API (certname: ' + certname + ')')
		return abort(401)

	# Generate the Puppet configuration
	node_yaml = cortex.puppet.puppet_generate_config(certname)

	# If we don't get any configuration, return 404
	if node_yaml is None:
		return abort(404)

	# Make a response and return it
	r = make_response(node_yaml)
	r.headers['Content-Type'] = "application/x-yaml"
	return r
