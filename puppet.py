#!/usr/bin/python
#

from cortex import app
import cortex.core
from flask import Flask, request, session, redirect, url_for, flash, g, abort, make_response, render_template, jsonify
import os 
import time
import json
import re
import werkzeug
import MySQLdb as mysql
import yaml

################################################################################

@app.route('/puppet/enc/<int:id>', methods=['GET', 'POST'])
@cortex.core.login_required
def puppet_enc_edit(id):
	# Get the system out of the database
	system       = cortex.core.get_system_by_id(id)
	environments = cortex.core.get_puppet_environments()
	env_dict     = cortex.core.get_environments_as_dict()

	if system == None:
		abort(404)

	# If we've got a new node, then don't show "None"
	if system['puppet_classes'] is None or system['puppet_classes'] == '':
		system['puppet_classes'] = "# Global variables to include can be entered here\n"
	if system['puppet_variables'] is None or system['puppet_variables'] == '':
		system['puppet_variables'] = "# Classes to include can be entered here\n"
	if system['puppet_certname'] is None:
		system['puppet_certname'] = ""

	# On any GET request, just display the information
	if request.method == 'GET':
		return render_template('puppet-enc.html', system=system, active='puppet', environments=environments)

	# On any POST request, validate the input and then save
	elif request.method == 'POST':
		# Extract data from form
		certname = request.form.get('certname', '')
		environment = request.form.get('environment', '')
		classes = request.form.get('classes', '')
		variables = request.form.get('variables', '')
		if 'include_default' in request.form:
			include_default = True
		else:
			include_default = False
		error = False

		# Validate certificate name
		if len(certname.strip()) == 0:
			flash('Invalid certificate name', 'alert-danger')
			error = True

		# Validate environement:
		if environment not in [e['id'] for e in environments]:
			flash('Invalid environment', 'alert-danger')
			error = True

		# Validate classes YAML
		try:
			yaml.load(classes)
		except Exception, e:
			flash('Invalid YAML syntax for classes: ' + str(e), 'alert-danger')
			error = True

		# Validate variables YAML
		try:
			yaml.load(variables)
		except Exception, e:
			flash('Invalid YAML syntax for variables: ' + str(e), 'alert-danger')
			error = True

		# On error, overwrite what is in the system object with our form variables
		# and return the page back to the user for fixing
		if error:
			system['puppet_certname'] = certname
			system['puppet_env'] = environment
			system['puppet_classes'] = classes
			system['puppet_variables'] = variables
			system['puppet_include_default'] = include_default
			return render_template('puppet-enc.html', system=system, active='puppet', environments=environments)

		# Get a cursor to the database
		cur = g.db.cursor(mysql.cursors.DictCursor)

		# Update the system
		cur.execute('UPDATE `puppet_nodes` SET `certname` = %s, `env` = %s, `classes` = %s, `variables` = %s, `include_default` = %s WHERE `id` = %s', (certname, env_dict[environment]['puppet'], classes, variables, include_default, id))
		g.db.commit()

		# Redirect back to the systems page
		flash('Puppet ENC for host ' + system['name'] + ' updated', 'alert-success')

		return redirect(url_for('puppet_enc_edit',id=id))

################################################################################

@app.route('/puppet/default', methods=['GET', 'POST'])
@cortex.core.login_required
def puppet_enc_default():
	## Get the default YAML out of the kv table
	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute("SELECT `value` FROM `kv_settings` WHERE `key` = 'puppet.enc.default'")
	result = curd.fetchone()
	if result == None:
		classes = "# Classes to include on all nodes using the default settings can be entered here\n"
	else:
		classes = result['value']

	# On any GET request, just display the information
	if request.method == 'GET':
		return render_template('puppet-default.html', classes=classes, active='puppet')

	# On any POST request, validate the input and then save
	elif request.method == 'POST':
		# Extract data from form
		classes = request.form.get('classes', '')

		# Validate classes YAML
		try:
			yaml.load(classes)
		except Exception, e:
			flash('Invalid YAML syntax: ' + str(e), 'alert-danger')
			return render_template('puppet-default.html', classes=classes, active='puppet')

		# Get a cursor to the database
		# Update the system
		curd.execute('REPLACE INTO `kv_settings` (`key`,`value`) VALUES ("puppet.enc.default",%s)', (classes,))
		g.db.commit()

		# Redirect back
		flash('Puppet default settings updated', 'alert-success')

		return redirect(url_for('puppet_enc_default'))

################################################################################

@app.route('/puppet/nodes')
@cortex.core.login_required
def puppet_nodes():
	# Get a cursor to the databaseo
	curd = g.db.cursor(mysql.cursors.DictCursor)

	# Get OS statistics
	curd.execute('SELECT `puppet_nodes`.`certname` AS `certname`, `puppet_nodes`.`env` AS `env`, `systems`.`id` AS `id`, `systems`.`name` AS `name`  FROM `puppet_nodes` LEFT JOIN `systems` ON `puppet_nodes`.`id` = `systems`.`id` ORDER BY `puppet_nodes`.`certname` ')
	results = curd.fetchall()

	return render_template('puppet-nodes.html', active='puppet', data=results)

################################################################################

@app.route('/puppet/groups', methods=['GET', 'POST'])
@cortex.core.login_required
def puppet_groups():
	# Get a cursor to the databaseo
	curd = g.db.cursor(mysql.cursors.DictCursor)

	if request.method == 'GET':
		# Get OS statistics
		curd.execute('SELECT * FROM `puppet_groups`')
		results = curd.fetchall()

		return render_template('puppet-groups.html', active='puppet', data=results)
	else:
		if request.form['action'] == 'add':
			netgroup_name = request.form['netgroup_name']

			if len(netgroup_name.strip()) == 0:
				flash('Invalid netgroup name', 'alert-danger')
				return redirect(url_for('puppet_groups'))

			## Make sure that group hasnt already been imported
			curd.execute('SELECT 1 FROM `puppet_groups` WHERE `name` = %s', netgroup_name)
			found = curd.fetchone()
			if found:
				flash('That netgroup has already been imported as a Puppet Group', 'alert-warning')
				return redirect(url_for('puppet_groups'))			

			if not cortex.core.netgroup_is_valid(netgroup_name):
				flash('That netgroup does not exist', 'alert-danger')
				return redirect(url_for('puppet_groups'))

			curd.execute('INSERT INTO `puppet_groups` (`name`) VALUES (%s)', (netgroup_name))
			g.db.commit()

			flash('The netgroup "' + netgroup_name + '" has imported as a Puppet Group', 'alert-success')
			return redirect(url_for('puppet_groups'))
		elif request.form['action'] == 'delete':
			group_name = request.form['group']

			try:
				curd.execute('DELETE FROM `puppet_groups` WHERE `name` = %s', group_name)
				g.db.commit()
				flash('Deleted Puppet group "' + group_name + '"', 'alert-success')
			except Exception, e:
				flash('Failed to delete Puppet group', 'alert-danger')

			return redirect(url_for('puppet_groups'))

################################################################################

@app.route('/puppet/group/<name>', methods=['GET', 'POST'])
@cortex.core.login_required
def puppet_group_edit(name):
	# Get a cursor to the databaseo
	curd = g.db.cursor(mysql.cursors.DictCursor)

	## Get the group from the DB
	curd.execute('SELECT * FROM `puppet_groups` WHERE `name` = %s', name)
	group = curd.fetchone()
	if not group:
		flash('I could not find a Puppet Group with that name', 'alert-warning')
		return redirect(url_for('puppet_groups'))

	if group['classes'] is None:
		group['classes'] = "# Classes to include can be entered here\n"

	# On any GET request, just display the information
	if request.method == 'GET':
		return render_template('puppet-group.html', group=group, active='puppet')

	# On any POST request, validate the input and then save
	elif request.method == 'POST':
		# Extract data from form
		classes = request.form.get('classes', '')

		# Validate classes YAML
		try:
			yaml.load(classes)
		except Exception, e:
			flash('Invalid YAML syntax for classes: ' + str(e), 'alert-danger')
			return render_template('puppet-group.html', group=group, classes=classes, active='puppet')

		# Update the system
		curd.execute('UPDATE `puppet_groups` SET `classes` = %s WHERE `name` = %s', (classes,name))
		g.db.commit()

		# Redirect back to the systems page
		flash('Changes saved successfully', 'alert-success')
		return redirect(url_for('puppet_group_edit',name=name))

################################################################################

@app.route('/puppet/yaml/<int:id>', methods=['GET', 'POST'])
@cortex.core.login_required
def puppet_node_yaml(id):
	system = cortex.core.get_system_by_id(id)

	if system == None:
		abort(404)

	curd = g.db.cursor(mysql.cursors.DictCursor)

	## Get the group from the DB
	curd.execute('SELECT * FROM `puppet_nodes` WHERE `id` = %s', system['id'])
	node = curd.fetchone()

	if node == None:
		abort(404)

	return render_template('puppet-node-yaml.html', raw=puppet_generate_config(node['certname']), system=system, node=node, active='puppet')

################################################################################

def puppet_generate_config(certname):
	"""Generates a YAML document describing the configuration of a particular
	node given as 'certname'."""

	# Get a cursor to the databaseo
	curd = g.db.cursor(mysql.cursors.DictCursor)

	# Get the task
	curd.execute("SELECT `id`, `classes`, `variables`, `env`, `include_default` FROM `puppet_nodes` WHERE `certname` = %s", (certname,))
	node = curd.fetchone()

	# If we don't find the node, return nothing
	if node is None:
		return None

	# Get the system
	system = cortex.core.get_system_by_id(node['id'])

	curd.execute("SELECT `value` FROM `kv_settings` WHERE `key` = 'puppet.enc.default'")
	default_classes = curd.fetchone()
	if default_classes is not None:
		default_classes = yaml.load(default_classes['value'])
	
		## yaml load can come back with no actual objects, e.g. comments, blank etc.
		if default_classes == None:
			default_classes = {}
	else:
		default_classes = {}

	# Start building response
	response = {'environment': node['env']}

	# Decode YAML for classes from the node
	if len(node['classes'].strip()) != 0:
		node_classes = yaml.load(node['classes'])

		## yaml load can come back with no actual objects, e.g. comments, blank etc.
		if node_classes == None:
			response['classes'] = {}
		else:
			response['classes'] = node_classes
	else:
		response['classes'] = {}

	# Find all netgroups this node is a member of to load in their classes too
	curd.execute("SELECT `name`, `classes` FROM `puppet_groups` ORDER BY `name`")
	groups = curd.fetchall()

	for group in groups:
		if group['classes'] == None:
			continue

		if cortex.core.host_in_netgroup(certname,group['name']):

			# Convert from YAML to python types for the classes for this group
			group_classes = yaml.load(group['classes'])

			## If there are classes within that
			if not group_classes == None:
				## Get the name of each class
				for classname in group_classes:
					# And if the class hasn't already been loaded by the node...
					if not classname in response['classes']:
						# import this class and its params too
						response['classes'][classname] = group_classes[classname]

	if node['include_default']:
		# Load in global default classes too, unless we already loaded settings for those class names
		for classname in default_classes:
			if not classname in response['classes']:
				response['classes'][classname] = default_classes[classname]

	# Decode YAML for environment (Puppet calls them parameters, but we call them [global] variables)
	variables = None
	if len(node['variables'].strip()) != 0:
		params = yaml.load(node['variables'])

		if not params == None:
			response['parameters'] = params
		else:
			response['parameters'] = {}
	else:
		response['parameters'] = {}

	# Add in (and indeed potentially overwrite) some auto-generated variables
	if 'cmdb_id' not in system or system['cmdb_id'] is None or len(system['cmdb_id'].strip()) == 0:
		# Not linked to a ServiceNow entry, put in some defaults
		response['parameters']['uos_motd_sn_environment'] = 'ERROR: Not linked to ServiceNow. Visit: ' + url_for('systems_edit', _external=True, id=system['id'])
		response['parameters']['uos_motd_sn_description'] = 'ERROR: Not linked to ServiceNow. Visit: ' + url_for('systems_edit', _external=True, id=system['id'])
	else:
		response['parameters']['uos_motd_sn_environment'] = system['cmdb_environment']
		if system['cmdb_description'] is None or len(system['cmdb_description'].strip()) == 0:
			response['parameters']['uos_motd_sn_description'] = 'ERROR: Description not set in ServiceNow. Visit: ' + (app.config['CMDB_URL_FORMAT'] % system['cmdb_id'])
		else:
			response['parameters']['uos_motd_sn_description'] = system['cmdb_description']

	return yaml.dump(response)
