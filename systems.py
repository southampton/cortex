#!/usr/bin/python
#

from cortex import app, admin
import cortex.lib.core
import cortex.lib.systems
import cortex.lib.cmdb
import cortex.lib.classes
from flask import Flask, request, session, redirect, url_for, flash, g, abort, make_response, render_template, jsonify, Response
import os 
import time
import json
import re
import werkzeug
import MySQLdb as mysql
import yaml
import csv
import io

################################################################################

@app.route('/systems')
@cortex.lib.user.login_required
def systems():
	"""Shows the list of known systems to the user."""

	# Get the list of systems
	systems = cortex.lib.systems.get_systems()

	# Get the list of active classes (used to populate the tab bar)
	classes = cortex.lib.classes.list(hide_disabled=True)

	# Render
	return render_template('systems.html', systems=systems, classes=classes, active='systems', title="Systems")

################################################################################

# This function streams our CSV response from the data
def systems_csv_stream(cursor):
	# Get the first row
	row = cursor.fetchone()

	# Write header
	output = io.BytesIO()
	writer = csv.writer(output)
	writer.writerow(['Name', 'Comment', 'Allocated by', 'Allocation date', 'CI Operational Status', 'CMDB Link'])
	yield output.getvalue()

	# Write data
	while row is not None:
		output = io.BytesIO()
		writer = csv.writer(output)

		# Generate link to CMDB
		cmdb_url = ""
		if row['cmdb_id'] is not None and row['cmdb_id'] != "":
			cmdb_url = app.config['CMDB_URL_FORMAT'] % row['cmdb_id']

		# Write a row to the CSV output
		writer.writerow([row['name'], row['allocation_comment'], row['allocation_who'], row['allocation_date'], row['cmdb_operational_status'], cmdb_url])
		yield output.getvalue()

		# Iterate
		row = cursor.fetchone()

################################################################################

@app.route('/systems/search')
@cortex.lib.user.login_required
def systems_search():
	# Get the query from the URL
	query = request.args.get('query')
	if query is None:
		return abort(400)

	# Search for the system
	system = cortex.lib.systems.get_system_by_name(query)

	if system is not None:
		# If we found the system, redirect to the system's edit page
		return redirect(url_for('systems_edit', id=system['id']))
	else:
		# If we didn't find the system, flash an error and go to the systems list
		flash('Unable to find system "' + query + '"', 'alert-warning')
		return redirect(url_for('systems'))

################################################################################

@app.route('/systems/download/csv')
@cortex.lib.user.login_required
def systems_download_csv():
	"""Downloads the list of allocated server names as a CSV file."""

	# Get the list of systems
	cur = cortex.lib.systems.get_systems(return_cursor=True)

	# Return the response
	return Response(systems_csv_stream(cur), mimetype="text/csv", headers={'Content-Disposition': 'attachment; filename="systems.csv"'})

################################################################################

@app.route('/systems/new', methods=['GET','POST'])
@cortex.lib.user.login_required
def systems_new():
	"""Handles the Allocate New System Name(s) page"""

	# On GET requests, just show big buttons for all the classes
	if request.method == 'GET':
		classes = cortex.lib.classes.list(hide_disabled=True)
		return render_template('systems-new.html', classes=classes, active='systems', title="Allocate new system names")

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
			neocortex   = cortex.lib.core.neocortex_connect()

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
			return redirect(url_for('systems_edit', id=new_systems[new_systems.keys()[0]]))
		else:
			return render_template('systems-new-bulk.html', systems=new_systems, comment=system_comment, title="Systems")

################################################################################

@app.route('/systems/bulk/save', methods=['POST'])
@cortex.lib.user.login_required
def systems_bulk_save():
	"""This is a POST handler used to set comments for a series of existing 
	systems which have been allocated already"""

	found_keys = []

	## Find a list of systems from the form. Each of the form input elements
	## containing a system comment has a name that starts "system_comment_"
	for key, value in request.form.iteritems():
		 if key.startswith("system_comment_"):
			## yay we found one! blindly update it!
			updateid = key.replace("system_comment_", "")
			found_keys.append(updateid)
			cur = g.db.cursor()
			cur.execute("UPDATE `systems` SET `allocation_comment` = %s WHERE `id` = %s", (request.form[key], updateid))

	g.db.commit()

	flash("Comments successfully updated", "alert-success")
	return(redirect(url_for("systems_bulk_view",start=min(found_keys),finish=max(found_keys))))

################################################################################

@app.route('/systems/bulk/view/<int:start>/<int:finish>', methods=['GET'])
@cortex.lib.user.login_required
def systems_bulk_view(start,finish):
	"""This is a GET handler to view the list of assigned names"""

	start  = int(start)
	finish = int(finish)

	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute("SELECT `id`, `name`, `allocation_comment` AS `comment` FROM `systems` WHERE `id` >= %s AND `id` <= %s",(start,finish))
	systems = curd.fetchall()

	return render_template('systems-new-bulk-done.html', systems=systems, title="Systems")


################################################################################

@app.route('/systems/edit/<int:id>', methods=['GET', 'POST'])
@cortex.lib.user.login_required
def systems_edit(id):
	if request.method == 'GET' or request.method == 'HEAD':
		# Get the system out of the database
		system = cortex.lib.systems.get_system_by_id(id)
		system_class = cortex.lib.classes.get(system['class'])

		return render_template('systems-edit.html', system=system, system_class=system_class, active='systems', title=system['name'])
	elif request.method == 'POST':
		try:
			# Get a cursor to the database
			cur = g.db.cursor(mysql.cursors.DictCursor)

			# Update the system
			cur.execute('UPDATE `systems` SET `allocation_comment` = %s, `cmdb_id` = %s, `vmware_uuid` = %s WHERE `id` = %s', (request.form['allocation_comment'], request.form['cmdb_id'], request.form['vmware_uuid'], id))
			g.db.commit();

			flash('System updated', "alert-success") 
		except Exception as ex:
			# On error, notify the user
			flash('Failed to update system: ' + str(ex), 'alert-danger')

		# Regardless of success or error, redirect to the systems page
		return redirect(url_for('systems_edit', id=id))
	else:
		abort(400)

################################################################################

@app.route('/systems/vmware/json')
@cortex.lib.user.login_required
def systems_vmware_json():
	"""Used by DataTables to extract infromation from the VMware cache. The
	parameters and return format are dictated by DataTables"""

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

	# Validate and extract ordering column. This parameter is the index of the
	# column on the HTML table to order by
	if 'order[0][column]' in request.args:
		order_column = int(request.args['order[0][column]'])
	else:   
		order_column = 0

	# Validate and extract ordering direction. 'asc' for ascending, 'desc' for
	# descending.
	if 'order[0][dir]' in request.args:
		if request.args['order[0][dir]'] == 'asc':
			order_dir = "ASC"
		elif request.args['order[0][dir]'] == 'desc':
			order_dir = "DESC"
		else:
			abort(400)
	else:
		order_dir = "DESC"

	# Validate and convert the ordering column number to the name of the
	# column as it is in the database
	if order_column == 0:
		order_column = 'name'
	elif order_column == 1:
		order_column = 'uuid'
	else:
		abort(400)

	# Query the database
	curd = g.db.cursor(mysql.cursors.DictCursor)

	# Get total number of VMs in cache
	curd.execute('SELECT COUNT(*) AS `count` FROM `vmware_cache_vm`;')
	total_count = curd.fetchone()['count']

	# Get total number of VMs that match query
	if search is not None:
		curd.execute('SELECT COUNT(*) AS `count` FROM `vmware_cache_vm` WHERE `name` LIKE %s', ("%" + search + "%"))
		filtered_count = curd.fetchone()['count']
	else:
		# If unfiltered, return the total count
		filtered_count = total_count

	# Build query	
	query = 'SELECT `name`, `uuid` FROM `vmware_cache_vm` '
	query_params = ()
	if search is not None:
		query = query + 'WHERE `name` LIKE %s '
		query_params = ("%" + search + "%")

	# Add on ordering
	query = query + "ORDER BY " + order_column + " " + order_dir + " "

	# Add on query limits
	query = query + "LIMIT " + str(start)
	if length is not None:
		query = query + "," + str(length)
	else:
		query = query + ",18446744073709551610"

	# Perform the query
	curd.execute(query, query_params)

	# Turn the results in to an appropriately shaped arrau
	row = curd.fetchone()
	system_data = []
	while row is not None:
		system_data.append([row['name'], row['uuid']])
		row = curd.fetchone()

	# Return JSON data in the format DataTables wants
	return jsonify(draw=draw, recordsTotal=total_count, recordsFiltered=filtered_count, data=system_data)


################################################################################

@app.route('/systems/cmdb/json')
@cortex.lib.user.login_required
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

	# Validate and extract ordering column. This parameter is the index of the
	# column on the HTML table to order by
	if 'order[0][column]' in request.args:
		order_column = int(request.args['order[0][column]'])
	else:   
		order_column = 0

	# Validate and extract ordering direction. 'asc' for ascending, 'desc' for
	# descending.
	if 'order[0][dir]' in request.args:
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
		order_column = 'u_number'
	elif order_column == 1:
		order_column = 'short_description'
	else:
		abort(400)

	# Get results of query
	total_count    = cortex.lib.cmdb.get_ci_count()
	filtered_count = cortex.lib.cortex.get_ci_count(search)
	results        = cortex.lib.cmdb.get_cis(start, length, search, order_column, order_asc)

	system_data = []
	for row in results:
		system_data.append([row['u_number'], row['name'], row['sys_id']])

	# Return JSON data in the format DataTables wants
	return jsonify(draw=draw, recordsTotal=total_count, recordsFiltered=filtered_count, data=system_data)

################################################################################

@app.route('/systems/json')
@cortex.lib.user.login_required
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
		order_column = int(request.args['order[0][column]'])
	else:   
		order_column = 0

	# Validate and extract ordering direction. 'asc' for ascending, 'desc' for
	# descending.
	if 'order[0][dir]' in request.args:
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
		# The filtering on starting with * ignores some special filter groups
		if request.args['filter_group'] != '' and request.args['filter_group'][0] != '*':
			filter_group = str(request.args['filter_group'])

	# Filter group being *OTHER should hide our group names and filter on 
	only_other = False
	if request.args['filter_group'] == '*OTHER':
		only_other = True

	# Validate the flag for showing decommissioned systems.
	show_decom = True
	#if 'show_decom' in request.args:
	#	if str(request.args['show_decom']) == '0':
	#		show_decom = False

	# Handle the search parameter. This is the textbox on the DataTables
	# view that the user can search by typing in
	search = None
	if 'search[value]' in request.args:
		if request.args['search[value]'] != '':
			search = str(request.args['search[value]'])

	# Get number of systems that match the query, and the number of systems
	# within the filter group
	system_count = cortex.lib.systems.get_system_count(filter_group, show_decom=show_decom)
	filtered_count = cortex.lib.systems.get_system_count(filter_group, search, show_decom)

	# Get results of query
	results = cortex.lib.systems.get_systems(filter_group, search, order_column, order_asc, start, length, show_decom, only_other)

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

