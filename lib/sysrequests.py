#!/usr/bin/python

from cortex import app
import MySQLdb as mysql
from flask import Flask, request, redirect, session, url_for, abort, render_template, flash, g

################################################################################

def get_requests(status = None, search = None, order = None, order_asc = True, limit_start = None, limit_length = None):
	"""Returns the list of systems in the database, optionally restricted to those of a certain class (e.g. srv, vhost), and ordered (defaults to "name")"""

	## BUILD THE QUERY

	# Start with no parameters, and a generic SELECT from the appropriate table
	params = ()
	query = "SELECT * FROM `system_request` "

	# Build the WHERE clause. This returns a tuple of (where_clause, query_params)
	query_where = _build_requests_query(status, search, order, order_asc, limit_start, limit_length)
	query       = query + query_where[0]
	params      = params + query_where[1]

	# Query the database
	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute(query, params)

	# Return the results
	return curd.fetchall()

################################################################################

def get_request_count(status = None, search = None):
	"""Returns the number of systems in the database, optionally restricted to those of a certain class (e.g. srv, vhost)"""

	## BUILD THE QUERY

	# Start with no parameters, and a generic SELECT COUNT(*) from the appropriate table
	params = ()
	query = 'SELECT COUNT(*) AS `count` FROM `system_request` '

	# Build the WHERE clause. This returns a tuple of (where_clause, query_params)
	query_where = _build_requests_query(status, search, None, None, None, None)
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

def _build_requests_query(status = None, search = None, order = None, order_asc = True, limit_start = None, limit_length = None):
	params = ()

	query = ""

	# If a status is specfied, add on a WHERE clause
	if status is not None:
		query = query + "WHERE `status` = %s"
		params = (status,)

	# If a search term is specified...
	if search is not None:
		# Build a filter string
		like_string = '%' + search + '%'

		# If a class name was specified already, we need to AND the query,
		# otherwise we need to start the WHERE clause
		if status is not None:
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

def approve(id):
	"""Approves and triggers the build of a system"""
	sysrequest = get_request_by_id(id)
	
	#check if system is already approved
	if sysrequest['status'] == 2:
		raise Exception('Request already approved')

	stmt = 'UPDATE `system_request` SET `status`=2 WHERE `id`=%s'
	params = (id,)

	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute(stmt,params)
	g.db.commit()
	#trigger build HERE

################################################################################

def reject(id):
	"""Rejects a request"""
	sysrequest = get_request_by_id(id)
	
	#check if system is already approved
	if sysrequest['status'] == 2:
		raise Exception('Request already approved')
	elif sysrequest['status'] == 1:
		raise Exception('Request already rejected')

	stmt = 'UPDATE `system_request` SET `status`=1 WHERE `id`=%s'
	params = (id,)

	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute(stmt,params)
	g.db.commit()
	#email requester?
