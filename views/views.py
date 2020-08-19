
import traceback

import MySQLdb as mysql
from flask import abort, g, render_template, request, session

import cortex.lib.core
import cortex.lib.puppet
import cortex.lib.user
import cortex.lib.vmware
from cortex import app
from cortex.lib.user import does_user_have_permission

################################################################################

@app.route('/about')
def about():
	"""Renders the about page"""

	return render_template('about.html', active='about', title="About")

################################################################################

@app.route('/nojs')
def nojs():
	"""Renders the 'you have JavaScript disabled' page"""

	return render_template('nojs.html')

################################################################################

@app.route('/dashboard')
@cortex.lib.user.login_required
def dashboard():
	"""This renders the front page after the user logged in."""

	# Get a cursor to the database
	curd = g.db.cursor(mysql.cursors.DictCursor)

	# Get number of VMs
	curd.execute('SELECT COUNT(*) AS `count` FROM `vmware_cache_vm` WHERE `template` = 0')
	row = curd.fetchone()
	vm_count = row['count']

	# Get number of CIs
	curd.execute('SELECT COUNT(*) AS `count` FROM `sncache_cmdb_ci`')
	row = curd.fetchone()
	ci_count = row['count']

	# Get number of in-progress tasks
	curd.execute('SELECT COUNT(*) AS `count` FROM `tasks` WHERE `status` = %s', (0,))
	row = curd.fetchone()
	task_progress_count = row['count']

	# Get number of failed tasks in the last 8 hours
	curd.execute('SELECT COUNT(*) AS `count` FROM `tasks` WHERE `status` = %s AND `end` > DATE_SUB(NOW(), INTERVAL 8 HOUR)', (2,))
	row = curd.fetchone()
	task_failed_count = row['count']

	# Get number of warning tasks in the last 8 hours
	curd.execute('SELECT COUNT(*) AS `count` FROM `tasks` WHERE `status` = %s AND `end` > DATE_SUB(NOW(), INTERVAL 8 HOUR)', (3,))
	row = curd.fetchone()
	task_warning_count = row['count']

	# Get tasks for user
	curd.execute('SELECT `id`, `module`, `start`, `end`, `status`, `description` FROM `tasks` WHERE `username` = %s ORDER BY `start` DESC LIMIT 5', (session['username'],))
	tasks = curd.fetchall()

	# We don't need the data, but we need to make sure the LDAP cache is up
	# to date for the systems query to work
	cortex.lib.user.get_users_groups()

	# Get the list of systems the user is specifically allowed to view
	curd.execute("SELECT * FROM `systems_info_view` WHERE (`id` IN (SELECT `p_system_perms_who`.`system_id` FROM `p_system_perms_who` JOIN `p_system_perms` ON `p_system_perms_who`.`perm_id`=`p_system_perms`.`id` WHERE (`p_system_perms_who`.`type` = '0' AND `p_system_perms_who`.`who` = %s AND (`p_system_perms`.`perm` = 'view' OR `p_system_perms`.`perm` = 'view.overview' OR `p_system_perms`.`perm` = 'view.detail')) OR (`p_system_perms_who`.`type` = '1' AND (`p_system_perms`.`perm` = 'view' OR `p_system_perms`.`perm` = 'view.overview' OR `p_system_perms`.`perm` = 'view.detail') AND `p_system_perms_who`.`who` IN (SELECT `group` FROM `ldap_group_cache` WHERE `username` = %s))) OR `allocation_who`=%s) AND ((`cmdb_id` IS NOT NULL AND `cmdb_operational_status` = 'In Service') OR `vmware_uuid` IS NOT NULL) ORDER BY `allocation_date` DESC LIMIT 100", (session['username'], session['username'], session['username']))
	systems = curd.fetchall()

	# Recent systems
	curd.execute("SELECT * FROM `systems_info_view` ORDER BY `allocation_date` DESC LIMIT 0,5")
	recent_systems = curd.fetchall()

	# OS VM stats
	types = cortex.lib.vmware.get_os_stats()

	curd.execute("SELECT SUM(`ram`) AS `total` FROM `vmware_cache_clusters`")
	total_ram = curd.fetchone()['total'] or 0

	curd.execute("SELECT SUM(`ram_usage`) AS `total` FROM `vmware_cache_clusters`")
	total_ram_usage = int(curd.fetchone()['total'] or 0) * 1024 * 1024

	curd.execute("SELECT SUM(`memoryMB`) AS `total` FROM `vmware_cache_vm`")
	total_vm_ram = (curd.fetchone()['total'] or 0) * 1024 * 1024

	# Puppet Stats
	try:
		stats = {
			'failed': len(cortex.lib.puppet.puppetdb_query('nodes', query='["extract","certname",["and",["=", "latest_report_status", "failed"], ["=", "latest_report_noop", false]]]')),
			'changed': len(cortex.lib.puppet.puppetdb_query('nodes', query='["extract", "certname",["and",["=", "latest_report_status", "changed"],["=", "latest_report_noop", false]]]')),
		}
	except Exception:
		app.logger.error("Failed to talk to PuppetDB on dashboard:\n" + traceback.format_exc())
		stats = {'failed': '???', 'changed': '???'}

	return render_template(
		'dashboard.html',
		active="dashboard",
		vm_count=vm_count,
		ci_count=ci_count,
		task_progress_count=task_progress_count,
		task_failed_count=task_failed_count,
		task_warning_count=task_warning_count,
		tasks=tasks,
		types=types,
		title="Dashboard",
		systems=systems,
		syscount=len(systems),
		recent_systems=recent_systems,
		total_ram=total_ram,
		total_ram_usage=total_ram_usage,
		total_vm_ram=total_vm_ram,
		stats=stats
	)

################################################################################

@app.route('/task/status/<int:task_id>', methods=['GET'])
@cortex.lib.user.login_required
def task_status(task_id):
	"""Handles the Task Status page for a individual task."""

	## Get the task details
	task = cortex.lib.core.task_get(task_id)

	# Return a 404 if we've not found the task
	if not task:
		abort(404)

	# Check the user has the permission to view this task
	if not task['username'] == session['username']:
		if not does_user_have_permission("tasks.view"):
			abort(403)

	# Check if the hide success flag is set
	hide_success = False
	if "hide_success" in request.args and request.args.get("hide_success", None):
		hide_success = True

	return cortex.lib.core.task_render_status(task, "tasks/status.html", hide_success=hide_success)

################################################################################

@app.route('/task/status/<int:task_id>/log', methods=['GET'])
@cortex.lib.user.login_required
def task_status_log(task_id):
	"""Much like task_status, but only returns the event log. This is used by
	an AJAX routine on the page to refresh the log every 10 seconds."""

	## Get the task details
	task = cortex.lib.core.task_get(task_id)

	# Return a 404 if we've not found the task
	if not task:
		abort(404)

	# Check the user has the permission to view this task
	if not task['username'] == session['username']:
		if not does_user_have_permission("tasks.view"):
			abort(403)

	# Check if the hide success flag is set
	hide_success = False
	if "hide_success" in request.args and request.args.get("hide_success", None):
		hide_success = True

	return cortex.lib.core.task_render_status(task, "tasks/status-log.html", hide_success=hide_success)
