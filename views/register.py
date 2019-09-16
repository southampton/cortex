from cortex import app
import cortex.lib.core
import cortex.lib.systems
import cortex.lib.core
from flask import Flask, request, session, redirect, url_for, flash, g, abort, make_response, jsonify, Response
import os
import re
import MySQLdb as mysql
import requests

################################################################################

@app.route('/api/register', methods=['POST'])
@app.disable_csrf_check
def api_register_system():
	"""API endpoint for when systems register with Cortex to obtain their
	   Puppet certificates, their Puppet environment, a satellite registration 
	   key, etc. Clients can authenticate either via username/password, which
	   is checked against LDAP, or via the VMware virtual machine UUID, which
	   is checked against the VMware systems cache."""

	# Clients can send hostname, username and password (interactive installation)
	if 'hostname' in request.form and 'username' in request.form and 'password' in request.form:

		# Get the hostname and remove the domain portions, if any
		# we want the 'short' hostname / the node name
		hostname = cortex.lib.core.fqdn_strip_domain(request.form['hostname'])

		# Match the hostname to a system record in the database
		system = cortex.lib.systems.get_system_by_name(hostname)

		if not system:
			app.logger.warn('Could not locate host in systems table for register API (hostname: ' + hostname + ')')
			abort(404)

		# LDAP username/password authentication
		if not cortex.lib.user.authenticate(request.form['username'], request.form['password']):
			app.logger.warn('Incorrect username/password when registering ' + hostname + ', username: ' + request.form['username'] + ')')
			abort(403)

		# LDAP authorisation
		if not cortex.lib.user.does_user_have_permission('api.register', request.form['username']):
			app.logger.warn('User does not have permission when attempting to register ' + hostname + ', username: ' + request.form['username'] + ')')
			abort(403)

		interactive = True

	# OR clients can send the vmware UUID as authentication instead (without a hostname)
	elif 'uuid' in request.form:
		# VMware UUID based authentication
		system = cortex.lib.systems.get_system_by_vmware_uuid(request.form['uuid'])

		if not system:
			app.logger.warn('Could not match VMware UUID to a system for the register API (UUID given: ' + request.form['uuid'].lower() + ')')
			abort(404)

		hostname = system['name']
		interactive = False

	else:
		app.logger.error('Neither UUID or host+username+password sent to authenticate')
		abort(401)

	# Increment the build count - this is perhaps useful for tracking rebuilds,
	# but also means we can generate a new unique password for each register,
	# which means that a person can't find a VMs original password by running
	# the register API call again
	cortex.lib.systems.increment_build_count(system['id'])

	# Build the node's fqdn
	fqdn = hostname + '.soton.ac.uk'

	# Start building the response dictionary
	cdata = {}

	# Default to production environment (for Puppet / Satellite)
	cdata['environment'] = 'production'

	# See if the system is linked to ServiceNow and we'll use that 
	# environment. If it isn't linked then we can't do much, so just assume
	# production (as above)
	if 'cmdb_environment' in system:
		envs = cortex.lib.core.get_cmdb_environments()
		for env in envs:
			if env['name'] == system['cmdb_environment']:
				cdata['environment'] = env['puppet']

	# Get the build identity from the request
	if 'ident' in request.form:
		ident = str(request.form['ident'])
	else:
		app.logger.warn('No build identity sent when attempting to register ' + hostname)
		abort(400)

	# Check that we know about the build identity
	if ident not in app.config['REGISTER_ACTIONS']:
		app.logger.warn('Unknown build identity (' + ident + ') sent when attempting to register ' + hostname)
		abort(400)

	# See if the build requires Puppet
	if 'puppet' in app.config['REGISTER_ACTIONS'][ident] and app.config['REGISTER_ACTIONS'][ident]['puppet'] is True:
		puppet_required = True
	else:
		puppet_required = False

	# See if the build requires Satellite
	if 'satellite' in app.config['REGISTER_ACTIONS'][ident] and app.config['REGISTER_ACTIONS'][ident]['satellite'] is True:
		satellite_required = True
	else:
		satellite_required = False

	# See if the build requires a random password
	if 'password' in app.config['REGISTER_ACTIONS'][ident] and app.config['REGISTER_ACTIONS'][ident]['password'] is True:
		password_required = True
	else:
		password_required = False

	if puppet_required:
		# Contact the cortex-puppet-bridge server to get ssl certificates for this hostname
		autosign_url = app.config['PUPPET_AUTOSIGN_URL']
		if not autosign_url.endswith('/'):
			autosign_url += '/'
		autosign_url += 'getcert/' + fqdn

		try:
			r = requests.get(autosign_url, headers={'X-Auth-Token': app.config['PUPPET_AUTOSIGN_KEY']}, verify=app.config['PUPPET_AUTOSIGN_VERIFY'])
		except Exception as ex:
			app.logger.error("Error occured contacting cortex-puppet-autosign server:" + str(ex))
			abort(500)

		if r.status_code == 200:
			try:
				pdata = r.json()
			except Exception as ex:
				app.logger.error("Error occured parsing response from cortex-puppet-autosign server:" + str(ex))
				abort(500)

			for key in ['private_key', 'public_key', 'cert']:
				if not key in pdata:
					app.logger.error("Error occured parsing response from cortex-puppet-autosign server. Parameter '" + key + "' was not sent.")
					abort(500)

				cdata[key] = pdata[key]
		else:
			app.logger.error("Error occured contacting cortex-puppet-autosign server. HTTP status code: '" + str(r.status_code) + "'")
			abort(500)
			
	# Systems authenticating by UUID also want to know their hostname and 
	# IP address in order to configure themselves!

	if not interactive:
		cdata['hostname']  = system['name']
		cdata['fqdn']      = fqdn
		netaddr = str(g.redis.get('vm/' + system['vmware_uuid'].lower() + '/ipaddress'), 'utf-8')
		if netaddr == None:
			cdata['ipaddress'] = 'dhcp'
		else:
			cdata['ipaddress'] = netaddr

		# Mark as done
		g.redis.setex("vm/" + system['vmware_uuid'] + "/" + "notify", 28800, "inprogress")

	# Add on some other details which could be useful to post-install
	cdata['user'] = system['allocation_who']

	# If the build requires a random password

	if password_required:
		# This password is repeatable, but random so long as SECRET_KEY is not compromised
		cdata['password'] = cortex.lib.systems.generate_repeatable_password(system['id'])

	# Create puppet ENC entry if it does not already exist
	if puppet_required:
		cdata['certname'] = fqdn

		create_entry = False
		if 'puppet_certname' in system:
			if system['puppet_certname'] == None:
				create_entry = True
		else:
			create_entry = True

		if create_entry:
			# A system record exists but no puppet_nodes entry. We'll create one!
			# We set the environment to what we determined above, which defaults
			# to production, but updates from the CMDB
			curd = g.db.cursor(mysql.cursors.DictCursor)
			curd.execute("INSERT INTO `puppet_nodes` (`id`, `certname`, `env`) VALUES (%s, %s, %s)", (system['id'], fqdn, cdata['environment']))
			g.db.commit()
			app.logger.info('Created Puppet ENC entry for certname "' + fqdn + '"')
		else:
			if 'puppet_env' in system:
				if system['puppet_env'] != None:
					cdata['environment'] = system['puppet_env']

	# Get the satellite registration key (if any)
	if satellite_required:
		if ident in app.config['SATELLITE_KEYS']:
			data = app.config['SATELLITE_KEYS'][ident]
			if cdata['environment'] in data:
				cdata['satellite_activation_key'] = data[cdata['environment']]
			else:
				app.logger.warn('No Satellite activation key configured for OS ident, ' + str(ident) + ' with environment ' + cdata['environment'] + ' - a Satellite activation key will not be returned')
		else:
			app.logger.warn('No Satellite activation keys configured for OS ident (' + str(ident) + ') - a Satellite activation key will not be returned')

	if interactive:
		cortex.lib.core.log(__name__, "api.register.system", "New system '" + fqdn + "' registered via the API by " + request.form['username'], username=request.form['username'])
	else:
		cortex.lib.core.log(__name__, "api.register.system", "New system '" + fqdn + "' registered via the API by VM-UUID authentication")

	return jsonify(cdata)

################################################################################

@app.route('/api/installer/notify', methods=['POST'])
@app.disable_csrf_check
def api_installer_notify():
	"""API endpoint to allow the bonemeal installer to notify cortex that the 
	the installation is now complete and is about to reboot."""

	if 'uuid' in request.form:
		# VMware UUID based authentication
		system = cortex.lib.systems.get_system_by_vmware_uuid(request.form['uuid'].lower())

		if not system:
			app.logger.warn('Could not match VMware UUID to a system for the installer notify API (UUID given: ' + request.form['uuid'].lower() + ')')
			abort(404)

		# Mark as done
		if 'warnings' in request.form and int(request.form['warnings']) > 0:
			g.redis.setex("vm/" + system['vmware_uuid'].lower() + "/" + "notify", 28800, "done-with-warnings")
		else:
			g.redis.setex("vm/" + system['vmware_uuid'].lower() + "/" + "notify", 28800, "done")

		return "OK"
	else:
		app.logger.warn('Missing \'uuid\' parameter in installer notify API')
		abort(401)
