#!/usr/bin/python

from cortex import app
import cortex.lib.core
from flask import Flask, request, session, redirect, url_for, flash, g, abort, make_response, render_template, jsonify
import os 
import re
import MySQLdb as mysql
from functools import wraps
import ldap
from werkzeug.urls import url_encode

ROLE_WHO_USER = 0
ROLE_WHO_LDAP_GROUP = 1
ROLE_WHO_NIS_GROUP = 2

################################################################################

def login_required(f):
	"""This is a decorator function that when called ensures the user has logged in.
	Usage is as such: @cortex.lib.user.login_required"""

	@wraps(f)
	def decorated_function(*args, **kwargs):
		if not is_logged_in():
			flash('You must login first!', 'alert-danger')
			args = url_encode(request.args)
			return redirect(url_for('login', next=request.script_root + request.path + "?" + args))
		return f(*args, **kwargs)
	return decorated_function

################################################################################

# NOT CURRENTLY IN USE
def global_admin_required(f):
	"""This is a decorator function that when called ensures the user is a global admin
	Usage is as such: @cortex.lib.user.global_admin_required"""

	@wraps(f)
	def decorated_function(*args, **kwargs):
		if not is_global_admin(session['username']):
			abort(403)
		return f(*args, **kwargs)
	return decorated_function

################################################################################

def is_global_admin(username):
	"""Returns a boolean indicating if the given user is a global admin."""

	groups = get_users_groups(username)
	groups = [x.lower() for x in groups]

	if app.config['LDAP_ADMIN_GROUP'].lower() in groups:
		return True

	return False

################################################################################

# NOT CURRENTLY IN USE
def is_in_group(group_cn):
	"""Returns a boolean indicating if the logged in user is in the given
	group, which is specified given it's entire CN. The group name 
	comparison is performed in a case insensitive manner. If no user is
	logged in, this function will return False."""

	# If user is not logged in, then assume we're not in the group
	if not is_logged_in():
		return False

	# Get a lowercase list of groups
	groups = get_users_groups(session['username'])
	groups = [x.lower() for x in groups]

	# See if the user is in the group and return true if they are
	if group.lower() in groups:
		return True

	return False

################################################################################

def is_logged_in():
	"""Returns a boolean indicating whether the current session has a logged
	in user."""

	return session.get('logged_in', False)

################################################################################

def clear_session():
	"""Ends the logged in user's login session. The session remains but it 
	is marked as being not logged in."""

	app.logger.info('User "' + session['username'] + '" logged out from "' + request.remote_addr + '" using ' + request.user_agent.string)

	# Remove the following items from the session
	session.pop('logged_in', None)
	session.pop('username', None)
	session.pop('id', None)


################################################################################

def logon_ok(): 
	"""This function is called post-logon or post TOTP logon to complete the
	logon sequence"""

	# Mark as logged on
	session['logged_in'] = True

	# Log a successful login
	app.logger.info('User "' + session['username'] + '" logged in from "' + request.remote_addr + '" using ' + request.user_agent.string)
		
	# Determine if "next" variable is set (the URL to be sent to)
	next = request.form.get('next', default=None)
	
	if next == None:
		return redirect(url_for('dashboard'))
	else:
		return redirect(next)

################################################################################
# Authentication

def authenticate(username, password):
	"""Determines whether the given username and password are valid by using
	them to authenticate against LDAP."""

	if len(username) == 0:
		return False
	if len(password) == 0:
		return False

	# Connect to the LDAP server
	l = cortex.lib.core.connect()

	# Now search for the user object to bind as
	try:
		results = l.search_s(app.config['LDAP_SEARCH_BASE'], ldap.SCOPE_SUBTREE, (app.config['LDAP_USER_ATTRIBUTE']) + "=" + username)
	except ldap.LDAPError as e:
		return False

	# Handle the search results
	for result in results:
		dn	= result[0]
		attrs	= result[1]

		if dn == None:
			# No dn returned. Return false.
			return False
		else:
			# Found the DN. Yay! Now bind with that DN and the password the user supplied
			try:
				lauth = ldap.initialize(app.config['LDAP_URI'])
				lauth.set_option(ldap.OPT_REFERRALS, 0)
				lauth.simple_bind_s( (dn), (password) )
			except ldap.LDAPError as e:
				# Password was wrong
				return False

			# Return that LDAP auth succeeded
			return True

	# Catch all return false for LDAP auth
	return False

################################################################################

def get_users_groups(username, from_cache=True):
	"""Returns a set (not a list) of groups that a user belongs to. The result is 
	cached to improve performance and to lessen the impact on the LDAP server. The 
	results are returned from the cache unless you set "from_cache" to be 
	False. 

	This function will return None in all cases where the user was not found
	or where the user has no groups. It is not expeceted that a user will ever
	be in no groups, and if they are, then they probably shouldn't be using cortex.
	"""

	# This uses REDIS to cache the LDAP response
	# because Active Directory is dog slow and takes forever to respond
	# with a list of groups, making pages load really slowly. 

	if from_cache == False:
		return get_users_groups_from_ldap(username)
	else:
		# Check the cache to see if it already has entries for the user
		# we use a key to set whether we /have/ cached the users 
		groups = g.redis.smembers("ldap/user/groups/" + username)

		if groups == None:
			return get_users_groups_from_ldap(username)
		elif not len(groups) > 0:
			return get_users_groups_from_ldap(username)
		else:
			return groups

################################################################################
		
def get_users_groups_from_ldap(username):
	"""Talks to LDAP and gets the list of the given users groups. This
	information is then stored in Redis so that it can be accessed 
	quickly."""


	# Connect to the LDAP server
	l = cortex.lib.core.connect()

	# Now search for the user object
	try:
		results = l.search_s(app.config['LDAP_SEARCH_BASE'], ldap.SCOPE_SUBTREE, (app.config['LDAP_USER_ATTRIBUTE']) + "=" + username)
	except ldap.LDAPError as e:
		return None

	# Handle the search results
	for result in results:
		dn	= result[0]
		attrs	= result[1]

		if dn == None:
			return None
		else:
			# Found the DN. Yay! Now bind with that DN and the password the user supplied
			if 'memberOf' in attrs:
				if len(attrs['memberOf']) > 0:
					for group in attrs['memberOf']:
						g.redis.sadd("ldap/user/groups/" + username, group)
					g.redis.expire("ldap/user/groups/" + username, app.config['LDAP_GROUPS_CACHE_EXPIRE'])
					return attrs['memberOf']
				else:
					return None
			else:
				return None

	return None

##############################################################################

def get_user_realname_from_ldap(username):
	"""Talks to LDAP and retrieves the real name of the username passed."""

	# The name we've picked
	# Connect to LDAP
	l = cortex.lib.core.connect()
	
	# Now search for the user object
	try:
		results = l.search_s(app.config['LDAP_SEARCH_BASE'], ldap.SCOPE_SUBTREE, (app.config['LDAP_USER_ATTRIBUTE']) + "=" + username)
	except ldap.LDAPError as e:
		return username

	# Handle the search results
	for result in results:
		dn	= result[0]
		attrs	= result[1]

		if dn == None:
			return None
		else:
			if 'givenName' in attrs:
				if len(attrs['givenName']) > 0:
					firstname = attrs['givenName'][0]
			if 'sn' in attrs:
				if len(attrs['sn']) > 0:
					lastname = attrs['sn'][0]

	try:
		if len(firstname) > 0 and len(lastname) > 0:
			name = firstname + ' ' + lastname
		elif len(firstname) > 0:
			name = firstname
		elif len(lastname) > 0:
			name = lastname
		else:
			name = username
	except Exception as ex:
		name = username
	try:
		curd = g.db.cursor(mysql.cursors.DictCursor)
		curd.execute('REPLACE INTO `realname_cache` (`username`, `realname`) VALUES (%s,%s)', (username, name))
		g.db.commit()
	except Exception as ex:
		app.logger.warning('Failed to cache user name: ' + str(ex))
	return name

#############################################################################

def get_user_realname(username, from_cache=True):
	"""Returns the real name of the passed username . The result is 
	cached to improve performance and to lessen the impact on the LDAP server. The 
	results are returned from the cache unless you set "from_cache" to be 
	False. 

	This function will return the username  in all cases where the user was not found
	or where there is no associated real name.
	"""

	# We cache the real names in MySQL because Active Directory is 
	# dog slow and takes forever to respond with a list of groups, 
	# making pages load really slowly. We don't use REDIS because we have a
	# MySQL view which needs to include the real name data.

	if from_cache == False:
		return get_user_realname_from_ldap(username)
	else:
		# Check the cache to see if it already has entries for the user
		# we use a key to set whether we /have/ cached the users 
		try:
			curd = g.db.cursor(mysql.cursors.DictCursor)
			curd.execute('SELECT `realname` AS `name` FROM `realname_cache` WHERE `username` = %s', (username))
			user = curd.fetchone()
			curd.close()
		except Exception as ex:
			app.logger.warning('Failed to retrieve user from cache: ' + str(ex) + 'Falling back to LDAP lookup')
			return get_user_realname_from_ldap(username)

		if user is None:
			return get_user_realname_from_ldap(username)
		return user['name']

#############################################################################

def does_user_have_permission(perm, user=None):
	"""Returns a boolean indicating if a user has a certain permission or
	one of a list of permissions.
	  perm: Either a string or a list of strings that contains the
	        permission(s) to search for
	  user: The user whose permissions should be checked. Defaults to
	        None, which checks the currently logged in user."""

	# Default to using the current user
	if user is None:
		if 'username' in session:
			user = session['username']
		else:
			# User not logged in - they definitely don't have permission!
			return False

	# Turn the permission(s) in to a lowercase list of permissions so we 
	# can check a number of permissions at once
	if type(perm) is list:
		for idx, val in enumerate(perm):
			perm[idx] = val.lower()
	else:
		perm = [perm.lower()]

	# If we've already cached this users groups
	if 'user_perms' in g:
		app.logger.debug("Checking request-cached permissions for user " + str(user) + ": " + str(perm))

		# Check if any of the permissions in perm are in the users
		# cached permissions list
		for p in perm:
			if p in g.user_perms:
				return True

		# Didn't match any permissions, return False
		app.logger.info("User " + str(user) + " did not have permission(s) " + str(perm))
		return False

	app.logger.debug("Calculating permissions for user " + str(user) + ": " + str(perm))

	# Query role_who joined to role_perms to see which permissions a user
	# has explicitly assigned to their username attached to a role
	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute('SELECT LOWER(`role_perms`.`perm`) AS `perm` FROM `role_who` JOIN `role_perms` ON `role_who`.`role_id` = `role_perms`.`role_id` JOIN `roles` ON `roles`.`id` = `role_perms`.`role_id` WHERE `role_who`.`who` = %s AND `role_who`.`type` = %s', (user, ROLE_WHO_USER))

	# Start a set to build the users permissions
	user_perms = set()

	# Iterate through these permissions, adding them to the set
	user_perms.update([row['perm'] for row in curd])

	# Get the (possibly cached) list of groups for the user
	ldap_groups = get_users_groups(user)

	# Regex for extracting just the CN from the DN in the cached group names
	cn_regex = re.compile("^(cn|CN)=([^,;]+),")

	# Iterate over the groups, getting the roles (and thus permissions) for
	# that group
	for group in ldap_groups:
		# Extract the CN from the DN using the compiled regex
		matched = cn_regex.match(group)
		if matched:
			group = matched.group(2)
		else:
			continue

		curd.execute('SELECT LOWER(`role_perms`.`perm`) AS `perm` FROM `role_who` JOIN `role_perms` ON `role_who`.`role_id` = `role_perms`.`role_id` JOIN `roles` ON `roles`.`id` = `role_perms`.`role_id` WHERE `role_who`.`who` = %s AND `role_who`.`type` = %s', (group, ROLE_WHO_LDAP_GROUP))

		# Add all the user permissions to the set
		user_perms.update([row['perm'] for row in curd])

	# Store these calculated permissions in the context
	app.logger.debug("Calculated user permissions for " + str(user) + " as " + str(user_perms))
	g.user_perms = user_perms

	# Check whether the user has any of the permissions
	for p in perm:
		if p in g.user_perms:
			return True
	
	# We've not found the permission, return False to indicate that
	app.logger.info("User " + str(user) + " did not have permission(s) " + str(perm))
	return False

#############################################################################

def can_user_access_workflow(workflow, user=None):
	"""Returns a boolean indicating if a user is allowed to use the
	specified workflow. This function takes into account the 
	workflows.all permission, which overrides this.
	  workflow: The name of the workflow's view function.
	  user: The user whose permissions should be checked. Defaults to
	        None, which checks the currently logged in user."""

	# Default to using the current user
	if user is None:
		if 'username' in session:
			user = session['username']
		else:
			# User not logged in - they definitely don't have permission!
			return False

	# Check the overriding permission of "workflows.all". If the user has
	# this then they can access the workflow regardless
	if does_user_have_permission("workflows.all", user):
		return True

	app.logger.debug("Checking permissions for user " + str(user) + " on workflow " + str(workflow))

	# Query the workflow_perms table to see if the user has the workflow
	# explicitly given access to them
	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute('SELECT 1 FROM `workflow_perms` WHERE `workflow_name` = %s AND `who` = %s AND `type` = %s', (workflow, user, ROLE_WHO_USER))

	# If a row is returned then they have access to the workflow
	if len(curd.fetchall()) > 0:
		return True

	# Get the (possibly cached) list of groups for the user
	ldap_groups = get_users_groups(user)

	# Regex for extracting just the CN from the DN in the cached group names
	cn_regex = re.compile("^(cn|CN)=([^,;]+),")

	# Iterate over the groups, checking each group for the permission
	for group in ldap_groups:
		# Extract the CN from the DN using the compiled regex
		matched = cn_regex.match(group)
		if matched:
			group = matched.group(2)
		else:
			continue

		# Query the workflow_perms table to see if the workflow is 
		# given access by group
		curd.execute('SELECT 1 FROM `workflow_perms` WHERE `workflow_name` = %s AND `who` = %s AND `type` = %s', (workflow, group, ROLE_WHO_LDAP_GROUP))

		# If a row is returned then they have access to the workflow
		if len(curd.fetchall()) > 0:
			return True

	# Default: return False as the user shouldn't be able to access the workflow
	return False
