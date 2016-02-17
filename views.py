#!/usr/bin/python

from cortex import app
import cortex.lib.user
from flask import Flask, request, session, redirect, url_for, flash, g, abort, make_response, render_template, jsonify
import os 
import MySQLdb as mysql

################################################################################

@app.route('/about')
def about():
	return render_template('about.html', active='help', title="About")

################################################################################

@app.route('/nojs')
def nojs():
	return render_template('nojs.html')

################################################################################

@app.route('/dashboard')
@cortex.lib.user.login_required
def dashboard():
	"""This renders the front page after the user logged in."""

	# Get a cursor to the database
	cur = g.db.cursor(mysql.cursors.DictCursor)
	
	# Get number of VMs
	cur.execute('SELECT COUNT(*) AS `count` FROM `vmware_cache_vm`');
	row = cur.fetchone()
	vm_count = row['count']
	
	# Get number of CIs
	cur.execute('SELECT COUNT(*) AS `count` FROM `sncache_cmdb_ci`');
	row = cur.fetchone()
	ci_count = row['count']

	# Get number of in-progress tasks
	cur.execute('SELECT COUNT(*) AS `count` FROM `tasks` WHERE `status` = %s', (0,))
	row = cur.fetchone()
	task_progress_count = row['count']

	# Get number of failed tasks in the last 3 hours
	cur.execute('SELECT COUNT(*) AS `count` FROM `tasks` WHERE `status` = %s AND `end` > DATE_SUB(NOW(), INTERVAL 3 HOUR)', (2,))
	row = cur.fetchone()
	task_failed_count = row['count']

	# Get tasks for user
	cur.execute('SELECT `id`, `module`, `start`, `end`, `status`, `description` FROM `tasks` WHERE `username` = %s ORDER BY `start` DESC LIMIT 5', (session['username'],))
	tasks = cur.fetchall()

	return render_template('dashboard.html', vm_count=vm_count, ci_count=ci_count, task_progress_count=task_progress_count, task_failed_count=task_failed_count, tasks=tasks, title="Dashboard")

################################################################################

def render_task_status(id, template):
	"""The task_status and task_status_log functions do /very/ similar
	things. This function does that work, and is herely purely to reduce
	code duplication."""

	# Get a cursor to the database
	cur = g.db.cursor(mysql.cursors.DictCursor)

	# Get the task
	cur.execute("SELECT `id`, `module`, `username`, `start`, `end`, `status`, `description` FROM `tasks` WHERE id = %s", (id,))
	task = cur.fetchone()

	# Get the events for the task
	cur.execute("SELECT `id`, `source`, `related_id`, `name`, `username`, `desc`, `status`, `start`, `end` FROM `events` WHERE `related_id` = %s AND `source` = 'neocortex.task'", (id,))
	events = cur.fetchall()

	return render_template(template, id=id, task=task, events=events, title="Task Status")

################################################################################

@app.route('/task/status/<int:id>', methods=['GET'])
@cortex.lib.user.login_required
def task_status(id):
	"""Handles the Task Status page for a individual task."""

	return render_task_status(id, "task-status.html")

################################################################################

@app.route('/task/status/<int:id>/log', methods=['GET'])
@cortex.lib.user.login_required
def task_status_log(id):
	"""Much like task_status, but only returns the event log. This is used by 
	an AJAX routine on the page to refresh the log every 10 seconds."""

	return render_task_status(id, "task-status-log.html")
