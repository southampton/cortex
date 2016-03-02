#!/usr/bin/python
#

from cortex import app
import cortex.lib.core
from flask import Flask, request, session, redirect, url_for, flash, g, abort, render_template
import re
import MySQLdb as mysql

################################################################################

@app.route('/admin/tasks')
@cortex.lib.user.login_required
def admin_tasks():
	"""Displays the list of tasks to the user."""

	# Get all the tasks from the database
	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute("SELECT `id`, `module`, `username`, `start`, `end`, `status`, `description` FROM `tasks`")
	tasks = curd.fetchall()

	# Render the page
	return render_template('admin-tasks.html', tasks=tasks, active='admin', title="Tasks", tasktype='all')

################################################################################

@app.route('/admin/tasks/active')
@cortex.lib.user.login_required
def admin_tasks_active():
	"""Displays the active tasks"""

	# Get the list of tasks from NeoCortex
	curd = g.db.cursor(mysql.cursors.DictCursor)
	neocortex = cortex.lib.core.neocortex_connect()
	neotasks  = neocortex.active_tasks()
	tasks     = []

	# Get additional information out of the database
	for ntask in neotasks:
		curd.execute("SELECT `id`, `module`, `username`, `start`, `end`, `status`, `description` FROM `tasks` WHERE `id` = %s", (ntask['id']))
		task = curd.fetchone()
		if not task == None:
			tasks.append(task)

	# Render the page
	return render_template('admin-tasks.html', tasks=tasks, active='admin', title="Active Tasks", tasktype='active')

################################################################################

@app.route('/admin/tasks/user')
@cortex.lib.user.login_required
def admin_tasks_user():
	"""Displays the list of tasks, excluding any system tasks"""

	# Get all the tasks from the database
	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute("SELECT `id`, `module`, `username`, `start`, `end`, `status`, `description` FROM `tasks` WHERE `username` != 'scheduler'")
	tasks = curd.fetchall()

	# Render the page
	return render_template('admin-tasks.html', tasks=tasks, active='admin', title="User Tasks", tasktype='user')

################################################################################

@app.route('/admin/tasks/system')
@cortex.lib.user.login_required
def admin_tasks_system():
	"""Displays the list of tasks started by the system"""

	# Get all the tasks from the database
	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute("SELECT `id`, `module`, `username`, `start`, `end`, `status`, `description` FROM `tasks` WHERE `username` = 'scheduler'")
	tasks = curd.fetchall()

	# Render the page
	return render_template('admin-tasks.html', tasks=tasks, active='admin', title="System Tasks", tasktype='system')

################################################################################

@app.route('/admin/classes', methods=['GET', 'POST'])
@cortex.lib.user.login_required
def admin_classes():
	"""Handles the content of the Admin -> Classes page"""

	# On a GET request, display the list of classes page
	if request.method == 'GET':
		classes = cortex.lib.classes.list(hide_disabled=False)
		return render_template('admin-classes.html', classes=classes, active='admin', cmdb_types=app.config['CMDB_CACHED_CLASSES'], title="Classes")

	elif request.method == 'POST':
		action = request.form['action']
		curd   = g.db.cursor()

		if action in ['add_class', 'edit_class']:		
			# Validate class name/prefix
			class_name = request.form['class_name']
			if not re.match(r'^[a-z]{1,16}$', class_name):
				flash("The class prefix you sent was invalid. It can only contain lowercase letters and be at least 1 character long and at most 16", "alert-danger")
				return redirect(url_for('admin_classes'))

			# Validate number of digits in hostname/server name
			try:
				class_digits = int(request.form['class_digits'])
			except ValueError:
				flash("The class digits you sent was invalid (it was not a number)." + str(type(class_digits)), "alert-danger")
				return redirect(url_for('admin_classes'))

			if class_digits < 1 or class_digits > 10:
				flash("The class digits you sent was invalid. It must be between 1 and 10.", "alert-danger")
				return redirect(url_for('admin_classes'))

			# Extract whether the new class is active
			if "class_active" in request.form:
				class_disabled = 0
			else:
				class_disabled = 1

			# Validate the comment for the class
			class_comment = request.form['class_comment']
			if not re.match(r'^.{3,512}$', class_comment):
				flash("The class comment you sent was invalid. It must be between 3 and 512 characters long.", "alert-danger")
				return redirect(url_for('admin_classes'))

			# Validate the CMDB type
			class_cmdb_type = request.form['class_cmdb_type']
			if len(class_cmdb_type) == 0:
				class_cmdb_type = None

			# Extract whether the new class links to VMware
			if "class_link_vmware" in request.form:
				class_link_vmware = 1
			else:
				class_link_vmware = 0

			# Check if the class already exists
			curd.execute('SELECT 1 FROM `classes` WHERE `name` = %s;', (class_name))
			if curd.fetchone() is None:
				class_exists = False
			else:
				class_exists = True

			if action == 'add_class':
				if class_exists:
					flash('A system class already exists with that prefix', 'alert-danger')
					return redirect(url_for('admin_classes'))

				# SQL insert
				curd.execute('''INSERT INTO `classes` (`name`, `digits`, `comment`, `disabled`, `link_vmware`, `cmdb_type`) VALUES (%s, %s, %s, %s, %s, %s)''', (class_name, class_digits, class_comment, class_disabled, class_link_vmware, class_cmdb_type))
				g.db.commit()

				flash("System class created", "alert-success")
				return redirect(url_for('admin_classes'))							
			

			elif action == 'edit_class':
				if not class_exists:
					flash('No system class matching that name/prefix could be found', 'alert-danger')
					return redirect(url_for('admin_classes'))

				curd.execute('''UPDATE `classes` SET `digits` = %s, `disabled` = %s, `comment` = %s, `link_vmware` = %s, `cmdb_type` = %s WHERE `name` = %s''', (class_digits, class_disabled, class_comment, class_link_vmware, class_cmdb_type, class_name))
				g.db.commit()

				flash("System class updated", "alert-success")
				return redirect(url_for('admin_classes'))

		else:
			abort(400)

################################################################################

@app.route('/admin/maintenance', methods=['GET', 'POST'])
@cortex.lib.user.login_required
def admin_maint():
	"""Allows the user to kick off scheduled jobs on demand"""

	# Connect to NeoCortex and the database
	neocortex = cortex.lib.core.neocortex_connect()
	curd = g.db.cursor(mysql.cursors.DictCursor)

	# Initial setup
	vmcache_task_id = None
	vmcache_novm_task_id = None
	sncache_task_id = None

	if request.method == 'GET':
		# See which tasks are already running
		active_tasks = neocortex.active_tasks()

		for task in active_tasks:
			if task['name'] == '_cache_vmware':
				vmcache_task_id = task['id']
			elif task['name'] == '_cache_vmware_novm':
				vmcache_novm_task_id = task['id']
			elif task['name'] == '_cache_servicenow':
				sncache_task_id = task['id']

		# Render the page
		return render_template('admin-maint.html', active='admin', sncache_task_id=sncache_task_id, vmcache_task_id=vmcache_task_id, vmcache_novm_task_id=vmcache_novm_task_id, title="Maintenance Tasks")

	else:
		# Find out what task to start
		module = request.form['task_name']

		# Start the appropriate internal task
		if module == 'vmcache':
			task_id = neocortex.start_internal_task(session['username'], 'cache_vmware.py', '_cache_vmware', description="Caches information about virtual machines, datacenters and clusters from VMware")
		elif module == 'vmcache_novm':
			task_id = neocortex.start_internal_task(session['username'], 'cache_vmware.py', '_cache_vmware_novm', options={'skip_vms': True}, description="Caches information about virtual machines, datacenters and clusters from VMware")
		elif module == 'sncache':
			task_id = neocortex.start_internal_task(session['username'], 'cache_servicenow.py', '_cache_servicenow', description="Caches server CIs from the ServiceNow CMDB")
		else:
			abort(400)

		# Show the user the status of the task
		return redirect(url_for('task_status', id=task_id))

