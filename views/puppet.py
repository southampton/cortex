#!/usr/bin/python

from cortex import app
import cortex.lib.puppet
import cortex.lib.core
import cortex.lib.systems
from cortex.lib.user import does_user_have_permission, does_user_have_system_permission
from cortex.lib.errors import stderr
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

@app.route('/help/puppet')
@cortex.lib.user.login_required
def puppet_help():
	"""Displays the Puppet ENC help page."""

	return render_template('puppet/help.html', active='puppet', title="Puppet Help")

################################################################################

@app.route('/puppet/enc/<node>', methods=['GET', 'POST'])
@cortex.lib.user.login_required
def puppet_enc_edit(node):
	"""Handles the manage Puppet node page"""

	# Get the system out of the database
	system       = cortex.lib.systems.get_system_by_puppet_certname(node)
	environments = cortex.lib.core.get_puppet_environments()
	env_dict     = cortex.lib.core.get_environments_as_dict()

	if system == None:
		abort(404)

	
	
	# On any GET request, just display the information
	if request.method == 'GET':
		
		# If the user has view or edit permission send them the template - otherwise abort with 403.
		if does_user_have_system_permission(system['id'],"view.puppet.classify","systems.all.view.puppet.classify") or \
			does_user_have_system_permission(system['id'],"edit.puppet","systems.all.edit.puppet"):

			return render_template('puppet/enc.html', system=system, active='puppet', environments=environments, title=system['name'], nodename=node, pactive="edit", yaml=cortex.lib.puppet.generate_node_config(system['puppet_certname']))
		else:
			abort(403)

	# If the method is POST and the user has edit permission.
	# Validate the input and then save.
	elif request.method == 'POST' and does_user_have_system_permission(system['id'],"edit.puppet","systems.all.edit.puppet"):

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
			data = yaml.safe_load(classes)
		except Exception as e:
			flash('Invalid YAML syntax for classes: ' + str(e), 'alert-danger')
			error = True

		try:
			if not data is None:
				assert isinstance(data, dict)
		except Exception as e:
			flash('Invalid YAML syntax for classes: result was not a list of classes, did you forget a trailing colon? ' + str(e), 'alert-danger')
			error = True

		# Validate variables YAML
		try:
			data = yaml.safe_load(variables)
		except Exception as e:
			flash('Invalid YAML syntax for variables: ' + str(e), 'alert-danger')
			error = True

		try:
			if not data is None:
				assert isinstance(data, dict)
		except Exception as e:
			flash('Invalid YAML syntax for variables: result was not a list of variables, did you forget a trailing colon? ' + str(e), 'alert-danger')
			error = True


		# On error, overwrite what is in the system object with our form variables
		# and return the page back to the user for fixing
		if error:
			system['puppet_env'] = environment
			system['puppet_classes'] = classes
			system['puppet_variables'] = variables
			system['puppet_include_default'] = include_default
			return render_template('puppet/enc.html', system=system, active='puppet', environments=environments, title=system['name'])

		# Get a cursor to the database
		curd = g.db.cursor(mysql.cursors.DictCursor)

		# Update the system
		curd.execute('UPDATE `puppet_nodes` SET `env` = %s, `classes` = %s, `variables` = %s, `include_default` = %s WHERE `certname` = %s', (env_dict[environment]['puppet'], classes, variables, include_default, system['puppet_certname']))
		g.db.commit()
		cortex.lib.core.log(__name__, "puppet.config.changed", "Puppet node configuration updated for '" + system['puppet_certname'] + "'")

		# Redirect back to the systems page
		flash('Puppet ENC for host ' + system['name'] + ' updated', 'alert-success')

		return redirect(url_for('puppet_enc_edit', node=node))

	else:
		abort(403)

################################################################################

@app.route('/puppet/default', methods=['GET', 'POST'])
@cortex.lib.user.login_required
def puppet_enc_default():
	"""Handles the Puppet ENC Default Classes page"""

	# Check user permissions
	if not does_user_have_permission("puppet.default_classes.view"):
		abort(403)

	# Get the default YAML out of the kv table
	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute("SELECT `value` FROM `kv_settings` WHERE `key` = 'puppet.enc.default'")
	result = curd.fetchone()
	if result == None:
		classes = "# Classes to include on all nodes using the default settings can be entered here\n"
	else:
		classes = result['value']

	# On any GET request, just display the information
	if request.method == 'GET':
		return render_template('puppet/default.html', classes=classes, active='puppet', title="Default Classes")

	# On any POST request, validate the input and then save
	elif request.method == 'POST':
		# Check user permissions
		if not does_user_have_permission("puppet.default_classes.edit"):
			abort(403)

		# Extract data from form
		classes = request.form.get('classes', '')

		# Validate classes YAML
		try:
			data = yaml.safe_load(classes)
		except Exception as e:
			flash('Invalid YAML syntax: ' + str(e), 'alert-danger')
			return render_template('puppet/default.html', classes=classes, active='puppet', title="Default Classes")

		try:
			if not data is None:
				assert isinstance(data, dict)
		except Exception as e:
			flash('Invalid YAML syntax: result was not a list of classes, did you forget a trailing colon? ' + str(e), 'alert-danger')
			return render_template('puppet/default.html', classes=classes, active='puppet', title="Default Classes")

		# Get a cursor to the database
		# Update the system
		curd.execute('REPLACE INTO `kv_settings` (`key`, `value`) VALUES ("puppet.enc.default", %s)', (classes,))
		g.db.commit()

		cortex.lib.core.log(__name__, "puppet.defaultconfig.changed", "Puppet default configuration updated")
		# Redirect back
		flash('Puppet default settings updated', 'alert-success')

		return redirect(url_for('puppet_enc_default'))

################################################################################

@app.route('/puppet/nodes')
@app.route('/puppet/nodes/status/<string:status>')
@cortex.lib.user.login_required
def puppet_nodes(status = None):
	"""Handles the Puppet nodes list page"""

	# Check user permissions
	if not does_user_have_permission("puppet.nodes.view"):
		abort(403)

	# Get a cursor to the database
	curd = g.db.cursor(mysql.cursors.DictCursor)

	# Get Puppet nodes from the database
	curd.execute('SELECT `puppet_nodes`.`certname` AS `certname`, `puppet_nodes`.`env` AS `env`, `systems`.`id` AS `id`, `systems`.`name` AS `name`, `systems`.`allocation_comment` AS `allocation_comment` FROM `puppet_nodes` LEFT JOIN `systems` ON `puppet_nodes`.`id` = `systems`.`id` ORDER BY `puppet_nodes`.`certname` ')
	results = curd.fetchall()

	# Get node statuses
	try:
		statuses = cortex.lib.puppet.puppetdb_get_node_statuses()
	except Exception as e:
		return stderr("Unable to connect to PuppetDB","Unable to connect to the Puppet database. The error was: " + type(e).__name__ + " - " + str(e))

	
	data = []
	for row in results:
		if row['certname'] in statuses:
			row['status'] = statuses[row['certname']]['status']
			row['clientnoop'] = statuses[row['certname']]['clientnoop']
		else:
			row['status'] = 'unknown'
			row['clientnoop'] = 'unknown'

		if status == None or status == 'all':
			data.append(row)
		elif status == 'unchanged' and row['status'] == 'unchanged':
			data.append(row)
		elif status == 'changed' and row['status'] == 'changed':
			data.append(row)
		elif status == 'noop' and row['status'] == 'noop':
			data.append(row)
		elif status == 'failed' and row['status'] == 'failed':
			data.append(row)
		elif status == 'unknown' and row['status'] not in ['unchanged', 'changed', 'noop', 'failed']:
			data.append(row)

	# Page Title Map
	title = 'Puppet Nodes'
	page_title_map = {'unchanged': 'Normal', 'changed': 'Changed', 'noop': 'Disabled', 'failed': 'Failed', 'unknown': 'Unknown/Unreported', 'all': 'Registered'}

	if status != None and status in page_title_map:
		title = title + ' - {}'.format(page_title_map.get(status)) 

	# Render
	return render_template('puppet/nodes.html', active='puppet', data=data, title=title, hide_unknown=True)

################################################################################

@app.route('/puppet/facts/<node>')
@cortex.lib.user.login_required
def puppet_facts(node):
	"""Handle the Puppet node facts page"""

	# Get the system (we need to know the ID for permissions checking)
	system = cortex.lib.systems.get_system_by_puppet_certname(node)
	if system is None:
		abort(404)

	## Check if the user is allowed to view the facts about this node
	if not does_user_have_system_permission(system['id'],"view.puppet","systems.all.view.puppet"):
		abort(403)

	dbnode = None
	facts = None
	try:
		# Connect to PuppetDB, get the node information and then it's related facts
		db     = cortex.lib.puppet.puppetdb_connect()
		dbnode = db.node(node)
		facts  = dbnode.facts()
	except HTTPError as he:
		# If we get a 404 from the PuppetDB API
		if he.response.status_code == 404:
			# We will continue to render the page, just with no facts and display a nice error
			facts = None
		else:
			raise(he)
	except Exception as e:
		return stderr("Unable to connect to PuppetDB","Unable to connect to the Puppet database. The error was: " + type(e).__name__ + " - " + str(e))

	# Turn the facts generator in to a dictionary
	facts_dict = {}

	if facts != None:
		for fact in facts:
			facts_dict[fact.name] = fact.value

	# Render
	return render_template('puppet/facts.html', facts=facts_dict, node=dbnode, active='puppet', title=node + " - Puppet Facts", nodename=node, pactive="facts", system=system)

################################################################################

@app.route('/puppet/dashboard')
@cortex.lib.user.login_required
def puppet_dashboard():
	"""Handles the Puppet dashboard page."""

	# Check user permissions
	if not does_user_have_permission("puppet.dashboard.view"):
		abort(403)

	try:
		stats=cortex.lib.puppet.puppetdb_get_node_stats()
	except Exception as e:
		return stderr("Unable to connect to PuppetDB","Unable to connect to the Puppet database. The error was: " + type(e).__name__ + " - " + str(e))

	return render_template('puppet/dashboard.html', stats=stats,active='puppet', title="Puppet Dashboard", environments=cortex.lib.core.get_puppet_environments())

################################################################################

@app.route('/puppet/radiator')
def puppet_radiator():
	"""Handles the Puppet radiator view page. Similar to the dashboard."""

	## No permissions check: this is accessible without logging in
	try:
		stats=cortex.lib.puppet.puppetdb_get_node_stats()
		
	except Exception as e:
		return stderr("Unable to connect to PuppetDB","Unable to connect to the Puppet database. The error was: " + type(e).__name__ + " - " + str(e))

	# create dictionary to hold the values the radiator needs
	top_level_stats = {}
	for s in stats:
		#'count' value in the dictionary is the value we need
		top_level_stats[s] = stats[s]['count']

	return render_template('puppet/radiator.html', stats=top_level_stats, active='puppet')

################################################################################

@app.route('/puppet/radiator/body')
def puppet_radiator_body():
	"""Handles the body of the Puppet radiator view. JavaScript on the page
	calls this function to update the content using AJAX rather than a
	iffy page refresh."""

	## No permissions check: this is accessible without logging in
	stats=cortex.lib.puppet.puppetdb_get_node_stats()
	# create dictionary to hold the values the radiator needs
	top_level_stats = {}
	for s in stats:
		#'count' value in the dictionary is the value we need
		top_level_stats[s] = stats[s]['count']

	return render_template('puppet/radiator-body.html', stats=top_level_stats, active='puppet')

################################################################################

@app.route('/puppet/reports/<node>')
@cortex.lib.user.login_required
def puppet_reports(node):
	"""Handles the Puppet reports page for a node"""

	# Get the system (we need to know the ID for permissions checking)
	system = cortex.lib.systems.get_system_by_puppet_certname(node)
	if system is None:
		abort(404)

	## Check if the user is allowed to view the reports of this node
	if not does_user_have_system_permission(system['id'],"view.puppet","systems.all.view.puppet"):
		abort(403)

	try:
		# Connect to PuppetDB and get the reports
		db = cortex.lib.puppet.puppetdb_connect()
		reports = db.node(node).reports()
		
	except HTTPError as he:
		# If we get a 404 response from PuppetDB
		if he.response.status_code == 404:
			# Still display the page but with a nice error
			reports = None
		else:
			raise(he)
	except Exception as e:
		return stderr("Unable to connect to PuppetDB","Unable to connect to the Puppet database. The error was: " + type(e).__name__ + " - " + str(e))

	return render_template('puppet/reports.html', reports=reports, active='puppet', title=node + " - Puppet Reports", nodename=node, pactive="reports", system=system)

################################################################################

@app.route('/puppet/report/<report_hash>')
@cortex.lib.user.login_required
def puppet_report(report_hash):
	"""Displays an individual report for a Puppet node"""

	# Connect to Puppet DB and query for a report with the given hash
	try:
		db = cortex.lib.puppet.puppetdb_connect()
	except Exception as e:
		return stderr("Unable to connect to PuppetDB","Unable to connect to the Puppet database. The error was: " + type(e).__name__ + " - " + str(e))

	reports = db.reports(query='["=", "hash", "' + report_hash + '"]')

	# 'reports' is a generator. Get the next (first and indeed, only item) from the generator
	try:
		report = next(reports)
	except StopIteration as e:
		# If we get a StopIteration error, then we've not got any data
		# returned from the reports generator, so the report didn't
		# exist, hence we should 404
		return abort(404)

	# Get the system (we need the ID for perms check, amongst other things)
	system = cortex.lib.systems.get_system_by_puppet_certname(report.node)
	if system is None:
		return abort(404)

	## Check if the user is allowed to view the report
	if not does_user_have_system_permission(system['id'],"view.puppet","systems.all.view.puppet"):
		abort(403)

	# Build metrics into a more useful dictionary
	metrics = {}
	for metric in report.metrics:
		if metric['category'] not in metrics:
			metrics[metric['category']] = {}

		metrics[metric['category']][metric['name']] = metric['value']

	# Render
	return render_template('puppet/report.html', report=report, metrics=metrics, system=system, active='puppet', title=report.node + " - Puppet Report")

##############################################################################

@app.route('/puppet/search')
@cortex.lib.user.login_required
def puppet_search():
	"""Provides search functionality for puppet classes and environment
	variables"""

	# Check user permissions
	if not does_user_have_permission("puppet.nodes.view"):
		abort(403)

	q = request.args.get('q')
	if q is None:
		app.logger.warn('Missing \'query\' parameter in puppet search request')
		return abort(400)

	q.strip();
	# escape wildcards
	q = q.replace('%', '\%').replace('_', '\_')

	#Search for the text
	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute('''SELECT DISTINCT `puppet_nodes`.`certname` AS `certname`, `puppet_nodes`.`env` AS `env`, `systems`.`id` AS `id`, `systems`.`name` AS `name`  FROM `puppet_nodes` LEFT JOIN `systems` ON `puppet_nodes`.`id` = `systems`.`id` WHERE `puppet_nodes`.`classes` LIKE %s OR `puppet_nodes`.`variables` LIKE %s ORDER BY `puppet_nodes`.`certname`''', ('%' + q + '%', '%' + q + '%'))
	results = curd.fetchall()

	return render_template('puppet/search.html', active='puppet', data=results, title="Puppet search")

##############################################################################

@app.route('/puppet/catalog/<node>')
@cortex.lib.user.login_required
def puppet_catalog(node):
	"""Show the Puppet catalog for a given node."""

	# Get the system
	system = cortex.lib.systems.get_system_by_puppet_certname(node)
	
	if system == None:
		abort(404)

	## Check if the user is allowed to edit the Puppet configuration
	if not does_user_have_system_permission(system['id'],"view.puppet.catalog","systems.all.view.puppet.catalog"):
		abort(403)

	dbnode = None
	catalog = None
	try:
		# Connect to PuppetDB, get the node information and then it's catalog.
		db = cortex.lib.puppet.puppetdb_connect()
		dbnode = db.node(node)
		catalog = db.catalog(node)
	except HTTPError as he:
		# If we get a 404 from the PuppetDB API
		if he.response.status_code == 404:
			catalog = None
		else:
			raise(he)
	except Exception as e:
		return stderr("Unable to connect to PuppetDB","Unable to connect to the Puppet database. The error was: " + type(e).__name__ + " - " + str(e))

	catalog_dict = {}
	
	if catalog != None:
		for res in catalog.get_resources():
			catalog_dict[str(res)] = res.parameters
			
	# Render
	return render_template('puppet/catalog.html', catalog=catalog_dict, node=dbnode, active='puppet', title=node + " - Puppet Catalog", nodename=node, pactive="catalog", system=system)	
