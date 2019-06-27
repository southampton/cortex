#!/usr/bin/python

from cortex import app
import cortex.lib.core
from cortex.corpus import Corpus
import MySQLdb as mysql
from flask import Flask, request, redirect, session, url_for, abort, render_template, flash, g

################################################################################

def get_requests(status = None, user = None, search = None, order = None, order_asc = True, limit_start = None, limit_length = None):
	"""Returns the list of systems in the database, optionally restricted to those of a certain class (e.g. srv, vhost), and ordered (defaults to "name")"""

	## BUILD THE QUERY

	# Start with no parameters, and a generic SELECT from the appropriate table
	params = ()
	query = "SELECT * FROM `system_request` "

	# Build the WHERE clause. This returns a tuple of (where_clause, query_params)
	query_where = _build_requests_query(status, user, search, order, order_asc, limit_start, limit_length)
	query       = query + query_where[0]
	params      = params + query_where[1]

	# Query the database
	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute(query, params)

	# Return the results
	return curd.fetchall()

################################################################################

def get_request_count(status = None, user = None, search = None):
	"""Returns the number of reqeusts in the database, optionally restricted to those of a certain status or user"""

	## BUILD THE QUERY

	# Start with no parameters, and a generic SELECT COUNT(*) from the /ppropriate table
	params = ()
	query = 'SELECT COUNT(*) AS `count` FROM `system_request` '

	# Build the WHERE clause. This returns a tuple of (where_clause, query_params)
	query_where = _build_requests_query(status, user, search, None, None, None, None)
	query = query + query_where[0]
	params = params + query_where[1]

	# Query the database
	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute(query, params)

	# Get the results
	row = curd.fetchone()

	# Return the count
	return row['count']

################################################################################

def _build_requests_query(status = None, user = None, search = None, order = None, order_asc = True, limit_start = None, limit_length = None):
	params = ()

	query = ""

	# If a status is specfied, add on a WHERE clause
	if status is not None:
		query = query + "WHERE `status` = %s"
		params = (status,)
	if user is not None:
		if status is not None:
			query = query + " AND "
		else:
			query = query + "WHERE "
		query = query + "`requested_who` = %s"
		params = params + (user,)

	# If a search term is specified...
	if search is not None:
		# Build a filter string
		# escape wildcards
		search = search.replace('%', '\%').replace('_', '\_')
		like_string = '%' + search + '%'

		# If a class name was specified already, we need to AND the query,
		# otherwise we need to start the WHERE clause
		if status is not None or user is not None:
			query = query + " AND "
		else:
			query = query + "WHERE "

		# Allow the search to match on name, allocation_comment or 
		# allocation_who
		query = query + "(`requested_who` LIKE %s OR `purpose` LIKE %s)"

		# Add the filter string to the parameters of the query. Add it 
		# three times as there are three columns to match on.
		params = params + (like_string, like_string)

	# Handle the ordering of the rows
	query = query + " ORDER BY ";

	# By default, if order is not specified, we order by name
	if order is None:
		query = query + "`request_date`"

	# Validate the name of the column to sort by (this prevents errors and
	# also prevents SQL from accidentally being injected). Add the column
	# name on to the query
	if order in ["status", "requested_who", "purpose", "request_date"]:
		query = query + "`" + order + "`"

	# Determine which direction to order in, and add that on
	if order_asc:
		query = query + " ASC"
	else:
		query = query + " DESC"

	# If a limit is specified, we need to add that on
	if limit_start is not None or limit_length is not None:
		query = query + " LIMIT "
		if limit_start is not None:
			# Start is specified (which syntactically means length 
			# must also be specified)
			query = query + str(int(limit_start)) + ","
		if limit_length is not None:
			# Add on the number of rows to return
			query = query + str(int(limit_length))
		else:
			# We must always specify how many rows to return in SQL.
			# If we want them all, but have specified a limit_start,
			# we have to request as many rows as possible.
			#
			# Seriously, this is how MySQL recommends to do this :'(
			query = query + "18446744073709551610"

	return (query, params)

################################################################################

def get_request_by_id(id):
	"""Gets all the information about a system by its database ID."""

	# Query the database
	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute("SELECT * FROM `system_request` WHERE `id` = %s", (id,))

	# Return the result
	return curd.fetchone()

################################################################################

def approve(id, status_text=None):
	"""Approves and triggers the build of a system"""
	sysrequest = get_request_by_id(id)

	#check if system is already approved
	if sysrequest['status'] == 2:
		raise Exception('Request already approved')



	#load options from request
	stmt = ('SELECT `workflow`, '
					'`hostname`, '
				    '`sockets`, '
				    '`cores`, '
				    '`ram`, '
			     	'`disk`, '
					'`template`, '
					'`network`, '
					'`cluster`, '
					'`environment`, '
					'`purpose`, '
					'`comments`, '
					'`expiry_date`, '
					'`sendmail` '
			  		'FROM `system_request` '
			  		'WHERE `id`=%s')
	params = (id,)
	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute(stmt, params)
	results = curd.fetchall()[0]

	options = {}
	options['workflow'] = results['workflow']
	options['sockets'] = results['sockets']
	options['cores'] = results['cores']
	options['ram'] = results['ram']
	options['disk'] = results['disk']
	options['template'] = results['template']
	options['network'] = results['network']
	options['cluster'] = results['cluster']
	options['env'] = results['environment']
	options['hostname'] = results['hostname']
	options['purpose'] = results['purpose']
	options['comments'] = results['comments']
	options['expiry'] = results['expiry_date']
	options['sendmail'] = results['sendmail']

	#trigger build

	options['wfconfig'] = app.workflows.get('buildvm').config

	# Connect to NeoCortex and start the task
	neocortex = cortex.lib.core.neocortex_connect()
	task_id = neocortex.create_task('buildvm', session['username'], options, description="Creates and configures a virtual machine")


	#update db
	stmt = 'UPDATE `system_request` SET `status`=2, `updated_at`=NOW(), `updated_who`=%s, `status_text`=%s WHERE `id`=%s'
	params = (session['username'], status_text, id)

	curd.execute(stmt, params)
	g.db.commit()

	#email requester
	subject = 'System request approved'
	message = ('Your request for a system has been approved.\n' +
		   '\n' +
		   'Request id: ' + str(sysrequest['id']) + '\n' +
		   'Requested at: ' + str(sysrequest['request_date']) + '\n' +
		   'Reason: ' + str(status_text) + '\n' +
		   '\n' +
		   'For more details see https://cortex.soton.ac.uk/sysrequest/view/' + str(sysrequest['id']))
	corpus = Corpus(g.db, app.config)
	corpus.send_email(str(sysrequest['requested_who']), subject, message)

	return redirect(url_for('task_status', id=task_id))
	#return redirect(url_for('dashboard'))


################################################################################

def reject(id, status_text=None):
	"""Rejects a request"""
	sysrequest = get_request_by_id(id)
	
	#check if system is already approved
	if sysrequest['status'] == 2:
		raise Exception('Request already approved')
	elif sysrequest['status'] == 1:
		raise Exception('Request already rejected')

	stmt = 'UPDATE `system_request` SET `status`=1, `updated_at`=NOW(), `updated_who`=%s, `status_text`=%s WHERE `id`=%s'
	params = (session['username'], status_text, id)

	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute(stmt,params)
	g.db.commit()
	flash('Request has been rejected', 'alert-info')

	#email requester
	subject = 'System request rejected'
	message = ('Your request for a system has been rejected.\n' +
		   '\n' +
		   'Request id: ' + str(sysrequest['id']) + '\n' +
		   'Requested at: ' + str(sysrequest['request_date']) + '\n' +
		   'Reason: ' + str(status_text) + '\n' +
		   '\n' +
		   'For more details see https://cortex.soton.ac.uk/sysrequest/view/' + str(sysrequest['id']))
	corpus = Corpus(g.db, app.config)
	corpus.send_email(str(sysrequest['requested_who']), subject, message)
