#!/usr/bin/python

from cortex import app
import cortex.lib.puppet
import cortex.lib.core
import cortex.lib.systems
from flask import Flask, request, session, redirect, url_for, flash, g, abort, make_response, render_template, jsonify
import os 
import time
import json
import re
import werkzeug
import MySQLdb as mysql
import yaml
import pypuppetdb
from requests.exceptions import HTTPError

################################################################################

@app.route('/help/puppet', methods=['GET', 'POST'])
@cortex.lib.user.login_required
def puppet_help():
	return render_template('puppet-help.html', active='help', title="Puppet Help")

################################################################################

@app.route('/puppet/enc/<node>', methods=['GET', 'POST'])
@cortex.lib.user.login_required
def puppet_enc_edit(node):
	# Get the system out of the database
	system       = cortex.lib.systems.get_system_by_puppet_certname(node)
	environments = cortex.lib.core.get_puppet_environments()
	env_dict     = cortex.lib.core.get_environments_as_dict()

	if system == None:
		abort(404)

	# If we've got a new node, then don't show "None"
	if system['puppet_classes'] is None or system['puppet_classes'] == '':
		system['puppet_classes'] = "# Classes to include can be entered here\n"
	if system['puppet_variables'] is None or system['puppet_variables'] == '':
		system['puppet_variables'] = "# Global variables to include can be entered here\n"
	if system['puppet_certname'] is None:
		system['puppet_certname'] = ""

	# On any GET request, just display the information
	if request.method == 'GET':
		return render_template('puppet-enc.html', system=system, active='puppet', environments=environments, title=system['name'],nodename=node,pactive="edit")

	# On any POST request, validate the input and then save
	elif request.method == 'POST':
		# Extract data from form
		environment = request.form.get('environment', '')
		classes = request.form.get('classes', '')
		variables = request.form.get('variables', '')
		if 'include_default' in request.form:
			include_default = True
		else:
			include_default = False
		error = False

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
			system['puppet_env'] = environment
			system['puppet_classes'] = classes
			system['puppet_variables'] = variables
			system['puppet_include_default'] = include_default
			return render_template('puppet-enc.html', system=system, active='puppet', environments=environments, title=system.name)

		# Get a cursor to the database
		cur = g.db.cursor(mysql.cursors.DictCursor)

		# Update the system
		cur.execute('UPDATE `puppet_nodes` SET `env` = %s, `classes` = %s, `variables` = %s, `include_default` = %s WHERE `certname` = %s', (env_dict[environment]['puppet'], classes, variables, include_default, system['puppet_certname']))
		g.db.commit()

		# Redirect back to the systems page
		flash('Puppet ENC for host ' + system['name'] + ' updated', 'alert-success')

		return redirect(url_for('puppet_enc_edit',node=node))

################################################################################

@app.route('/puppet/default', methods=['GET', 'POST'])
@cortex.lib.user.login_required
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
		return render_template('puppet-default.html', classes=classes, active='puppet', title="Default Classes")

	# On any POST request, validate the input and then save
	elif request.method == 'POST':
		# Extract data from form
		classes = request.form.get('classes', '')

		# Validate classes YAML
		try:
			yaml.load(classes)
		except Exception, e:
			flash('Invalid YAML syntax: ' + str(e), 'alert-danger')
			return render_template('puppet-default.html', classes=classes, active='puppet', title="Default Classes")

		# Get a cursor to the database
		# Update the system
		curd.execute('REPLACE INTO `kv_settings` (`key`,`value`) VALUES ("puppet.enc.default",%s)', (classes,))
		g.db.commit()

		# Redirect back
		flash('Puppet default settings updated', 'alert-success')

		return redirect(url_for('puppet_enc_default'))

################################################################################

@app.route('/puppet/nodes')
@cortex.lib.user.login_required
def puppet_nodes():
	# Get a cursor to the database
	curd = g.db.cursor(mysql.cursors.DictCursor)

	# Get OS statistics
	curd.execute('SELECT `puppet_nodes`.`certname` AS `certname`, `puppet_nodes`.`env` AS `env`, `systems`.`id` AS `id`, `systems`.`name` AS `name`  FROM `puppet_nodes` LEFT JOIN `systems` ON `puppet_nodes`.`id` = `systems`.`id` ORDER BY `puppet_nodes`.`certname` ')
	results = curd.fetchall()

	return render_template('puppet-nodes.html', active='puppet', data=results, title="Puppet Nodes")

################################################################################

@app.route('/puppet/groups', methods=['GET', 'POST'])
@cortex.lib.user.login_required
def puppet_groups():
	# Get a cursor to the databaseo
	curd = g.db.cursor(mysql.cursors.DictCursor)

	if request.method == 'GET':
		# Get OS statistics
		curd.execute('SELECT * FROM `puppet_groups`')
		results = curd.fetchall()

		return render_template('puppet-groups.html', active='puppet', data=results, title="Puppet Groups")
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

			if not cortex.lib.netgroup.exists(netgroup_name):
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
@cortex.lib.user.login_required
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
		return render_template('puppet-group.html', group=group, active='puppet', title=group['name'])

	# On any POST request, validate the input and then save
	elif request.method == 'POST':
		# Extract data from form
		classes = request.form.get('classes', '')

		# Validate classes YAML
		try:
			yaml.load(classes)
		except Exception, e:
			flash('Invalid YAML syntax for classes: ' + str(e), 'alert-danger')
			return render_template('puppet-group.html', group=group, classes=classes, active='puppet', title=group['name'])

		# Update the system
		curd.execute('UPDATE `puppet_groups` SET `classes` = %s WHERE `name` = %s', (classes,name))
		g.db.commit()

		# Redirect back to the systems page
		flash('Changes saved successfully', 'alert-success')
		return redirect(url_for('puppet_group_edit',name=name))

################################################################################

@app.route('/puppet/yaml/<node>', methods=['GET', 'POST'])
@cortex.lib.user.login_required
def puppet_node_yaml(node):
	system = cortex.lib.systems.get_system_by_puppet_certname(node)

	if system == None:
		abort(404)

	curd = g.db.cursor(mysql.cursors.DictCursor)

	## Get the group from the DB
	curd.execute('SELECT * FROM `puppet_nodes` WHERE `id` = %s', system['id'])
	node = curd.fetchone()

	if node == None:
		abort(404)

	return render_template('puppet-node-yaml.html', raw=cortex.lib.puppet.generate_node_config(node['certname']), system=system, node=node, active='puppet', title="Puppet Configuration",nodename=node['certname'],pactive="view")

################################################################################

@app.route('/puppet/facts/<node>')
@cortex.lib.user.login_required
def puppet_facts(node):
	dbnode = None
	facts = None
	try:
		db     = cortex.lib.puppet.puppetdb_connect()
		dbnode = db.node(node)
		facts  = db.node(dbnode).facts()
	except HTTPError, he:
		if he.response.status_code == 404:
			facts = None
		else:
			raise(he)
	except Exception, e:
		raise(e)

	return render_template('puppet-facts.html', facts=facts, node=dbnode, active='puppet', title=node + " - Puppet Facts",nodename=node,pactive="facts")

################################################################################

@app.route('/puppet/dashboard')
@cortex.lib.user.login_required
def puppet_dashboard():
	return render_template('puppet-dashboard.html', stats=cortex.lib.puppet.puppetdb_get_node_stats(), active='puppet', title="Puppet Dashboard")

################################################################################

@app.route('/puppet/dashboard/status/<status>')
@cortex.lib.user.login_required
def puppet_dashboard_status(status):
	# Page Titles to use
	page_title_map = {'unchanged': 'Normal', 'changed': 'Changed', 'noop': 'Disabled (No-op)', 'failed': 'Failed', 'unknown': 'Unknown'}

	# If we have an invalid status, return 404
	if status not in page_title_map:
		abort(404)

	# Connect to PuppetDB
	db = cortex.lib.puppet.puppetdb_connect()

	# Get information about all the nodes, including their status
	nodes = db.nodes(with_status = True)

	# Create a filterd array
	nodes_of_type = []

	# Iterate over nodes and do the filtering
	for node in nodes:
		# If the status matches...
		if node.status == status:
			nodes_of_type.append(node)
		# Or if the required status is 'unknown' and it's not one of the normal statii
		elif status == 'unknown' and node.status not in ['unchanged', 'changed', 'noop', 'failed']:
			nodes_of_type.append(node)

	return render_template('puppet-dashboard-status.html', active='puppet', title="Puppet Dashboard", nodes=nodes_of_type, status=page_title_map[status])

################################################################################

@app.route('/puppet/radiator')
def puppet_radiator():
	return render_template('puppet-radiator.html', stats=cortex.lib.puppet.puppetdb_get_node_stats(), active='puppet')

################################################################################

@app.route('/puppet/radiator/body')
def puppet_radiator_body():
	return render_template('puppet-radiator-body.html', stats=cortex.lib.puppet.puppetdb_get_node_stats(), active='puppet')

################################################################################

@app.route('/puppet/reports/<node>')
@cortex.lib.user.login_required
def puppet_reports(node):
	try:
		db = cortex.lib.puppet.puppetdb_connect()
		reports = db.node(node).reports()
	except HTTPError, he:
		if he.response.status_code == 404:
			reports = None
		else:
			raise(he)
	except Exception, e:
		raise(e)

	return render_template('puppet-reports.html', reports=reports, active='puppet', title=node + " - Puppet Reports", nodename=node, pactive="reports")

################################################################################

@app.route('/puppet/report/<report_hash>')
@cortex.lib.user.login_required
def puppet_report(report_hash):
	db = cortex.lib.puppet.puppetdb_connect()
	reports = db.reports(query='["=", "hash", "' + report_hash + '"]')

	# 'reports' is a generator. Get the next (first and indeed, only item) from the generator
	try:
		report = next(reports)
	except StopIteration, e:
		# If we get a StopIteration error, then we've not got any data
		# returned from the reports generator, so the report didn't
		# exist, hence we should 404
		return abort(404)

	# Build metrics into a more useful dictionary
	metrics = {}
	for metric in report.metrics:
		if metric['category'] not in metrics:
			metrics[metric['category']] = {}

		metrics[metric['category']][metric['name']] = metric['value']

	# Render
	return render_template('puppet-report.html', report=report, metrics=metrics, active='puppet', title=report.node + " - Puppet Report")
