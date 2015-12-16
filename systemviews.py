#!/usr/bin/python
#

from cortex import app
import cortex.core
from flask import Flask, request, session, redirect, url_for, flash, g, abort, make_response, render_template, jsonify
import os 
import time
import json
import re
import werkzeug
import MySQLdb as mysql
import yaml

################################################################################

@app.route('/systems')
@cortex.core.login_required
def systems():
	"""Shows the list of known systems to the user."""

	# Get the list of systems
	systems = cortex.core.get_systems()

	# Get the list of active classes (used to populate the tab bar)
	classes = cortex.admin.get_classes(True)

	# Render
	return render_template('systems.html', systems=systems, classes=classes, active='systems')

################################################################################

@app.route('/systems/new', methods=['GET','POST'])
@cortex.core.login_required
def systems_new():
	"""Handles the Allocate New System Name(s) page"""

	# On GET requests, just show big buttons for all the classes
	if request.method == 'GET':
		classes = cortex.admin.get_classes(True)
		return render_template('systems-new.html', classes=classes, active='allocate')

	# On POST requests...
	elif request.method == 'POST':
		## The user has asked for one or more new system names.

		# Grab the prefix chosen and validate it's a valid class name.
		# The regular expression matches on an entire string of 1 to 16 lowercase characters
		class_name = request.form['class_name']
		if not re.match(r'^[a-z]{1,16}$', class_name):
			flash("The class prefix you sent was invalid. It can only contain lowercase letters and be at least 1 character long and at most 16", "alert-danger")
			return redirect(url_for('systems_new'))

		# Grab how many names the user wants and validate it
		system_number = int(request.form['system_number'])

		# Validate the number of systems
		if system_number < 1 or system_number > 50:
			flash("You cannot allocate more than 50 names at once, sorry about that.", "alert-danger")
			return redirect(url_for('admin_classes'))

		# Grab the comment
		if 'system_comment' in request.form:
			system_comment = request.form['system_comment']
		else:
			system_comment = ""

		## Allocate the names asked for
		try:
			# To prevent code duplication, this is done remotely by Neocortex. So, connect:
			neocortex   = cortex.core.neocortex_connect()

			# Allocate the name
			new_systems = neocortex.allocate_name(class_name, system_comment, username=session['username'], num=system_number)
		except Exception as ex:
			flash("A fatal error occured when trying to allocate names: " + str(ex), "alert-danger")
			return redirect(url_for('systems_new'))

		# If the user only wanted one system, redirect back to the systems
		# list page and flash up success. If they requested more than one
		# system, then redirect to a bulk-comments-edit page where they can
		# change the comments on all of the systems.
		if len(new_systems) == 1:
			flash("System name allocated successfully", "alert-success")
			return redirect(url_for('systems'))
		else:
			return render_template('systems-new-bulk.html', systems=new_systems, comment=system_comment)

################################################################################

@app.route('/systems/bulk', methods=['POST'])
@cortex.core.login_required
def systems_bulk():
	"""This is a POST handler used to set comments for a series of existing 
	systems which have been allocated already"""

	## Find a list of systems from the form. Each of the form input elements
	## containing a system comment has a name that starts "system_comment_"
	for key, value in request.form.iteritems():
		 if key.startswith("system_comment_"):
			## yay we found one! blindly update it!
			updateid = key.replace("system_comment_", "")
			cur = g.db.cursor()
			cur.execute("UPDATE `systems` SET `allocation_comment` = %s WHERE `id` = %s", (request.form[key], updateid))

	g.db.commit()

	flash("Comments successfully updated", "alert-success")
	return(redirect(url_for("systems")))

################################################################################

@app.route('/systems/edit/<int:id>', methods=['GET', 'POST'])
@cortex.core.login_required
def systems_edit(id):
	if request.method == 'GET' or request.method == 'HEAD':
		# Get the system out of the database
		system = cortex.core.get_system_by_id(id)

		return render_template('systems-edit.html', system=system, active='systems')
	elif request.method == 'POST':
		try:
			# Get a cursor to the database
			cur = g.db.cursor(mysql.cursors.DictCursor)

			# Update the system
			cur.execute('UPDATE `systems` SET `allocation_comment` = %s, `cmdb_id` = %s WHERE `id` = %s', (request.form['allocation_comment'], request.form['cmdb_id'], id))
			g.db.commit();

			flash('System updated', "alert-success") 
		except Exception as ex:
			# On error, notify the user
			flash('Failed to update system: ' + str(ex), 'alert-danger')

		# Regardless of success or error, redirect to the systems page
		return redirect(url_for('systems'))
	else:
		abort(400)

################################################################################

@app.route('/systems/puppet-enc/<int:id>', methods=['GET', 'POST'])
@cortex.core.login_required
def systems_puppet_enc(id):
	# Get the system out of the database
	system = cortex.core.get_system_by_id(id)
	environments = cortex.core.get_puppet_environments()

	# If we've got a new node, then don't show "None"
	if system['puppet_classes'] is None:
		system['puppet_classes'] = "# Global variables to include can be entered here"
	if system['puppet_variables'] is None:
		system['puppet_variables'] = "# Classes to include can be entered here"
	if system['puppet_certname'] is None:
		system['puppet_certname'] = ""

	# On any GET request, just display the information
	if request.method == 'GET':
		return render_template('systems-puppet-enc.html', system=system, active='systems', environments=environments)

	# On any POST request, validate the input and then save
	elif request.method == 'POST':
		# Extract data from form
		certname = request.form.get('certname', '')
		environment = request.form.get('environment', '')
		classes = request.form.get('classes', '')
		variables = request.form.get('variables', '')
		if 'include_default' in request.form:
			include_default = True
		else:
			include_default = False
		error = False

		# Validate certificate name
		if len(certname.strip()) == 0:
			flash('Invalid certificate name', 'alert-danger')
			error = True

		# Validate environement:
		if environment not in [e['name'] for e in environments]:
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
			system['puppet_certname'] = certname
			system['puppet_env'] = environment
			system['puppet_classes'] = classes
			system['puppet_variables'] = variables
			system['puppet_include_default'] = include_default
			return render_template('systems-puppet-enc.html', system=system, active='systems', environments=environments)

		# Get a cursor to the database
		cur = g.db.cursor(mysql.cursors.DictCursor)

		# Update the system
		cur.execute('UPDATE `puppet_nodes` SET `certname` = %s, `env` = %s, `classes` = %s, `variables` = %s, `include_default` = %s WHERE `id` = %s', (certname, environment, classes, variables, include_default, id))
		g.db.commit();

		# Redirect back to the systems page
		flash('Puppet ENC for host ' + system['name'] + ' updated', 'alert-success')

		return redirect(url_for('systems'))

################################################################################

@app.route('/systems/cmdb/json')
@cortex.core.login_required
def systems_cmdb_json():
	"""Used by DataTables to extract information from the ServiceNow CMDB CI
	cache. The parameters and return format are as dictated by DataTables"""

	# Validate and extract 'draw' parameter. This parameter is simply a counter
	# that DataTables uses internally.
	if 'draw' in request.args:
		draw = int(request.args['draw'])
	else:   
		abort(400)

	# Validate and extract 'start' parameter. This parameter is the index of the
	# first row to return.
	if 'start' in request.args:
		start = int(request.args['start'])
	else:   
		abort(400)

	# Validate and extract 'length' parameter. This parameter is the number of
	# rows that we should return
	if 'length' in request.args:
		length = int(request.args['length'])
		if length < 0:
			length = None
	else:   
		abort(400)

	# Handle the search parameter. This is the textbox on the DataTables
	# view that the user can search by typing in
	search = None
	if 'search[value]' in request.args:
		if request.args['search[value]'] != '':
			search = str(request.args['search[value]'])

	# Get results of query
	total_count = cortex.core.get_cmdb_ci_count()
	filtered_count = cortex.core.get_cmdb_ci_count(search)
	results = cortex.core.get_cmdb_cis(start, length, search)

	system_data = []
	for row in results:
		system_data.append([row['u_number'], row['name'], row['sys_id']])

	# Return JSON data in the format DataTables wants
	return jsonify(draw=draw, recordsTotal=total_count, recordsFiltered=filtered_count, data=system_data)

################################################################################

@app.route('/systems/json')
@cortex.core.login_required
def systems_json():
	"""Used by DataTables to extract information from the systems table in
	the database. The parameters and return format are as dictated by 
	DataTables"""

	# Validate and extract 'draw' parameter. This parameter is simply a counter
	# that DataTables uses internally.
	if 'draw' in request.args:
		draw = int(request.args['draw'])
	else:   
		abort(400)

	# Validate and extract 'start' parameter. This parameter is the index of the
	# first row to return.
	if 'start' in request.args:
		start = int(request.args['start'])
	else:   
		abort(400)

	# Validate and extract 'length' parameter. This parameter is the number of
	# rows that we should return
	if 'length' in request.args:
		length = int(request.args['length'])
		if length < 0:
			length = None
	else:   
		abort(400)

	# Validate and extract ordering column. This parameter is the index of the
	# column on the HTML table to order by
	if 'order[0][column]' in request.args:
		print "order[0][column] = " + request.args['order[0][column]']
		order_column = int(request.args['order[0][column]'])
	else:   
		order_column = 0

	# Validate and extract ordering direction. 'asc' for ascending, 'desc' for
	# descending.
	if 'order[0][dir]' in request.args:
		print "order[0][dir] = " + request.args['order[0][dir]']
		if request.args['order[0][dir]'] == 'asc':
			order_asc = True
		elif request.args['order[0][dir]'] == 'desc':
			order_asc = False
		else:
			abort(400)
	else:
		order_asc = False

	# Validate and convert the ordering column number to the name of the
	# column as it is in the database
	if order_column == 0:
		order_column = 'name'
	elif order_column == 1:
		order_column = 'allocation_comment'
	elif order_column == 2:
		order_column = 'allocation_who'
	elif order_column == 3:
		order_column = 'allocation_date'
	elif order_column == 4:
		order_column = 'cmdb_operational_status'
	else:
		abort(400)

	# Validate the system class filter group. This is the name of the
	# currently selected tab on the page that narrows down by system
	# class, e.g .srv, vhost, etc.
	filter_group = None
	if 'filter_group' in request.args:
		if request.args['filter_group'] != '':
			filter_group = str(request.args['filter_group'])

	# Validate the flag for showing decommissioned systems.
	show_decom = True
	if 'show_decom' in request.args:
		if str(request.args['show_decom']) == '0':
			show_decom = False

	# Handle the search parameter. This is the textbox on the DataTables
	# view that the user can search by typing in
	search = None
	if 'search[value]' in request.args:
		if request.args['search[value]'] != '':
			search = str(request.args['search[value]'])

	# Get number of systems that match the query, and the number of systems
	# within the filter group
	system_count = cortex.core.get_system_count(filter_group, show_decom=show_decom)
	filtered_count = cortex.core.get_system_count(filter_group, search, show_decom)

	# Get results of query
	results = cortex.core.get_systems(filter_group, search, order_column, order_asc, start, length, show_decom)

	# DataTables wants an array in JSON, so we build this here, returning
	# only the columns we want. We format the date as a string as
	# datetime.datetime are not JSON-serialisable. We also add on columns for
	# CMDB ID and database ID, and operational status which are not displayed 
	# verbatim, but can be processed by a DataTables rowCallback
	system_data = []
	for row in results:
		if row['cmdb_id'] is not None and row['cmdb_id'] is not '':
			cmdb_id = app.config['CMDB_URL_FORMAT'] % row['cmdb_id']
		else:
			cmdb_id = ''
		system_data.append([row['name'], row['allocation_comment'], row['allocation_who'], row['allocation_date'].strftime('%Y-%m-%d %H:%M:%S'), row['cmdb_operational_status'], cmdb_id, row['id'], row['vmware_guest_state'], row['puppet_certname']])

	# Return JSON data in the format DataTables wants
	return jsonify(draw=draw, recordsTotal=system_count, recordsFiltered=filtered_count, data=system_data)

