from cortex import app
import cortex.core
from flask import Flask, request, session, redirect, url_for, flash, g, abort, make_response, jsonify, Response
import os 
import re
import MySQLdb as mysql
import yaml
from cortex.systems import systems_csv_stream

################################################################################

@app.route('/api/systems/csv', methods=['POST'])
@app.disable_csrf_check
def api_systems_csv():
	"""Returns a CSV file, much like the /systems/download/csv but with API
	auth rather than normal auth."""

	# The request should contain a parameter in the passed form which
	# contains the authentication pre-shared key. Validate this:
	if 'auth_token' not in request.form:
		app.logger.warn('auth_token missing from Systems API request')
		return abort(401)
	if request.form['auth_token'] != app.config['CORTEX_API_AUTH_TOKEN']:
		app.logger.warn('Incorrect auth_token on request to Systems API')
		return abort(401)

	# Get the list of systems
	cur = cortex.core.get_systems(return_cursor=True)

	# Return the response (systems_csv_stream is in systems.py)
	return Response(systems_csv_stream(cur), mimetype="text/csv", headers={'Content-Disposition': 'attachment; filename="systems.csv"'})
	
################################################################################

@app.route('/api/puppet/enc/<certname>', methods=['POST'])
@app.disable_csrf_check
def api_puppet_enc(certname):
	"""Returns the YAML associated with the given node."""

	# The request should contain a parameter in the passed form which 
	# contains the autthentication pre-shared key. Validate this:
	if 'auth_token' not in request.form:
		app.logger.warn('auth_token missing from Puppet ENC API request (certname: ' + certname + ')')
		return abort(401)
	if request.form['auth_token'] != app.config['ENC_API_AUTH_TOKEN']:
		app.logger.warn('Incorrect auth_token on request to Puppet ENC API (certname: ' + certname + ')')
		return abort(401)

	if not cortex.core.is_valid_hostname(certname):
		app.logger.warn('Invalid certname presented to Puppet ENC API (certname: ' + certname + ')')
		abort(400)

	# Generate the Puppet configuration
	node_yaml = cortex.puppet.puppet_generate_config(certname)

	# If we don't get any configuration, return 404
	if node_yaml is None:
		return abort(404)

	# Make a response and return it
	r = make_response(node_yaml)
	r.headers['Content-Type'] = "application/x-yaml"
	return r

################################################################################

@app.route('/api/puppet/enc-enable/<certname>', methods=['GET','POST'])
@app.disable_csrf_check
def api_puppet_enc_enable(certname):
	"""Ensures a particular server name is added to the Puppet ENC. This
	is usually done as part of a VM workflow, but for physical boxes and manually
	installed systems a name will have been allocated but not added to the Puppet
	ENC and won't recieve any base configuration. This API endpoint tries to match the
	certname against an entry in the systems table and then adds it into the Puppet nodes
	table so the ENC will return results for it. It only accepts node names ending in .soton.ac.uk
	which is all the ENC supports.

	The response is YAML containing the environment of the node."""

	# The request should contain a parameter on the query string which contains
	# the authentication pre-shared key. Validate this:
	if 'auth_token' not in request.form:
		app.logger.error('auth_token missing from Puppet Node Enable API request (certname: ' + certname + ')')
		return abort(401)
	if request.form['auth_token'] != app.config['ENC_API_AUTH_TOKEN']:
		app.logger.error('Incorrect auth_token on request to Puppet Node Enable API (certname: ' + certname + ')')
		return abort(401)

	## First ensure the hostname is of the form "name.soton.ac.uk"
	if not cortex.core.is_valid_certname(certname):
		app.logger.warn('Invalid certname presented to Puppet Node Enable API (certname: ' + certname + ')')
		abort(400)

	## Remove the .soton.ac.uk
	system_name = certname.replace(".soton.ac.uk","")

	## Match an entry in the systems table
	system = cortex.core.get_system_by_name(system_name)

	if not system:
		app.logger.warn('Could not match certname to a system name on request to the Puppet Node Enable API (certname: ' + certname + ')')
		abort(404)

	node_yaml = {}

	## Create puppet ENC entry if it does not already exist
	if 'puppet_certname' in system:
		if system['puppet_certname'] == None:
			curd = g.db.cursor(mysql.cursors.DictCursor)
			curd.execute("INSERT INTO `puppet_nodes` (`id`, `certname`, `environment`) VALUES (%s, %s, 'production')", (system['id'], certname))
			g.db.commit()
			app.logger.info('Created Puppet ENC entry for certname "' + certname + '"')
			node_yaml['environment'] = 'production'
	else:
		node_yaml['environment'] = system['puppet_environment']

	node_yaml['certname'] = certname
	response = make_response(node_yaml)
	response.headers['Content-Type'] = "application/x-yaml"
	return response	
