#!/usr/bin/python

from cortex import app
import MySQLdb as mysql
from flask import Flask, request, redirect, session, url_for, abort, render_template, flash, g
import io, csv
from cortex.corpus import Corpus
import cortex.lib.user

REVIEW_STATUS_BY_NAME = {'NONE': 0, 'REQUIRED': 1, 'REVIEW': 2, 'NOT_REQUIRED': 3}
REVIEW_STATUS_BY_ID   = {0: 'Not reviewed', 1: 'Required', 2: 'Under review', 3: 'Not required' }

################################################################################

def csv_stream(cursor):
	"""Streams a CSV response of systems data from the database using the
	given cursor"""

	# Get the first row
	row = cursor.fetchone()

	# Write CSV header
	output = io.BytesIO()
	writer = csv.writer(output)
	writer.writerow([
		'ID', 'Type', 'Class', 'Number', 'Name', 'Allocation Date', 'Expiry Date', 'Decom Date', 'Allocation Who', 'Allocation Who Realname', 'Allocation Comment',
		'Review Status', 'Review Task', 'Cmdb Id', 'Build Count', 'Primary Owner Who', 'Primary Owner Role', 'Primary Owner Who Realname', 'Secondary Owner Who',
		'Secondary Owner Role', 'Secondary Owner Who Realname', 'Cmdb Sys Class Name', 'Cmdb Name', 'Cmdb Operational Status', 'Cmdb U Number', 'Cmdb Environment',
		'Cmdb Description', 'Cmdb Comments', 'Cmdb Os', 'Cmdb Short Description', 'Cmdb Is Virtual', 'Vmware Name', 'Vmware Vcenter', 'Vmware Uuid', 'Vmware Cpus',
		'Vmware Ram', 'Vmware Guest State', 'Vmware Os', 'Vmware Hwversion', 'Vmware Ipaddr', 'Vmware Tools Version Status', 'Vmware Hostname', 'Puppet Certname',
		'Puppet Env', 'Puppet Include Default', 'Puppet Classes', 'Puppet Variables'
	])
	yield output.getvalue()

	# Write data
	while row is not None:
		# There's no way to flush (and empty) a CSV writer, so we create
		# a new one each time
		output = io.BytesIO()
		writer = csv.writer(output)

		# Generate link to CMDB
		cmdb_url = ""
		if row['cmdb_id'] is not None and row['cmdb_id'] != "":
			cmdb_url = app.config['CMDB_URL_FORMAT'] % row['cmdb_id']

		# Write a row to the CSV output
		outrow = [row['id'], row['type'], row['class'], row['number'], row['name'], row['allocation_date'], row['expiry_date'], row['decom_date'], row['allocation_who'], row['allocation_who_realname'], row['allocation_comment'], row['review_status'], row['review_task'], row['cmdb_id'], row['build_count'], row['primary_owner_who'], row['primary_owner_role'], row['primary_owner_who_realname'], row['secondary_owner_who'], row['secondary_owner_role'], row['secondary_owner_who_realname'], row['cmdb_sys_class_name'], row['cmdb_name'], row['cmdb_operational_status'], row['cmdb_u_number'], row['cmdb_environment'], row['cmdb_description'], row['cmdb_comments'], row['cmdb_os'], row['cmdb_short_description'], row['cmdb_is_virtual'], row['vmware_name'], row['vmware_vcenter'], row['vmware_uuid'], row['vmware_cpus'], row['vmware_ram'], row['vmware_guest_state'], row['vmware_os'], row['vmware_hwversion'], row['vmware_ipaddr'], row['vmware_tools_version_status'], row['vmware_hostname'], row['puppet_certname'], row['puppet_env'], row['puppet_include_default'], row['puppet_classes'], row['puppet_variables']]

		# For each element in the output row...
		for i in range(0, len(outrow)):
			# ...if it's not None...
			if outrow[i]:
				# ...if the element is unicode...
				if type(outrow[i]) == unicode:
					# ...decode from utf-8 into a ASCII-compatible byte string
					outrow[i] = outrow[i].encode('utf-8')
				else:
					# ...otherwise just chuck it out as a string
					outrow[i] = str(outrow[i])

		# Write the output row to the stream
		writer.writerow(outrow)
		yield output.getvalue()

		# Iterate
		row = cursor.fetchone()

################################################################################

def get_system_count(class_name = None, search = None, hide_inactive = True, only_other = False, show_expired = False, show_nocmdb = False, show_perms_only = False, show_allocated_and_perms = False, only_allocated_by = None, show_favourites_for = None, virtual_only = False, toggle_queries=False):
	"""Returns the number of systems in the database, optionally restricted to those of a certain class (e.g. srv, vhost)"""

	## BUILD THE QUERY

	# Start with no parameters, and a generic SELECT COUNT(*) from the appropriate table
	params = ()
	query = 'SELECT COUNT(*) AS `count` FROM `systems_info_view` '

	# Build the WHERE clause. This returns a tuple of (where_clause, query_params)
	query_where = _build_systems_query(class_name, search, None, None, None, None, hide_inactive, only_other, show_expired, show_nocmdb, show_perms_only, show_allocated_and_perms, only_allocated_by, show_favourites_for, virtual_only, toggle_queries)
	query = query + query_where[0]
	params = params + query_where[1]

	# Query the database
	curd = g.db.cursor(mysql.cursors.DictCursor)
	try:
		curd.execute(query, params)

		# Get the results
		row = curd.fetchone()

		# Return the count
		return row['count']
	except:
		# If error occurs, it's because of the incorrect syntax of the query;
		# Therefore, no data is being returned anyway so just return 0
		return 0

################################################################################

def get_system_by_id(id):
	"""Gets all the information about a system by its database ID."""

	corpus = Corpus(g.db, app.config)
	return corpus.get_system_by_id(id)

################################################################################

def get_system_by_name(name, must_have_vmware_uuid=False, must_have_snow_sys_id=False):
	"""Gets all the information about a system by its hostname."""

	corpus = Corpus(g.db, app.config)
	return corpus.get_system_by_name(name, must_have_vmware_uuid, must_have_snow_sys_id)

################################################################################

def get_system_by_puppet_certname(name):
	"""Gets all the information about a system by its Puppet certificate 
	name."""

	# Query the database
	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute("SELECT * FROM `systems_info_view` WHERE `puppet_certname` = %s", (name,))

	# Return the result
	return curd.fetchone()

################################################################################

def get_system_by_vmware_uuid(name):
	"""Gets all the information about a system by its VMware UUID."""

	# Query the database
	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute("SELECT * FROM `systems_info_view` WHERE `vmware_uuid` = %s", (name,))

	# Return the result
	return curd.fetchone()

################################################################################

def search_is_valid(search):
	# This regex pretty much matches the syntax of the WHERE clause
	# Doesn't fully prevent SQL injection, the \w* regex is quite flexible -> maybe replace it with the column names specifically?
	regex = '(`\w*`\s*(<|>|=|!=|LIKE|NOT LIKE|<=|>=)\s*(((\'|\")\w*(\'|\"))|[0-9]*))(\s*(AND|OR)\s*(`\w*`\s*(<|>|=|!=|LIKE|NOT LIKE|<=|>=)\s*(((\'|\")\w*(\'|\"))|[0-9]*)))*'

	# test the search string against the regex and return either True or False depending on the result

################################################################################
def _build_systems_query(class_name = None, search = None, order = None, order_asc = True, limit_start = None, limit_length = None, hide_inactive = True, only_other = False, show_expired = False, show_nocmdb = False, show_perms_only = False, show_allocated_and_perms = False, only_allocated_by = None, show_favourites_for = None, virtual_only = False, toggle_queries = False):
	params = ()
	query = ""

	# If a class_name is specfied, add on a WHERE clause
	if class_name is not None:
                query = query + "WHERE `class` = %s"
                params = (class_name,)

	if toggle_queries and search is not None and search is not "": # and search_is_valid(search):
		if class_name is not None:
               		query = query + " AND "
                else:   
               	        query = query + "WHERE "
		query = query + search
	else:
		# If a search term is specified...
		if search is not None:
			# Build a filter string
			# escape wildcards
			search = search.replace('%', '\%').replace('_', '\_')
			like_string = '%' + search + '%'

			# If a class name was specified already, we need to AND the query,
			# otherwise we need to start the WHERE clause
			if class_name is not None:
				query = query + " AND "
			else:
				query = query + "WHERE "

			# Allow the search to match on name, allocation_comment or 
			# allocation_who
			query = query + "(`name` LIKE %s OR `allocation_comment` LIKE %s OR `allocation_who` LIKE %s OR `cmdb_environment` LIKE %s OR `allocation_who_realname` LIKE %s OR `vmware_ipaddr` LIKE %s)"

			# Add the filter string to the parameters of the query. Add it 
			# three times as there are three columns to match on.
			params = params + (like_string, like_string, like_string, like_string, like_string, like_string)

	# If hide_inactive is set to false, then exclude systems that are no longer In Service
	if hide_inactive == True:
		if class_name is not None or search is not None:
			query = query + " AND "
		else:
			query = query + "WHERE "

		query = query + ' ((`cmdb_id` IS NOT NULL AND `cmdb_operational_status` = "In Service") OR `vmware_uuid` IS NOT NULL)'

	# Restrict to other/legacy types
	if only_other:
		if class_name is not None or search is not None or hide_inactive == True:
			query = query + " AND "
		else:
			query = query + "WHERE "
		query = query + ' `type` != 0'

	if show_expired:
		if class_name is not None or search is not None or hide_inactive == True or only_other:
			query = query + " AND "
		else:
			query = query + "WHERE "
		query = query + ' (`expiry_date` < NOW())'

	if show_nocmdb:
		if class_name is not None or search is not None or hide_inactive == True or only_other or show_expired:
			query = query + " AND "
		else:
			query = query + "WHERE "
		query = query + ' (`cmdb_id` IS NULL AND `vmware_uuid` IS NOT NULL)'

	if show_perms_only:
		if class_name is not None or search is not None or hide_inactive == True or only_other or show_expired or show_nocmdb:
			query = query + " AND "
		else:
			query = query + "WHERE "
		query = query + ' `id` IN (SELECT DISTINCT `system_id` FROM `system_perms_view`)'
	
	if show_allocated_and_perms:
		if class_name is not None or search is not None or hide_inactive == True or only_other or show_expired or show_nocmdb or show_perms_only:
			query = query + " AND "
		else:
			query = query + "WHERE "

		query = query + "((`id` IN (SELECT `system_id` FROM `system_perms_view` WHERE (`type` = '0' AND `who` = %s AND (`perm` = 'view' OR `perm` = 'view.overview' OR `perm` = 'view.detail')) OR (`type` = '1' AND (`perm` = 'view' OR `perm` = 'view.overview' OR `perm` = 'view.detail') AND `who` IN (SELECT `group` FROM `ldap_group_cache` WHERE `username` = %s)))) OR `allocation_who`=%s)"
		params = params + (only_allocated_by, only_allocated_by, only_allocated_by)

		# Ignore the only_allocated_by.
		only_allocated_by = None

	if only_allocated_by:
		if class_name is not None or search is not None or hide_inactive == True or only_other or show_expired or show_nocmdb or show_perms_only or show_allocated_and_perms:
			query = query + " AND "
		else:
			query = query + "WHERE "
		query = query + ' `allocation_who`=%s'
		params = params + (only_allocated_by,)

	if show_favourites_for:
		if class_name is not None or search is not None or hide_inactive == True or only_other or show_expired or show_nocmdb or show_perms_only or show_allocated_and_perms or only_allocated_by:
			query = query + " AND "
		else:
			query = query + "WHERE "
		query = query + " `id` IN (SELECT `system_id` FROM `system_user_favourites` WHERE `username`=%s)"
		params = params + (show_favourites_for,)

	if virtual_only:
		if class_name is not None or search is not None or hide_inactive == True or only_other or show_expired or show_nocmdb or show_perms_only or show_allocated_and_perms or only_allocated_by or virtual_only:
			query = query + " AND "
		else:
			query = query + "WHERE "
		query = query + " `vmware_uuid` IS NOT NULL"


	# Handle the ordering of the rows
	query = query + " ORDER BY ";

	# By default, if order is not specified, we order by name
	if order is None:
		query = query + "`name`"

	# Validate the name of the column to sort by (this prevents errors and
	# also prevents SQL from accidentally being injected). Add the column
	# name on to the query
	if order in ["id", "name", "number", "allocation_comment", "allocation_date", "allocation_who", 'cmdb_operational_status', 'cmdb_environment']:
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

def get_systems(class_name = None, search = None, order = None, order_asc = True, limit_start = None, limit_length = None, hide_inactive = True, only_other = False, show_expired = False, show_nocmdb = False, show_perms_only = False, return_cursor = False, show_allocated_and_perms=False, only_allocated_by = None, show_favourites_for = None, virtual_only = False, toggle_queries = False):
	"""Returns the list of systems in the database, optionally restricted to those of a certain class (e.g. srv, vhost), and ordered (defaults to "name")"""

	## BUILD THE QUERY

	# Start with no parameters, and a generic SELECT from the appropriate table
	params = ()
	query = "SELECT * FROM `systems_info_view` "

	# Build the WHERE clause. This returns a tuple of (where_clause, query_params)
	query_where = _build_systems_query(class_name, search, order, order_asc, limit_start, limit_length, hide_inactive, only_other, show_expired, show_nocmdb, show_perms_only, show_allocated_and_perms, only_allocated_by, show_favourites_for, virtual_only, toggle_queries)
	query       = query + query_where[0]
	params      = params + query_where[1]

	# Query the database
	curd = g.db.cursor(mysql.cursors.DictCursor)
	try:
		curd.execute(query, params)
		
		# Return the results
		if return_cursor:
			return curd
		else:
			return curd.fetchall()
	except:
		# If an error occurs, it's because of the incorrect syntax of the WHERE clause
		# Therefore, return nothing
		if return_cursor:
			return curd
		else:
			return None

################################################################################

def get_system_favourites(username):
	query = 'SELECT `system_id` FROM `system_user_favourites` WHERE `username`=%s'
	params = (username,)
	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute(query, params)
	results = curd.fetchall()
	return [result['system_id'] for result in results]


################################################################################

def get_vm_by_system_id(id):
	query = 'SELECT `vmware_uuid`, `vmware_vcenter` FROM `systems_info_view` WHERE `id`=%s AND `vmware_uuid` IS NOT NULL'
	params = (id,)
	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute(query, params)
	row = curd.fetchone()
	if row is None:
		raise ValueError
	corpus = Corpus(g.db, app.config)
	return corpus.vmware_get_vm_by_uuid(row['vmware_uuid'], row['vmware_vcenter'])

################################################################################

def power_on(id):
	vm = get_vm_by_system_id(id)
	return vm.PowerOn()

################################################################################

def shutdown(id):
	vm = get_vm_by_system_id(id)
	return vm.ShutdownGuest()

################################################################################

def power_off(id):
	vm = get_vm_by_system_id(id)
	return vm.PowerOff()

################################################################################

def reset(id):
	vm = get_vm_by_system_id(id)
	return vm.Reset()

################################################################################

def increment_build_count(id):
	# Increment the build count
	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute('UPDATE `systems` SET `build_count` = `build_count` + 1 WHERE `id` = %s', (id,))
	g.db.commit()

################################################################################

def generate_repeatable_password(id):
	corpus = Corpus(g.db, app.config)
	return corpus.system_get_repeatable_password(id)

################################################################################

def generate_pretty_display_name(who, who_realname):
	if who is not None and len(who) > 0:
		if who_realname is not None:
			return '{0} ({1})'.format(who_realname, who)
		else:
			return '{0} ({1})'.format(cortex.lib.user.get_user_realname(who), who)
	else:
		# If we weren't given a 'who' return None.
		return None
		
