#!/usr/bin/python

from cortex import app
import cortex.lib.core
import cortex.lib.user
import cortex.lib.vmware
import cortex.lib.puppet
from cortex.lib.user import does_user_have_permission
from flask import Flask, request, session, redirect, url_for, flash, g, abort, make_response, render_template, jsonify
import os 
import datetime
import MySQLdb as mysql

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
	curd.execute('SELECT COUNT(*) AS `count` FROM `vmware_cache_vm` WHERE `template` = 0');
	row = curd.fetchone()
	vm_count = row['count']
	
	# Get number of CIs
	curd.execute('SELECT COUNT(*) AS `count` FROM `sncache_cmdb_ci`');
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
	curd.execute("SELECT * FROM `systems_info_view` WHERE (`id` IN (SELECT `system_id` FROM `system_perms_view` WHERE (`type` = '0' AND `who` = %s AND (`perm` = 'view' OR `perm` = 'view.overview' OR `perm` = 'view.detail')) OR (`type` = '1' AND (`perm` = 'view' OR `perm` = 'view.overview' OR `perm` = 'view.detail') AND `who` IN (SELECT `group` FROM `ldap_group_cache` WHERE `username` = %s))) OR `allocation_who`=%s) AND ((`cmdb_id` IS NOT NULL AND `cmdb_operational_status` = 'In Service') OR `vmware_uuid` IS NOT NULL) ORDER BY `allocation_date` DESC LIMIT 100;",(session['username'],session['username'], session['username']))
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
		# Get the current time minus 2 hours.
		now_minus_2 = datetime.datetime.now() - datetime.timedelta(hours=2)
		stats = {
			'failed': len(cortex.lib.puppet.puppetdb_query('nodes', query='["extract","certname",["and",["=", "latest_report_status", "failed"], ["=", "latest_report_noop", false], [">", "report_timestamp", "{0}"]]]'.format(now_minus_2.isoformat()))),
			'changed': len(cortex.lib.puppet.puppetdb_query('nodes', query='["extract", "certname",["and",["=", "latest_report_status", "changed"],["=", "latest_report_noop", false], [">", "report_timestamp", "{0}"]]]'.format(now_minus_2.isoformat()))),
		}
	except Exception as e:
		import traceback
		app.logger.error("Failed to talk to PuppetDB on dashboard:\n" + traceback.format_exc())
		stats = { 'failed': '???', 'changed': '???' }
	
	return render_template('dashboard.html', active="dashboard", 
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
		stats=stats)

################################################################################

@app.route('/task/status/<int:id>', methods=['GET'])
@cortex.lib.user.login_required
def task_status(id):
	"""Handles the Task Status page for a individual task."""

	## Get the task details
	task = cortex.lib.core.task_get(id)

	# Return a 404 if we've not found the task
	if not task:
		abort(404)

	# Check the user has the permission to view this task
	if not task['username'] == session['username']:
		if not does_user_have_permission("tasks.view"):
			abort(403)

	return cortex.lib.core.task_render_status(task, "tasks/status.html")

################################################################################

@app.route('/task/status/<int:id>/log', methods=['GET'])
@cortex.lib.user.login_required
def task_status_log(id):
	"""Much like task_status, but only returns the event log. This is used by 
	an AJAX routine on the page to refresh the log every 10 seconds."""

	## Get the task details
	task = cortex.lib.core.task_get(id)

	# Return a 404 if we've not found the task
	if not task:
		abort(404)

	# Check the user has the permission to view this task
	if not task['username'] == session['username']:
		if not does_user_have_permission("tasks.view"):
			abort(403)

	return cortex.lib.core.task_render_status(task, "tasks/status-log.html")
