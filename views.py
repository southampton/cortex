#!/usr/bin/python
#

from cortex import app
import cortex.core
from flask import Flask, request, session, redirect, url_for, flash, g, abort, make_response, render_template, jsonify
import os 
import re
import MySQLdb as mysql

import time
from multiprocessing import Process, Value
import syslog

################################################################################
#### HOME PAGE / LOGIN PAGE

@app.route('/', methods=['GET', 'POST'])
def login():
	if cortex.core.is_user_logged_in():
		return redirect(url_for('dashboard'))
	else:
		if request.method == 'GET' or request.method == 'HEAD':
			next = request.args.get('next',default=None)
			return render_template('login.html', next=next)

		elif request.method == 'POST':
			result = cortex.core.auth_user(request.form['username'], request.form['password'])

			if not result:
				flash('Incorrect username and/or password','alert-danger')
				return redirect(url_for('login'))
			
			## Set the username in the session
			session['username']  = request.form['username'].lower()
			
			## restrict all logons to admins
			if cortex.core.is_user_global_admin(session['username']):
				return cortex.core.logon_ok()
			else:
				flash('Permission denied','alert-danger')
				return redirect(url_for('login'))

################################################################################
#### LOGOUT

@app.route('/logout')
@cortex.core.login_required
def logout():
	## Log out of the session
	cortex.core.session_logout()
	
	## Tell the user
	flash('You were logged out successfully','alert-success')
	
	## redirect the user to the logon page
	return redirect(url_for('login'))

#### HELP PAGES
@app.route('/about')
def about():
	return render_template('about.html', active='help', title="About")

################################################################################

@app.route('/nojs')
def nojs():
	return render_template('nojs.html')

################################################################################

@app.route('/dashboard')
@cortex.core.login_required
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
@cortex.core.login_required
def task_status(id):
	"""Handles the Task Status page for a individual task."""

	return render_task_status(id, "task-status.html")

################################################################################

@app.route('/task/status/<int:id>/log', methods=['GET'])
@cortex.core.login_required
def task_status_log(id):
	"""Much like task_status, but only returns the event log. This is used by 
	an AJAX routine on the page to refresh the log every 10 seconds."""

	return render_task_status(id, "task-status-log.html")

################################################################################

@app.route('/user/groups')
@cortex.core.login_required
def user_groups():
	ldap_groups = cortex.core.get_users_groups(session['username'])
	groups = []

	for lgroup in ldap_groups:
		p = re.compile("^(cn|CN)=([^,;]+),")
		matched = p.match(lgroup)
		if matched:
			name = matched.group(2)
			groups.append({"name": name, "dn": lgroup})
	

	return render_template('user-groups.html', active='user', groups=groups, title="AD Groups")
