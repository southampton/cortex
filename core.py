#!/usr/bin/python
#

from cortex import app
import cortex.errors     
from werkzeug.urls import url_encode
from flask import Flask, request, redirect, session, url_for, abort, render_template, flash, g
from functools import wraps   ## used for login_required and downtime_check
from Crypto.Cipher import AES ## used for crypto of password
import base64                 ## used for crypto of password
import os                     ## used throughout
import datetime               ## used in ut_to_string, online functions
#import redis                  ## used in before_request
import time                   ## used in before_request
import random                 ## used in pwgen            
import string                 ## used in pwgen
import ldap
import MySQLdb as mysql	      ## used in before_request
import json
import requests
import Pyro4
import inspect

################################################################################

def session_logout():
	"""Ends the logged in user's login session. The session remains but it is marked as being not logged in."""

	app.logger.info('User "' + session['username'] + '" logged out from "' + request.remote_addr + '" using ' + request.user_agent.string)

	# Remove the following items from the session
	session.pop('logged_in', None)
	session.pop('username', None)
	session.pop('id', None)

################################################################################

def login_required(f):
	"""This is a decorator function that when called ensures the user has logged in.
	Usage is as such: @cortex.core.login_required
	"""
	@wraps(f)
	def decorated_function(*args, **kwargs):
		if not is_user_logged_in():
			flash('You must login first!','alert-danger')
			args = url_encode(request.args)
			return redirect(url_for('login', next=request.script_root + request.path + "?" + args))
		return f(*args, **kwargs)
	return decorated_function

def is_user_logged_in():
	return session.get('logged_in',False)

@app.before_request
def before_request():
	"""This function is run before the request is handled by Flask. At present it checks
	to make sure a valid CSRF token has been supplied if a POST request is made, sets
	the default theme, tells out of date web browsers to foad, and connects to redis
	for user data storage.
	"""

	# Check for MSIE version <= 8.0
	if (request.user_agent.browser == "msie" and int(round(float(request.user_agent.version))) <= 8):
		return render_template('foad.html')

	## Connect to redis
	#if app.config['REDIS_ENABLED']:
	#	try:
	#		g.redis = redis.StrictRedis(host=app.config['REDIS_HOST'], port=app.config['REDIS_PORT'], db=0)
	#		g.redis.get('foo')
	#	except Exception as ex:
	#		cortex.errors.fatal('Unable to connect to redis',str(ex))
	
	## Connect to database
	try:
		g.db = mysql.connect(host=app.config['MYSQL_HOST'], port=app.config['MYSQL_PORT'], user=app.config['MYSQL_USER'], passwd=app.config['MYSQL_PASS'], db=app.config['MYSQL_NAME'])
	except Exception as ex:
		cortex.errors.fatal('Unable to connect to MySQL', str(ex))

	## Check CSRF key is valid
	if request.method == "POST":
		## check csrf token is valid
		token = session.get('_csrf_token')
		if not token or token != request.form.get('_csrf_token'):
			if 'username' in session:
				app.logger.warning('CSRF protection alert: %s failed to present a valid POST token', session['username'])
			else:
	 			app.logger.warning('CSRF protection alert: a non-logged in user failed to present a valid POST token')

			### the user should not have accidentally triggered this
			### so just throw a 400
			abort(400)

################################################################################

def get_cmdb_ci_count(search = None):
	"""Returns the number of CMDB CIs in the database, optionally restricted by a search term"""

	## BUILD THE QUERY

	# Start with no parameters, and a generic SELECT COUNT(*) from the appropriate table
	params = ()
	query = 'SELECT COUNT(*) AS `count` FROM `sncache_cmdb_ci` '

	# If a search term is specified...
	if search is not None:
		# Build a filter string
		like_string = '%' + search + '%'

		# Allow the search to match on name or u_number
		query = query + "WHERE (`name` LIKE %s OR `u_number` LIKE %s)"

		# Add the filter string to the parameters of the query. Add it 
		# three times as there are three columns to match on.
		params = (like_string, like_string)

	# Query the database
	cur = g.db.cursor(mysql.cursors.DictCursor)
	cur.execute(query, params)

	# Get the results
	row = cur.fetchone()

	# Return the count
	return row['count']

################################################################################

def get_cmdb_cis(limit_start = None, limit_length = None, search = None):
	"""Returns the list of systems from the ServiceNow CMDB CI cache table."""

	## BUILD THE QUERY

	# Start with no parameters, and a generic SELECT from the appropriate table
	params = ()
	query = "SELECT `sys_id`, `sys_class_name`, `name`, `operational_status`, `u_number`, `short_description` FROM `sncache_cmdb_ci` "

	# If a search term is specified...
	if search is not None:
		# Build a filter string
		like_string = '%' + search + '%'

		# Allow the search to match on name, or u_number
		query = query + "WHERE (`name` LIKE %s OR `u_number` LIKE %s)"

		# Add the filter string to the parameters of the query. Add it 
		# three times as there are three columns to match on.
		params = (like_string, like_string)

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
	cur = g.db.cursor(mysql.cursors.DictCursor)
	cur.execute(query, params)

	# Return the results
	return cur.fetchall()

################################################################################

def get_system_count(class_name = None, search = None, show_decom = True):
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
		query = query + "(`name` LIKE %s OR `allocation_comment` LIKE %s OR `allocation_who` LIKE %s)"

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

	# Query the database
	cur = g.db.cursor(mysql.cursors.DictCursor)
	cur.execute(query, params)

	# Get the results
	row = cur.fetchone()

	# Return the count
	return row['count']

################################################################################

def get_system_by_id(id):
	# Query the database
	cur = g.db.cursor(mysql.cursors.DictCursor)
	cur.execute("SELECT `id`, `type`, `class`, `number`, `systems`.`name` AS `name`, `allocation_date`, `allocation_who`, `allocation_comment`, `cmdb_id`, `sys_class_name` AS `cmdb_sys_class_name`, `sncache_cmdb_ci`.`name` AS `cmdb_name`, `operational_status` AS `cmdb_operational_status`, `u_number` AS `cmdb_u_number`, `sncache_cmdb_ci`.`short_description` AS `cmdb_short_description` FROM `systems` LEFT JOIN `sncache_cmdb_ci` ON `systems`.`cmdb_id` = `sncache_cmdb_ci`.`sys_id` WHERE `id` = %s", (id,))

	# Return the results
	return cur.fetchone()

################################################################################

def get_systems(class_name = None, search = None, order = None, order_asc = True, limit_start = None, limit_length = None, show_decom = True):
	"""Returns the list of systems in the database, optionally restricted to those of a certain class (e.g. srv, vhost), and ordered (defaults to "name")"""

	## BUILD THE QUERY

	# Start with no parameters, and a generic SELECT from the appropriate table
	params = ()
	query = "SELECT `systems`.`id` AS `id`, `systems`.`type` AS `type`, `systems`.`class` AS `class`, `systems`.`number` AS `number`, `systems`.`name` AS `name`, `systems`.`allocation_date` AS `allocation_date`, `systems`.`allocation_who` AS `allocation_who`, `systems`.`allocation_comment` AS `allocation_comment`, `systems`.`cmdb_id` AS `cmdb_id`, `sncache_cmdb_ci`.`operational_status` AS `cmdb_operational_status` FROM `systems` LEFT JOIN `sncache_cmdb_ci` ON `systems`.`cmdb_id` = `sncache_cmdb_ci`.`sys_id` "

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
		query = query + "(`name` LIKE %s OR `allocation_comment` LIKE %s OR `allocation_who` LIKE %s)"

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
	cur = g.db.cursor(mysql.cursors.DictCursor)
	cur.execute(query, params)

	# Return the results
	return cur.fetchall()

################################################################################

def class_display_name(name):
	"""Maps a ServiceNow sys_class_name to a user-readable name"""

	if name in app.config['CMDB_CLASS_NAMES']:
		return app.config['CMDB_CLASS_NAMES'][name]
	else:
		return 'Unknown'

################################################################################

def generate_csrf_token():
	"""This function is used in __init__.py to generate a CSRF token for use
	in templates.
	"""

	if '_csrf_token' not in session:
		session['_csrf_token'] = pwgen(32)
	return session['_csrf_token']

################################################################################

def pwgen(length=16):
	"""This is very crude password generator. It is currently only used to generate
	a CSRF token.
	"""

	urandom = random.SystemRandom()
	alphabet = string.ascii_letters + string.digits
	return str().join(urandom.choice(alphabet) for _ in range(length))

################################################################################

def logon_ok():
	"""This function is called post-logon or post TOTP logon to complete the logon sequence
	"""

	## Mark as logged on
	session['logged_in']  = True

	## Log a successful login
	app.logger.info('User "' + session['username'] + '" logged in from "' + request.remote_addr + '" using ' + request.user_agent.string)
		
	## determine if "next" variable is set (the URL to be sent to)
	next = request.form.get('next',default=None)
	
	if next == None:
		return redirect(url_for('dashboard'))
	else:
		return redirect(next)

################################################################################
#### Authentication

def auth_user(username, password):
	app.logger.debug("cortex.core.auth_user " + username)

	if len(username) == 0:
		app.logger.debug("cortex.core.auth_user empty username")
		return False
	if len(password) == 0:
		app.logger.debug("cortex.core.auth_user empty password")
		return False

	## LDAP auth. This is preferred as of May 2015 due to issues with python-kerberos.

	## connect to LDAP and turn off referals
	l = ldap.initialize(app.config['LDAP_URI'])
	l.set_option(ldap.OPT_REFERRALS, 0)

	## and bind to the server with a username/password if needed in order to search for the full DN for the user who is logging in.
	try:
		if app.config['LDAP_ANON_BIND']:
			l.simple_bind_s()
		else:
			l.simple_bind_s( (app.config['LDAP_BIND_USER']), (app.config['LDAP_BIND_PW']) )
	except ldap.LDAPError as e:
		flash('Internal Error - Could not connect to LDAP directory: ' + str(e),'alert-danger')
		app.logger.error("Could not bind to LDAP: " + str(e))
		abort(500)


	app.logger.debug("cortex.core.auth_user ldap searching for username in base " + app.config['LDAP_SEARCH_BASE'] + " looking for attribute " + app.config['LDAP_USER_ATTRIBUTE'])

	## Now search for the user object to bind as
	try:
		results = l.search_s(app.config['LDAP_SEARCH_BASE'], ldap.SCOPE_SUBTREE,(app.config['LDAP_USER_ATTRIBUTE']) + "=" + username)
	except ldap.LDAPError as e:
		app.logger.debug("cortex.core.auth_user no object found in ldap")
		return False

	app.logger.debug("cortex.core.auth_user ldap found results from dn search")
	
	## handle the search results
	for result in results:
		dn	= result[0]
		attrs	= result[1]

		if dn == None:
			## No dn returned. Return false.
			return False
		else:
			app.logger.debug("cortex.core.auth_user ldap found dn " + str(dn))
			## Found the DN. Yay! Now bind with that DN and the password the user supplied
			try:
				app.logger.debug("cortex.core.auth_user ldap attempting ldap simple bind as " + str(dn))
				lauth = ldap.initialize(app.config['LDAP_URI'])
				lauth.set_option(ldap.OPT_REFERRALS, 0)
				lauth.simple_bind_s( (dn), (password) )
			except ldap.LDAPError as e:
				## password was wrong
				app.logger.debug("cortex.core.auth_user ldap bind failed as " + str(dn))
				return False

			app.logger.debug("cortex.core.auth_user ldap bind succeeded as " + str(dn))

			## Return that LDAP auth succeeded
			app.logger.debug("cortex.core.auth_user ldap success")
			return True

	## Catch all return false for LDAP auth
	return False

################################################################################

def neocortex_connect():
	"""This function connects to the Neocortex job daemon using the Pyro4
	Remote Procedure Call (RPC) library."""

	# Connect, and perform some set up, including setting up a pre-shared
	# message signing key
	proxy = Pyro4.Proxy('PYRO:neocortex@localhost:1888')
	proxy._pyroHmacKey = app.config['NEOCORTEX_KEY']
	proxy._pyroTimeout = 5

	## TODO better error handling

	# Ping the server to ensure it's alive
	proxy.ping()

	return proxy

################################################################################

@app.context_processor
def inject_template_data():
	"""This function is called on every page load. It injects a 'workflows'
	variable in to every render_template call, which is used to populate the
	Workflows menu on the page."""

	return dict(workflows=app.workflows)
