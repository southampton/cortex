#!/usr/bin/python

from cortex import app
import cortex.errors
import MySQLdb as mysql
from flask import Flask, request, redirect, session, url_for, abort, render_template, flash, g

################################################################################

def get_system_count(class_name = None, search = None, show_decom = True, only_other = False):
	"""Returns the number of systems in the database, optionally restricted to those of a certain class (e.g. srv, vhost)"""

	## BUILD THE QUERY

	# Start with no parameters, and a generic SELECT COUNT(*) from the appropriate table
	params = ()
	query = 'SELECT COUNT(*) AS `count` FROM `systems` LEFT JOIN `sncache_cmdb_ci` ON `systems`.`cmdb_id` = `sncache_cmdb_ci`.`sys_id`'

	# If a class_name is specfied, add on a WHERE clause
	if class_name is not None:
		query = query + "WHERE `class` = %s"
		params = (class_name,)

	# If a search term is specified...
	if search is not None:
		# Build a filter string
		like_string = '%' + search + '%'

		# If a class name was specified already, we need to AND the query,
		# otherwise we need to start the WHERE clause
		if class_name is not None:
			query = query + " AND "
		else:
			query = query + "WHERE "

		# Allow the search to match on name, allocation_comment or 
		# allocation_who
		query = query + "(`systems`.`name` LIKE %s OR `systems`.`allocation_comment` LIKE %s OR `systems`.`allocation_who` LIKE %s)"

		# Add the filter string to the parameters of the query. Add it 
		# three times as there are three columns to match on.
		params = params + (like_string, like_string, like_string)

	# If show_decom is set to false, then exclude systems that are no longer In Service
	if show_decom == False:
		if class_name is not None or search is not None:
			query = query + " AND "
		else:
			query = query + "WHERE "

		query = query + ' (`sncache_cmdb_ci`.`operational_status` = "In Service" OR `sncache_cmdb_ci`.`operational_status` IS NULL)'

	# Restrict to other/legacy types
	if only_other:
		if class_name is not None or search is not None or show_decom == False:
			query = query + " AND "
		else:
			query = query + "WHERE "
		query = query + ' `systems`.`type` != 0'

	# Query the database
	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute(query, params)

	# Get the results
	row = curd.fetchone()

	# Return the count
	return row['count']


################################################################################

def systems_select_query():
	return "SELECT `systems`.`id` AS `id`, `type`, `class`, `number`, `systems`.`name` AS `name`, `allocation_date`, `allocation_who`, `allocation_comment`, `cmdb_id`, `sys_class_name` AS `cmdb_sys_class_name`, `sncache_cmdb_ci`.`name` AS `cmdb_name`, `operational_status` AS `cmdb_operational_status`, `u_number` AS `cmdb_u_number`, `sncache_cmdb_ci`.`short_description` AS `cmdb_short_description`, `vmware_cache_vm`.`name` AS `vmware_name`, `vmware_cache_vm`.`vcenter` AS `vmware_vcenter`, `vmware_cache_vm`.`uuid` AS `vmware_uuid`, `vmware_cache_vm`.`numCPU` AS `vmware_cpus`, `vmware_cache_vm`.`memoryMB` AS `vmware_ram`, `vmware_cache_vm`.`powerState` AS `vmware_guest_state`, `vmware_cache_vm`.`guestFullName` AS `vmware_os`, `vmware_cache_vm`.`hwVersion` AS `vmware_hwversion`, `vmware_cache_vm`.`ipaddr` AS `vmware_ipaddr`, `vmware_cache_vm`.`toolsVersionStatus` AS `vmware_tools_version_status`, `puppet_nodes`.`certname` AS `puppet_certname`, `puppet_nodes`.`env` AS `puppet_env`, `puppet_nodes`.`include_default` AS `puppet_include_default`, `puppet_nodes`.`classes` AS `puppet_classes`, `puppet_nodes`.`variables` AS `puppet_variables`, `sncache_cmdb_ci`.`u_environment` AS `cmdb_environment`, `sncache_cmdb_ci`.`short_description` AS `cmdb_description`, `sncache_cmdb_ci`.`comments` AS `cmdb_comments`, `sncache_cmdb_ci`.`os` AS `cmdb_os`, `vmware_cache_vm`.`hostname` AS `vmware_hostname` FROM `systems` LEFT JOIN `sncache_cmdb_ci` ON `systems`.`cmdb_id` = `sncache_cmdb_ci`.`sys_id` LEFT JOIN `vmware_cache_vm` ON `systems`.`vmware_uuid` = `vmware_cache_vm`.`uuid` LEFT JOIN `puppet_nodes` ON `systems`.`id` = `puppet_nodes`.`id` "

################################################################################

def get_system_by_id(id):
	"""Gets all the information about a system by its database ID."""

	# Query the database
	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute(systems_select_query() + "WHERE `systems`.`id` = %s", (id,))

	# Return the result
	return curd.fetchone()

################################################################################

def get_system_by_name(name):
	"""Gets all the information about a system by its hostname."""

	# Query the database
	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute(systems_select_query() + "WHERE `systems`.`name` = %s", (name,))

	# Return the result
	return curd.fetchone()

################################################################################

def get_system_by_puppet_certname(name):
	"""Gets all the information about a system by its Puppet certificate 
	name."""

	# Query the database
	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute(systems_select_query() + "WHERE `puppet_nodes`.`certname` = %s", (name,))

	# Return the result
	return curd.fetchone()

################################################################################

def get_system_by_vmware_uuid(name):
	"""Gets all the information about a system by its VMware UUID."""

	# Query the database
	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute(systems_select_query() + "WHERE `systems`.`vmware_uuid` = %s", (name,))

	# Return the result
	return curd.fetchone()

################################################################################

def get_systems(class_name = None, search = None, order = None, order_asc = True, limit_start = None, limit_length = None, show_decom = True, only_other = False, return_cursor = False):
	"""Returns the list of systems in the database, optionally restricted to those of a certain class (e.g. srv, vhost), and ordered (defaults to "name")"""

	## BUILD THE QUERY

	# Start with no parameters, and a generic SELECT from the appropriate table
	params = ()
	query = "SELECT `systems`.`id` AS `id`, `systems`.`type` AS `type`, `systems`.`class` AS `class`, `systems`.`number` AS `number`, `systems`.`name` AS `name`, `systems`.`allocation_date` AS `allocation_date`, `systems`.`allocation_who` AS `allocation_who`, `systems`.`allocation_comment` AS `allocation_comment`, `systems`.`cmdb_id` AS `cmdb_id`, `sncache_cmdb_ci`.`operational_status` AS `cmdb_operational_status`, `vmware_cache_vm`.`powerState` AS `vmware_guest_state`, `puppet_nodes`.`certname` AS `puppet_certname`, `sncache_cmdb_ci`.`u_environment` AS `cmdb_environment`, `sncache_cmdb_ci`.`short_description` AS `cmdb_description` FROM `systems` LEFT JOIN `sncache_cmdb_ci` ON `systems`.`cmdb_id` = `sncache_cmdb_ci`.`sys_id` LEFT JOIN `vmware_cache_vm` ON `systems`.`vmware_uuid` = `vmware_cache_vm`.`uuid` LEFT JOIN `puppet_nodes` ON `puppet_nodes`.`id` = `systems`.`id` "

	# If a class_name is specfied, add on a WHERE clause
	if class_name is not None:
		query = query + "WHERE `class` = %s"
		params = (class_name,)

	# If a search term is specified...
	if search is not None:
		# Build a filter string
		like_string = '%' + search + '%'

		# If a class name was specified already, we need to AND the query,
		# otherwise we need to start the WHERE clause
		if class_name is not None:
			query = query + " AND "
		else:
			query = query + "WHERE "

		# Allow the search to match on name, allocation_comment or 
		# allocation_who
		query = query + "(`systems`.`name` LIKE %s OR `systems`.`allocation_comment` LIKE %s OR `systems`.`allocation_who` LIKE %s)"

		# Add the filter string to the parameters of the query. Add it 
		# three times as there are three columns to match on.
		params = params + (like_string, like_string, like_string)

	# If show_decom is set to false, then exclude systems that are no longer In Service
	if show_decom == False:
		if class_name is not None or search is not None:
			query = query + " AND "
		else:
			query = query + "WHERE "

		query = query + ' (`sncache_cmdb_ci`.`operational_status` = "In Service" OR `sncache_cmdb_ci`.`operational_status` IS NULL)'

	# Restrict to other/legacy types
	if only_other:
		if class_name is not None or search is not None or show_decom == False:
			query = query + " AND "
		else:
			query = query + "WHERE "
		query = query + ' `systems`.`type` != 0'

	# Handle the ordering of the rows
	query = query + " ORDER BY ";

	# By default, if order is not specified, we order by name
	if order is None:
		query = query + "`name`"

	# Validate the name of the column to sort by (this prevents errors and
	# also prevents SQL from accidentally being injected). Add the column
	# name on to the query
	if order in ["name", "number", "allocation_comment", "allocation_date", "allocation_who", "cmdb_operational_status"]:
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
			# Seriously, this is how MySQL recommends to do this :(
			query = query + "18446744073709551610"

	# Query the database
	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute(query, params)

	# Return the results
	if return_cursor:
		return curd
	else:
		return curd.fetchall()
