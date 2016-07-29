#!/usr/bin/python
#

from cortex import app
import cortex.lib.core
from flask import Flask, request, session, redirect, url_for, flash, g, abort, render_template, jsonify
import re
import MySQLdb as mysql

################################################################################

@app.route('/admin/tasks')
@cortex.lib.user.login_required
def admin_tasks():
	"""Displays the list of tasks to the user."""

	# Render the page
	return render_template('admin/tasks.html', active='admin', title="Tasks", tasktype='all', json_source=url_for('admin_tasks_json', tasktype='all'))

################################################################################

@app.route('/admin/tasks/json/<tasktype>', methods=['POST'])
@cortex.lib.user.login_required
@app.disable_csrf_check
def admin_tasks_json(tasktype):
	# Get a cursor to the database
	curd = g.db.cursor(mysql.cursors.DictCursor)

	# Extract stuff from DataTables requests
	(draw, start, length, order_column, order_asc, search) = _tasks_extract_datatables()

	# Choose the order column
	if order_column == 0:
		order_by = "id"
	elif order_column == 1:
		order_by = "module"
	elif order_column == 2:
		order_by = "start"
	elif order_column == 3:
		order_by = "end"
	elif order_column == 4:
		order_by = "elapsed"
	elif order_column == 5:
		order_by = "username"
	elif order_column == 6:
		order_by = "status"
	else:
		app.logger.warn('Invalid ordering column parameter in DataTables request')
		abort(400)

	# Choose order direction
	order_dir = "DESC"
	if order_asc:
		order_dir = "ASC"

	# Determine the task type and add that to the query
	params = ()
	where_clause = ""
	if tasktype == 'all':
		where_clause = '1=1'	# This is just to make 'search' always be able to be an AND and not need an optional WHERE
	elif tasktype == 'user':
		where_clause = '`username` != "scheduler"'
	elif tasktype == 'system':
		where_clause = '`username` = "scheduler"'
	else:
		abort(404)

	# Add on search string if we have one
	if search:
		where_clause = where_clause + " AND (`module` LIKE %s OR `username` LIKE %s) "
		params = params + ('%' + search + '%', '%' + search + '%')

	# Get the total number of tasks
	curd.execute("SELECT COUNT(*) AS `count` FROM `tasks`")
	task_count = curd.fetchone()['count']

	# Get the total number of tasks
	curd.execute("SELECT COUNT(*) AS `count` FROM `tasks` WHERE " + where_clause, params)
	filtered_task_count = curd.fetchone()['count']

	# Get the list of tasks
	curd.execute("SELECT `id`, `module`, `username`, `start`, `end`, `status`, `description` FROM `tasks` WHERE " + where_clause + " ORDER BY `" + order_by + "` " + order_dir + " LIMIT " + str(start) + "," + str(length), params)
	tasks = curd.fetchall()

	# Build an array of tasks
	task_data = []
	for task in tasks:
		# Format elapsed string nicely rather than just seconds which is what comes back from MySQL
		if task['start'] and task['end']:
			task['elapsed'] = str(task['end'] - task['start'])
		else:
			task['elapsed'] = ''

		# Format start time string
		if task['start']:
			task['start'] = task['start'].strftime('%Y-%m-%d %H:%M:%S')

		# Format end time string
		if task['end']:
			task['end'] = task['end'].strftime('%Y-%m-%d %H:%M:%S')

		# Add row to results
		task_data.append([task['id'], task['module'], task['start'], task['end'], task['elapsed'], task['username'], task['status'], task['description']])

	return jsonify(draw=draw, recordsTotal=task_count, recordsFiltered=filtered_task_count, data=task_data)

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
	return render_template('admin/tasks.html', tasks=tasks, active='admin', title="Active Tasks", tasktype='active')

################################################################################

@app.route('/admin/tasks/user')
@cortex.lib.user.login_required
def admin_tasks_user():
	"""Displays the list of tasks, excluding any system tasks"""

	# Render the page
	return render_template('admin/tasks.html', active='admin', title="User Tasks", tasktype='user', json_source=url_for('admin_tasks_json', tasktype='user'))

################################################################################

@app.route('/admin/tasks/system')
@cortex.lib.user.login_required
def admin_tasks_system():
	"""Displays the list of tasks started by the system"""

	# Render the page
	return render_template('admin/tasks.html', active='admin', title="System Tasks", tasktype='system', json_source=url_for('admin_tasks_json', tasktype='system'))

################################################################################

@app.route('/admin/classes', methods=['GET', 'POST'])
@cortex.lib.user.login_required
def admin_classes():
	"""Handles the content of the Admin -> Classes page"""

	# On a GET request, display the list of classes page
	if request.method == 'GET':
		classes = cortex.lib.classes.list(hide_disabled=False)
		return render_template('admin/classes.html', classes=classes, active='admin', cmdb_types=app.config['CMDB_CACHED_CLASSES'], title="Classes")

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

		elif action == "create_default_classes":

			curd.execute('SELECT 1 FROM `classes` WHERE `name` = %s;', ("srv"))
			if curd.fetchone() is None:
				curd.execute('''INSERT INTO `classes` (`name`, `digits`, `comment`, `disabled`, `link_vmware`, `cmdb_type`) VALUES ('srv', 5, 'Standard servers, physical and VMs', 0, 1, 'cmdb_ci_server')''')
				g.db.commit()

			curd.execute('SELECT 1 FROM `classes` WHERE `name` = %s;', ("play"))
			if curd.fetchone() is None:
				curd.execute('''INSERT INTO `classes` (`name`, `digits`, `comment`, `disabled`, `link_vmware`, `cmdb_type`) VALUES ('play', 5, 'Sandbox cluster VMs', 0, 1, 'cmdb_ci_server')''')
				g.db.commit()

			curd.execute('SELECT 1 FROM `classes` WHERE `name` = %s;', ("vhost"))
			if curd.fetchone() is None:
				curd.execute('''INSERT INTO `classes` (`name`, `digits`, `comment`, `disabled`, `link_vmware`, `cmdb_type`) VALUES ('vhost', 5, 'Virtualisation hosts', 0, 0, 'cmdb_ci_server')''')
				g.db.commit()

			curd.execute('SELECT 1 FROM `classes` WHERE `name` = %s;', ("stg"))
			if curd.fetchone() is None:
				curd.execute('''INSERT INTO `classes` (`name`, `digits`, `comment`, `disabled`, `link_vmware`, `cmdb_type`) VALUES ('stg', 5, 'Storage devices', 0, 0, 'cmdb_ci_msd')''')
				g.db.commit()

			curd.execute('SELECT 1 FROM `classes` WHERE `name` = %s;', ("ibs"))
			if curd.fetchone() is None:
				curd.execute('''INSERT INTO `classes` (`name`, `digits`, `comment`, `disabled`, `link_vmware`, `cmdb_type`) VALUES ('ibs', 5, 'Infiniband switches', 0, 0, 'cmdb_ci_netgear')''')
				g.db.commit()

			curd.execute('SELECT 1 FROM `classes` WHERE `name` = %s;', ("san"))
			if curd.fetchone() is None:
				curd.execute('''INSERT INTO `classes` (`name`, `digits`, `comment`, `disabled`, `link_vmware`, `cmdb_type`) VALUES ('san', 5, 'Fibre channel switches', 0, 0, 'cmdb_ci_netgear')''')
				g.db.commit()

			flash("System classes added", "alert-success")
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
			elif task['name'] == '_cache_servicenow':
				sncache_task_id = task['id']

		# Render the page
		return render_template('admin/maint.html', active='admin', sncache_task_id=sncache_task_id, vmcache_task_id=vmcache_task_id, title="Maintenance Tasks")

	else:
		# Find out what task to start
		module = request.form['task_name']

		# Start the appropriate internal task
		if module == 'vmcache':
			task_id = neocortex.start_internal_task(session['username'], 'cache_vmware.py', '_cache_vmware', description="Caches information about virtual machines, datacenters and clusters from VMware")
		elif module == 'sncache':
			task_id = neocortex.start_internal_task(session['username'], 'cache_servicenow.py', '_cache_servicenow', description="Caches server CIs from the ServiceNow CMDB")
		else:
			app.logger.warn('Unknown module name specified when starting task')
			abort(400)

		# Show the user the status of the task
		return redirect(url_for('task_status', id=task_id))

################################################################################

def _tasks_extract_datatables():
	# Validate and extract 'draw' parameter. This parameter is simply a counter
	# that DataTables uses internally.
	if 'draw' in request.form:
		draw = int(request.form['draw'])
	else:   
		app.logger.warn('\'draw\' parameter missing from DataTables request')
		abort(400)

	# Validate and extract 'start' parameter. This parameter is the index of the
	# first row to return.
	if 'start' in request.form:
		start = int(request.form['start'])
	else:
		app.logger.warn('\'start\' parameter missing from DataTables request')
		abort(400)

	# Validate and extract 'length' parameter. This parameter is the number of
	# rows that we should return
	if 'length' in request.form:
		length = int(request.form['length'])
		if length < 0:
			length = None
	else:
		app.logger.warn('\'length\' parameter missing from DataTables request')
		abort(400)

	# Validate and extract ordering column. This parameter is the index of the
	# column on the HTML table to order by
	if 'order[0][column]' in request.form:
		order_column = int(request.form['order[0][column]'])
	else:
		order_column = 0

	# Validate and extract ordering direction. 'asc' for ascending, 'desc' for
	# descending.
	if 'order[0][dir]' in request.form:
		if request.form['order[0][dir]'] == 'asc':
			order_asc = True
		elif request.form['order[0][dir]'] == 'desc':
			order_asc = False
		else:
			app.logger.warn('Invalid \'order[0][dir]\' parameter in DataTables request')
			abort(400)
	else:
		order_asc = False

	# Handle the search parameter. This is the textbox on the DataTables
	# view that the user can search by typing in
	search = None
	if 'search[value]' in request.form:
		if request.form['search[value]'] != '':
			if type(request.form['search[value]']) is not str and type(request.form['search[value]']) is not unicode:
				search = str(request.form['search[value]'])
			else:
				search = request.form['search[value]']

	return (draw, start, length, order_column, order_asc, search)
