from cortex import app
import cortex.lib.core
import cortex.lib.systems
from flask import Flask, request, session, redirect, url_for, flash, g, abort, make_response, jsonify, Response
import os 
import re
import MySQLdb as mysql
import requests

################################################################################

@app.route('/api/register', methods=['POST'])
@app.disable_csrf_check
def api_register_system():
	"""API endpoint for when linux systems register with Cortex to obtain their
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
		if not cortex.lib.user.is_global_admin(request.form['username']):
			app.logger.warn('Non-admin user attempted to register ' + hostname + ', username: ' + request.form['username'] + ')')
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
		abort(401)

	# Build the node's fqdn
	fqdn = hostname + '.soton.ac.uk'

	# Contact the puppet-autosign server to get ssl certificates for this hostname
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
			cdata = r.json()
		except Exception as ex:
			app.logger.error("Error occured parsing response from cortex-puppet-autosign server:" + str(ex))
			abort(500)

		for key in ['private_key', 'public_key', 'cert']:
			if not key in cdata:
				app.logger.error("Error occured parsing response from cortex-puppet-autosign server. Parameter '" + key + "' was not sent.")
				abort(500)
	else:
		app.logger.error("Error occured contacting cortex-puppet-autosign server. HTTP status code: '" + str(r.status_code) + "'")
		abort(500)
			
	# Systems authenticating by UUID also want to know their hostname and 
	# IP address in order to configure themselves!

	if not interactive:
		cdata['hostname']  = system['name']
		cdata['fqdn']      = fqdn
		netaddr = g.redis.get('vm/' + system['vmware_uuid'].lower() + '/ipaddress')
		if netaddr == None:
			cdata['ipaddress'] = 'dhcp'
		else:
			cdata['ipaddress'] = netaddr

		# Mark as done
		g.redis.setex("vm/" + system['vmware_uuid'] + "/" + "notify", 28800, "inprogress")

	# Default to production env for puppet
	cdata['environment'] = 'production'
	cdata['certname']    = fqdn

	# Create puppet ENC entry if it does not already exist
	create_entry = False
	if 'puppet_certname' in system:
		if system['puppet_certname'] == None:
			create_entry = True
	else:
		create_entry = True

	if create_entry:
		## A system record exists but no puppet_nodes entry. We'll create one!
		## However what do we set the puppet environment to? We could default to production
		## but that sucks. So we'll see if the system is linked to ServiceNow and we'll
		## use that. If it isn't linked then we can't do much.

		if 'cmdb_environment' in system:
			## We'll use this instead on 'production'
			cmdb_envs = cortex.lib.core.get_cmdb_environments()
			for cmdbenv in cmdb_envs:
				if cmdbenv['name'] == system['cmdb_environment']:
					cdata['environment'] = cmdbenv['puppet']

		curd = g.db.cursor(mysql.cursors.DictCursor)
		curd.execute("INSERT INTO `puppet_nodes` (`id`, `certname`, `env`) VALUES (%s, %s, %s)", (system['id'], fqdn, cdata['environment']))
		g.db.commit()
		app.logger.info('Created Puppet ENC entry for certname "' + fqdn + '"')
	else:
		if 'puppet_env' in system:
			if system['puppet_env'] != None:
				cdata['environment'] = system['puppet_env']

	# Get the satellite registration key (if any)
	if 'ident' in request.form:
		ident = request.form['ident']

		if ident in app.config['SATELLITE_KEYS']:
			data = app.config['SATELLITE_KEYS'][ident]
			if cdata['environment'] in data:
				cdata['satellite_activation_key'] = data[cdata['environment']]

	return(jsonify(cdata))

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
		g.redis.setex("vm/" + system['vmware_uuid'].lower() + "/" + "notify", 28800, "done")

		return "OK"
	else:
		app.logger.warn('Missing \'uuid\' parameter in installer notify API')
		abort(401)
