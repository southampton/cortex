#!/usr/bin/python
#

from cortex import app, NotFoundError, DisabledError
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
			
			## Check if two-factor is enabled for this account
			## TWO STEP LOGONS
			if app.config['TOTP_ENABLED']:
				if cortex.totp.totp_user_enabled(session['username']):
					app.logger.debug('User "' + session['username'] + '" has two step enabled. Redirecting to two-step handler')
					return redirect(url_for('totp_logon_view',next=request.form.get('next',default=None)))

			## Successful logon without 2-step needed
			return cortex.core.logon_ok()


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
	return render_template('about.html', active='help')

@app.route('/about/changelog')
def changelog():
	return render_template('changelog.html', active='help')

@app.route('/nojs')
def nojs():
	return render_template('nojs.html')
	
@app.route('/test')
def test():
	return render_template('test.html')

@app.route('/dashboard')
def dashboard():
	return render_template('dashboard.html')

################################################################################

@app.route('/vm/create/standard', methods=['GET','POST'])
@cortex.core.login_required
def vm_create_standard():
	domain = "soton.ac.uk"

	if request.method == 'GET' or request.method == 'HEAD':
		return render_template('vm-create.html')
	elif request.method == 'POST':
		# Allocate a system and get its information
		system_info = cortex.core.allocate_name('play', 'Automatic VM', 1)

		# Grab the system name from the returned dictionary
		system_name = system_info.keys()[0]
		print system_name

		# Allocate an IPv4 Address and Create a Host
		ipv4addr = cortex.core.infoblox_create_host(system_name + "." + domain, "192.168.63.0/25")
		print ipv4addr

		if ipv4addr is None:
			abort(500)

		## OH MY GOD WE ARE LOOKING FOR NUCLEAR WESSELS
		#cortex.core.vmware_clone_vm('2012r2template',system_name, cortex.core.OS_TYPE_BY_NAME['Windows'], ipv4addr, "192.168.63.126", "255.255.255.128")
		cortex.core.vmware_clone_vm('autotest_rhel6template',system_name, cortex.core.OS_TYPE_BY_NAME['Linux'], ipv4addr, "192.168.63.126", "255.255.255.128")

		return jsonify(system_name=system_name, ipv4addr=ipv4addr)

################################################################################

@app.route('/vm/create/sandbox', methods=['GET','POST'])
@cortex.core.login_required
def vm_create_sandbox():
	return "Not Implemented"

################################################################################

def render_task_status(id, template):
	"""The task_status and task_status_log functions do /very/ similar
	things. This function does that work, and is herely purely to reduce
	code duplication."""

	# Get a cursor to the database
	cur = g.db.cursor(mysql.cursors.DictCursor)

	# Get the task
	cur.execute("SELECT `id`, `module`, `username`, `start`, `end`, `status` FROM `tasks` WHERE id = %s", (id,))
	task = cur.fetchone()

	# Get the events for the task
	cur.execute("SELECT `id`, `source`, `related_id`, `name`, `username`, `desc`, `status`, `start`, `end` FROM `events` WHERE `related_id` = %s AND `source` = 'neocortex.task'", (id,))
	events = cur.fetchall()

	return render_template(template, id=id, task=task, events=events)


@app.route('/task/status/<int:id>', methods=['GET'])
@cortex.core.login_required
def task_status(id):
	"""Handles the Task Status page for a individual task."""

	return render_task_status(id, "task-status.html")

@app.route('/task/status/<int:id>/log', methods=['GET'])
@cortex.core.login_required
def task_status_log(id):
	"""Much like task_status, but only returns the event log. This is used by 
	an AJAX routine on the page to refresh the log every 10 seconds."""

	return render_task_status(id, "task-status-log.html")

