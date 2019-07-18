#!/usr/bin/python
#

from cortex import app
import cortex.lib.core
import cortex.lib.sysrequests
import cortex.lib.systems
from cortex.lib.user import does_user_have_permission, does_user_have_system_permission, does_user_have_any_system_permission
from flask import Flask, request, session, redirect, url_for, flash, g, abort, make_response, render_template, jsonify, Response
import json
import MySQLdb as mysql
import requests

################################################################################

@app.route('/requests')
@cortex.lib.user.login_required
def sysrequests():
	"""Shows the list of system requests to the user."""

	# Check user permissions
	if not does_user_have_permission("sysrequests.all.view"):
		abort(403)

	# Get the list of active classes (used to populate the tab bar)
	statuses = ((0, 'Pending'), (1, 'Rejected'), (2, 'Approved'))

	# Get the search string, if any
	q = request.args.get('q', None)

	# Strip any leading and or trailing spaces
	if q is not None:
		q = q.strip()

	# Render
	return render_template('sysrequests/list.html', statuses=statuses, active='systems', title="Requests", q=q)

################################################################################

@app.route('/requests/json', methods=['POST'])
@cortex.lib.user.login_required
@app.disable_csrf_check
def sysrequests_json():
	"""Used by DataTables to extract information from the systems table in
	the database. The parameters and return format are as dictated by 
	DataTables"""

	# Extract information from DataTables
	(draw, start, length, order_column, order_asc, search) = _sysrequests_extract_datatables()

	# Validate and convert the ordering column number to the name of the
	# column as it is in the database
	if order_column == 0:
		order_column = 'status'
	elif order_column == 1:
		order_column = 'requested_who'
	elif order_column == 2:
		order_column = 'purpose'
	elif order_column == 3:
		order_column = 'request_date'
	else:
		app.logger.warn('Invalid ordering column parameter in DataTables request')
		abort(400)

	# Validate the system class filter group. This is the name of the
	# currently selected tab on the page that narrows down by system
	# class, e.g .srv, vhost, etc.
	filter_group = None
	if request.form.get('filter_group', None) in ["0", "1", "2"]:
		filter_group = int(request.form['filter_group'])


	# Get results of query
	# get all the requests if the user has the permission
	if does_user_have_permission("sysrequests.all.view"):
		system_count = cortex.lib.sysrequests.get_request_count(filter_group)
		filtered_count = cortex.lib.sysrequests.get_request_count(filter_group, None, search)
		results = cortex.lib.sysrequests.get_requests(filter_group, None, search, order_column, order_asc, start, length)
	# otherwise only get their own requests
	else:
		system_count = cortex.lib.sysrequests.get_request_count(filter_group, session['username'])
		filtered_count = cortex.lib.sysrequests.get_request_count(filter_group, session['username'], search)
		results = cortex.lib.sysrequests.get_requests(filter_group, session['username'], search, order_column, order_asc, start, length)

	# DataTables wants an array in JSON, so we build this here, returning
	# only the columns we want. We format the date as a string as
	# datetime.datetime are not JSON-serialisable. We also add on columns for
	# CMDB ID and database ID, and operational status which are not displayed 
	# verbatim, but can be processed by a DataTables rowCallback
	requests_data = []
	for row in results:
		if row['request_date'] is not None:
			row['request_date'] = row['request_date'].strftime('%Y-%m-%d %H:%M:%S')
		else:
			row['request_date'] = "unknown"

		if row['requested_who'] is not None:
			row['requested_who'] = cortex.lib.user.get_user_realname(row['requested_who'])

		if row['updated_at'] is not None:
			row['updated_at'] = row['updated_at'].strftime('%Y-%m-%d %H:%M:%S')
		else:
			row['updated_at'] = "unknown"

		if row['updated_who'] is not None:
			row['updated_who'] = cortex.lib.user.get_user_realname(row['updated_who'])

		requests_data.append([row['id'], row['status'], row['requested_who'], row['hostname'], row['request_date'], row['updated_at'], row['updated_who'], row['id']])

	# Return JSON data in the format DataTables wants
	return jsonify(draw=draw, recordsTotal=system_count, recordsFiltered=filtered_count, data=requests_data)

################################################################################

@app.route('/request/view/<int:id>', methods=['GET', 'POST'])
@cortex.lib.user.login_required
def sysrequest(id):

	# Get the system
	sysrequest = cortex.lib.sysrequests.get_request_by_id(id)

	# Ensure that the request actually exists, and return a 404 if it doesn't
	if sysrequest is None:
		abort(404)

	# Check user permissions. User must have either sysrequests.all or own
	# the request
	if sysrequest['requested_who'] != session['username'] and not does_user_have_permission("sysrequests.all.view"):
		abort(403)

	if request.method == 'POST':
		try:
			action = request.form.get('action')
			if len(request.form.get('status_text', '')) > 0:
					status_text = request.form.get('status_text')
			else:
				status_text = None
			if action == 'approve' and does_user_have_permission("sysrequests.all.approve"):
				cortex.lib.sysrequests.approve(id, status_text)
			elif action == 'reject' and does_user_have_permission("sysrequests.all.reject"):
				cortex.lib.sysrequests.reject(id, status_text)
			else:
				raise ValueError('Unexpected action: "' + action + '".')
			# get the updated system
			sysrequest = cortex.lib.sysrequests.get_request_by_id(id)
		except ValueError as e:
			abort(400)

	sysrequest['requested_who'] = cortex.lib.user.get_user_realname(sysrequest['requested_who']) + ' (' + sysrequest['requested_who'] + ')'

	#get action permssions to decide whether or not to show controls
	perms = {'approve': does_user_have_permission("sysrequests.all.approve"), 'reject': does_user_have_permission("sysrequests.all.reject")}

	return render_template('sysrequests/view.html', request=sysrequest, title="Request #" + str(sysrequest['id']), perms=perms)

################################################################################

def _sysrequests_extract_datatables():
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
			if type(request.form['search[value]']) is not str and type(request.form['search[value]']) is not str:
				search = str(request.form['search[value]'])
			else:
				search = request.form['search[value]']

	return (draw, start, length, order_column, order_asc, search)
