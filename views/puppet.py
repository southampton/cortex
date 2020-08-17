
import json

import MySQLdb as mysql
import yaml
from flask import (abort, flash, g, redirect,
                   render_template, request, session, url_for)
from requests.exceptions import HTTPError

import cortex.lib.core
import cortex.lib.puppet
import cortex.lib.systems
from cortex import app
from cortex.lib.errors import stderr
from cortex.lib.user import (does_user_have_any_puppet_permission,
                             does_user_have_permission,
                             does_user_have_puppet_permission,
                             does_user_have_system_permission)

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
	system = cortex.lib.systems.get_system_by_puppet_certname(node)
	if system is None:
		abort(404)

	# Get the environments from the DB where:
	#  - the user has classify permission or,
	#  - the environment is the 'default' environment or,
	#  - the environment is an 'infrastructure' environment.

	if does_user_have_permission("puppet.environments.all.classify"):
		environments = cortex.lib.puppet.get_puppet_environments()
	else:
		environments = cortex.lib.puppet.get_puppet_environments(
			environment_permission="classify",
			include_default=True,
			include_infrastructure_envs=True,
		)

	# Get the environment names as a list
	environment_names = [e['environment_name'] for e in environments]

	# Get the database cursor
	curd = g.db.cursor(mysql.cursors.DictCursor)
	# TODO: Query with an order so 'production' take precedence
	curd.execute("SELECT `puppet_modules`.`module_name` AS `module_name`, `puppet_classes`.`class_name` AS `class_name`, `puppet_documentation`.`name` AS `param`, `puppet_documentation`.`text` AS `param_desc` FROM `puppet_modules` LEFT JOIN `puppet_classes` ON `puppet_modules`.`id`=`puppet_classes`.`module_id` LEFT JOIN `puppet_documentation` ON `puppet_classes`.`id`=`puppet_documentation`.`class_id` WHERE `puppet_documentation`.`tag`=%s;", ("param", ))
	hints = {}
	for row in curd.fetchall():
		if row["module_name"] not in hints:
			hints[row["module_name"]] = {}
		if row["class_name"] not in hints[row["module_name"]]:
			hints[row["module_name"]][row["class_name"]] = {}
		if row["param"] not in hints[row["module_name"]][row["class_name"]]:
			hints[row["module_name"]][row["class_name"]][row["param"]] = row["param_desc"]

	# If the user has view or edit permission send them the template - otherwise abort with 403.
	if not does_user_have_system_permission(system['id'], "view.puppet.classify", "systems.all.view.puppet.classify") and not does_user_have_system_permission(system['id'], "edit.puppet", "systems.all.edit.puppet"):
		abort(403)

	# If the method is POST and the user has edit permission.
	# Validate the input and then save.
	if request.method == 'POST':
		if not does_user_have_system_permission(system['id'], "edit.puppet", "systems.all.edit.puppet"):
			abort(403)

		# Extract data from form
		environment = request.form.get('environment', '')
		classes = request.form.get('classes', '')
		variables = request.form.get('variables', '')
		include_default = bool('include_default' in request.form)
		error = False

		# Validate environement:
		if environment not in environment_names:
			flash('Invalid Puppet environment, you can only classify systems with Environments you have \'classify\' permission over!', 'alert-danger')
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
			return render_template('puppet/enc.html', system=system, active='puppet', environments=environments, title=system['name'], hints=hints)

		# Get a cursor to the database
		curd = g.db.cursor(mysql.cursors.DictCursor)

		# Update the system
		curd.execute('UPDATE `puppet_nodes` SET `env` = %s, `classes` = %s, `variables` = %s, `include_default` = %s WHERE `certname` = %s', (environment, classes, variables, include_default, system['puppet_certname']))
		g.db.commit()
		cortex.lib.core.log(__name__, "puppet.config.changed", "Puppet node configuration updated for '" + system['puppet_certname'] + "'")

		# Redirect back to the systems page
		flash('Puppet ENC for host ' + system['name'] + ' updated', 'alert-success')

		return redirect(url_for('puppet_enc_edit', node=node))

	# On any GET request, just display the information
	return render_template('puppet/enc.html', system=system, active='puppet', environments=environments, title=system['name'], nodename=node, pactive="edit", yaml=cortex.lib.puppet.generate_node_config(system['puppet_certname']), hints=hints, environment_names=environment_names)

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
	if result is None:
		classes = "# Classes to include on all nodes using the default settings can be entered here\n"
	else:
		classes = result['value']

	# On any POST request, validate the input and then save
	if request.method == 'POST':
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

	# On any GET request, just display the information
	return render_template('puppet/default.html', classes=classes, active='puppet', title="Default Classes")

################################################################################

@app.route('/puppet/nodes')
@app.route('/puppet/nodes/status/<string:status>')
@cortex.lib.user.login_required
def puppet_nodes(status=None):
	"""Handles the Puppet nodes list page"""

	# Check user permissions
	if not does_user_have_permission("puppet.nodes.view"):
		abort(403)

	# Get a cursor to the database
	curd = g.db.cursor(mysql.cursors.DictCursor)

	# Get Puppet nodes from the database
	curd.execute('SELECT `puppet_nodes`.`certname` AS `certname`, `puppet_nodes`.`env` AS `env`, `systems`.`id` AS `id`, `systems`.`name` AS `name`, `systems`.`allocation_comment` AS `allocation_comment` FROM `puppet_nodes` LEFT JOIN `systems` ON `puppet_nodes`.`id` = `systems`.`id` ORDER BY `puppet_nodes`.`certname`')
	results = curd.fetchall()

	# Get node statuses
	try:
		statuses = cortex.lib.puppet.puppetdb_get_node_statuses()
	except Exception as e:
		return stderr("Unable to connect to PuppetDB", "Unable to connect to the Puppet database. The error was: " + type(e).__name__ + " - " + str(e))

	# Create node status data
	data = []
	for row in results:
		row['status'] = statuses[row['certname']]['status'] if row['certname'] in statuses else 'unknown'
		row['clientnoop'] = statuses[row['certname']]['clientnoop'] if row['certname'] in statuses else 'unknown'
		row['latest_report_hash'] = statuses[row['certname']]['latest_report_hash'] if row['certname'] in statuses else 'unknown'

		if status in (None, "all"):
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

	if status in page_title_map:
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
	if not does_user_have_system_permission(system['id'], "view.puppet", "systems.all.view.puppet"):
		abort(403)

	dbnode = None
	facts = None
	try:
		# Connect to PuppetDB, get the node information and then it's related facts
		db = cortex.lib.puppet.puppetdb_connect()
		dbnode = db.node(node)
		facts = dbnode.facts()
	except HTTPError as ex:
		# If we get a 404 from the PuppetDB API
		if ex.response.status_code == 404:
			# We will continue to render the page, just with no facts and display a nice error
			facts = None
		else:
			raise ex
	except Exception as ex:
		return stderr("Unable to connect to PuppetDB", "Unable to connect to the Puppet database. The error was: " + type(ex).__name__ + " - " + str(ex))

	# Turn the facts generator in to a dictionary
	facts_dict = {}

	if facts is not None:
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

	environments = cortex.lib.puppet.get_puppet_environments()

	try:
		stats = cortex.lib.puppet.puppetdb_get_node_stats(
			environments=[env["environment_name"] for env in environments],
		)
	except Exception as ex:
		return stderr("Unable to connect to PuppetDB", "Unable to connect to the Puppet database. The error was: " + type(ex).__name__ + " - " + str(ex))

	return render_template('puppet/dashboard.html', title="Puppet Dashboard", active="puppet", stats=stats)

################################################################################

@app.route('/puppet/radiator')
def puppet_radiator():
	"""Handles the Puppet radiator view page. Similar to the dashboard."""

	## No permissions check: this is accessible without logging in
	try:
		stats = cortex.lib.puppet.puppetdb_get_node_stats_totals()
	except Exception as ex:
		return stderr("Unable to connect to PuppetDB", "Unable to connect to the Puppet database. The error was: " + type(ex).__name__ + " - " + str(ex))

	return render_template('puppet/radiator.html', stats=stats, active='puppet')

################################################################################

@app.route('/puppet/radiator/body')
def puppet_radiator_body():
	"""Handles the body of the Puppet radiator view. JavaScript on the page
	calls this function to update the content using AJAX rather than a
	iffy page refresh."""

	## No permissions check: this is accessible without logging in
	try:
		stats = cortex.lib.puppet.puppetdb_get_node_stats_totals()
	except Exception as ex:
		return stderr("Unable to connect to PuppetDB", "Unable to connect to the Puppet database. The error was: " + type(ex).__name__ + " - " + str(ex))

	return render_template('puppet/radiator-body.html', stats=stats, active='puppet')

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
	if not does_user_have_system_permission(system['id'], "view.puppet", "systems.all.view.puppet"):
		abort(403)

	try:
		# Connect to PuppetDB and get the reports
		db = cortex.lib.puppet.puppetdb_connect()
		reports = db.node(node).reports()

	except HTTPError as ex:
		# If we get a 404 response from PuppetDB
		if ex.response.status_code == 404:
			# Still display the page but with a nice error
			reports = None
		else:
			raise ex
	except Exception as ex:
		return stderr("Unable to connect to PuppetDB", "Unable to connect to the Puppet database. The error was: " + type(ex).__name__ + " - " + str(ex))

	return render_template('puppet/reports.html', reports=reports, active='puppet', title=node + " - Puppet Reports", nodename=node, pactive="reports", system=system)

################################################################################

@app.route('/puppet/report/<report_hash>')
@cortex.lib.user.login_required
def puppet_report(report_hash):
	"""Displays an individual report for a Puppet node"""

	# Connect to Puppet DB and query for a report with the given hash
	try:
		db = cortex.lib.puppet.puppetdb_connect()
	except Exception as ex:
		return stderr("Unable to connect to PuppetDB", "Unable to connect to the Puppet database. The error was: " + type(ex).__name__ + " - " + str(ex))

	reports = db.reports(query='["=", "hash", "' + report_hash + '"]')

	# 'reports' is a generator. Get the next (first and indeed, only item) from the generator
	try:
		report = next(reports)
	except StopIteration:
		# If we get a StopIteration error, then we've not got any data
		# returned from the reports generator, so the report didn't
		# exist, hence we should 404
		return abort(404)

	# Get the system (we need the ID for perms check, amongst other things)
	system = cortex.lib.systems.get_system_by_puppet_certname(report.node)
	if system is None:
		return abort(404)

	## Check if the user is allowed to view the report
	if not does_user_have_system_permission(system['id'], "view.puppet", "systems.all.view.puppet"):
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

	query = request.args.get('q')
	if query is None:
		app.logger.warn('Missing \'query\' parameter in puppet search request')
		return abort(400)

	# Strip and escape wildcards
	query = "%" + query.strip().replace('%', '\\%').replace('_', '\\_') + "%"

	# Search for the text
	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute('''SELECT DISTINCT `puppet_nodes`.`certname` AS `certname`, `puppet_nodes`.`env` AS `env`, `systems`.`id` AS `id`, `systems`.`name` AS `name`  FROM `puppet_nodes` LEFT JOIN `systems` ON `puppet_nodes`.`id` = `systems`.`id` WHERE `puppet_nodes`.`classes` LIKE %s OR `puppet_nodes`.`variables` LIKE %s ORDER BY `puppet_nodes`.`certname`''', (query, query))
	results = curd.fetchall()

	# Get node statuses
	try:
		statuses = cortex.lib.puppet.puppetdb_get_node_statuses()
	except Exception as e:
		return stderr("Unable to connect to PuppetDB", "Unable to connect to the Puppet database. The error was: " + type(e).__name__ + " - " + str(e))

	# Create node status data
	for row in results:
		row['status'] = statuses[row['certname']]['status'] if row['certname'] in statuses else 'unknown'
		row['clientnoop'] = statuses[row['certname']]['clientnoop'] if row['certname'] in statuses else 'unknown'
		row['latest_report_hash'] = statuses[row['certname']]['latest_report_hash'] if row['certname'] in statuses else 'unknown'

	return render_template('puppet/search.html', active='puppet', data=results, title="Puppet search")

##############################################################################

@app.route('/puppet/catalog/<node>')
@cortex.lib.user.login_required
def puppet_catalog(node):
	"""Show the Puppet catalog for a given node."""

	# Get the system
	system = cortex.lib.systems.get_system_by_puppet_certname(node)

	if system is None:
		abort(404)

	## Check if the user is allowed to edit the Puppet configuration
	if not does_user_have_system_permission(system['id'], "view.puppet.catalog", "systems.all.view.puppet.catalog"):
		abort(403)

	dbnode = None
	catalog = None
	try:
		# Connect to PuppetDB, get the node information and then it's catalog.
		db = cortex.lib.puppet.puppetdb_connect()
		dbnode = db.node(node)
		catalog = db.catalog(node)
	except HTTPError as ex:
		# If we get a 404 from the PuppetDB API
		if ex.response.status_code == 404:
			catalog = None
		else:
			raise ex
	except Exception as ex:
		return stderr("Unable to connect to PuppetDB", "Unable to connect to the Puppet database. The error was: " + type(ex).__name__ + " - " + str(ex))

	catalog_dict = {}

	if catalog is not None:
		for res in catalog.get_resources():
			catalog_dict[str(res)] = res.parameters

	# Render
	return render_template('puppet/catalog.html', catalog=catalog_dict, node=dbnode, active='puppet', title=node + " - Puppet Catalog", nodename=node, pactive="catalog", system=system)

@app.route("/puppet/documentation")
@app.route("/puppet/documentation/<int:environment_id>/<string:module_id>")
@cortex.lib.user.login_required
def puppet_documentation(environment_id=None, module_id=None):
	"""Show the Puppet documentation"""

	# Check user permissions
	if not does_user_have_permission("puppet.documentation.view"):
		abort(403)

	# Get the database cursor
	curd = g.db.cursor(mysql.cursors.DictCursor)
	module = None
	data = {}
	if module_id:
		curd.execute("SELECT `puppet_modules`.`id` AS `id`, `puppet_modules`.`module_name` AS `module_name`, `puppet_environments`.`environment_name` AS `environment_name`, `puppet_modules`.`last_updated` AS `last_updated` FROM `puppet_modules` LEFT JOIN `puppet_environments` ON `puppet_modules`.`environment_id`=`puppet_environments`.`id` WHERE `puppet_modules`.`id`=%s AND `puppet_environments`.`id`=%s", (module_id, environment_id))
		module = curd.fetchone()

		if not module:
			abort(404)

		curd.execute("SELECT * FROM `puppet_classes` LEFT JOIN `puppet_documentation` ON `puppet_classes`.`id`=`puppet_documentation`.`class_id` WHERE `puppet_classes`.`module_id`=%s;", (module["id"],))
		for row in curd.fetchall():
			if row["class_name"] not in data:
				data[row["class_name"]] = {"desc": row["desc"]}

			if row["tag"] not in data[row["class_name"]]:
				data[row["class_name"]][row["tag"]] = []

			if any(row[k] for k in ["name", "text"]):
				data[row["class_name"]][row["tag"]].append({
					"name": row.get("name", "") if row.get("name") else "",
					"text": row.get("text", "") if row.get("text") else "",
					"types": json.loads(row["types"]) if row["types"] else [],
				})
	else:
		curd.execute("SELECT `puppet_modules`.`id` AS `module_id`, `puppet_modules`.`module_name` AS `module_name`, `puppet_environments`.`id` AS `environment_id`, `puppet_environments`.`environment_name` AS `environment_name`, `puppet_environments`.`short_name` AS `short_name` FROM `puppet_modules` LEFT JOIN `puppet_environments` ON `puppet_modules`.`environment_id`=`puppet_environments`.`id`")
		for row in curd.fetchall():
			if row["environment_id"] not in data:
				data[row["environment_id"]] = {"name": row["environment_name"], "short_name": row["short_name"], "modules": {}}
			data[row["environment_id"]]["modules"][row["module_id"]] = row["module_name"]

	return render_template('puppet/docs.html', active='puppet', title="Puppet Documentation", module=module, data=data, q=request.args.get("q", None))


@app.route("/puppet/environments", methods=["GET", "POST"])
@app.route("/puppet/environments/<int:environment_id>")
@cortex.lib.user.login_required
def puppet_environments(environment_id=None):
	"""Show the Puppet documentation"""

	# Handle POST request
	if request.method == "POST" and all(k in request.form for k in ["action", "environment_id"]):
		environment_id = request.form["environment_id"]
		if request.form["action"] == "delete_environment":
			if not does_user_have_puppet_permission(environment_id, "delete", "puppet.environments.all.delete"):
				abort(403)
			elif "puppet" not in app.workflows:
				return stderr("Unable to delete Puppet environment", "Error deleting Puppet environment, the workflow 'puppet' is required in order to delete Puppet environments, but was not found in app.workflows.")
			else:
				# Task Options
				options = {
					"actions": [{"id":"environment.delete", "desc": "Deleting Puppet Environment"}],
					"values": {"environment_id": environment_id},
				}
				# Everything should be good - start a task.
				neocortex = cortex.lib.core.neocortex_connect()
				task_id = neocortex.create_task("puppet", session["username"], options, description="Delete Puppet Environment")
				# Redirect to the status page for the task
				return redirect(url_for("task_status", task_id=task_id))
		else:
			abort(400)

	# Handle GET request
	# Get the database cursor
	curd = g.db.cursor(mysql.cursors.DictCursor)

	environments, permissions, nodes = [], [], []
	if environment_id and does_user_have_puppet_permission(environment_id, "view", "puppet.environments.all.view"):
		curd.execute("SELECT * FROM `puppet_environments` WHERE `id`=%s LIMIT 1", (environment_id,))
		environments = curd.fetchall()
		curd.execute("SELECT * FROM `p_puppet_perms_view` WHERE `environment_id`=%s ORDER BY `who`", (environment_id,))
		permissions = curd.fetchall()
	elif environment_id is None:
		if does_user_have_permission("puppet.environments.all.view"):
			environments = cortex.lib.puppet.get_puppet_environments()
		elif does_user_have_any_puppet_permission("view"):
			environments = cortex.lib.puppet.get_puppet_environments(environment_permission="view")
		else:
			abort(403)
	else:
		abort(403)

	# If no results could be found
	if not environments:
		abort(404)

	# If

	if environment_id:
		curd.execute(
			"SELECT `puppet_nodes`.`certname` AS `certname`, `puppet_nodes`.`env` AS `env`, `systems`.`id` AS `id`, `systems`.`name` AS `name`, `systems`.`allocation_comment` AS `allocation_comment` FROM `puppet_nodes` LEFT JOIN `systems` ON `puppet_nodes`.`id` = `systems`.`id` WHERE `puppet_nodes`.`env`=%s ORDER BY `puppet_nodes`.`certname`",
			(environments[0]["environment_name"],)
		)
		nodes = curd.fetchall()

	return render_template("puppet/environments.html", active="puppet", title="Puppet Environments", environment_id=environment_id, environments=environments, permissions=permissions, nodes=nodes)
