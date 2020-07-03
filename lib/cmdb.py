
import MySQLdb as mysql
from flask import g

################################################################################

def get_ci_count(search = None):
	"""Returns the number of CMDB CIs in the database, optionally restricted by a search term"""

	## BUILD THE QUERY

	# Start with no parameters, and a generic SELECT COUNT(*) from the appropriate table
	params = ()
	query = 'SELECT COUNT(*) AS `count` FROM `sncache_cmdb_ci` '

	# If a search term is specified...
	if search is not None:
		# Build a filter string
		# escape wildcards
		search = search.replace('%', '\%').replace('_', '\_')
		like_string = '%' + search + '%'

		# Allow the search to match on name or u_number
		query = query + "WHERE (`name` LIKE %s OR `u_number` LIKE %s)"

		# Add the filter string to the parameters of the query. Add it 
		# three times as there are three columns to match on.
		params = (like_string, like_string)

	# Query the database
	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute(query, params)

	# Get the results
	row = curd.fetchone()

	# Return the count
	return row['count']

################################################################################

def get_cis(limit_start = None, limit_length = None, search = None, order_by = "u_number", order_asc = True):
	"""Returns the list of systems from the ServiceNow CMDB CI cache table."""

	## BUILD THE QUERY

	# Start with no parameters, and a generic SELECT from the appropriate table
	params = ()
	query = "SELECT `sys_id`, `sys_class_name`, `name`, `operational_status`, `u_number`, `short_description` FROM `sncache_cmdb_ci` "

	# If a search term is specified...
	if search is not None:
		# Build a filter string
		# escape wildcards
		search = search.replace('%', '\%').replace('_', '\_')
		like_string = '%' + search + '%'

		# Allow the search to match on name, or u_number
		query = query + "WHERE (`name` LIKE %s OR `u_number` LIKE %s)"

		# Add the filter string to the parameters of the query. Add it 
		# three times as there are three columns to match on.
		params = (like_string, like_string)

	# Add on ordering
	if order_by in ['sys_id', 'sys_class_name', 'name', 'operational_status', 'u_number', 'short_description', 'u_environment', 'virtual', 'comments', 'os']:
		query = query + " ORDER BY " + order_by
		if order_asc:
			query = query + " ASC"
		else:
			query = query + " DESC"
	else:
		raise ValueError('order_by is invalid')

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
			# Seriously, this is how MySQL recommends to do this :(
			query = query + "18446744073709551610"

	# Query the database
	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute(query, params)

	# Return the results
	return curd.fetchall()
