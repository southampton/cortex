#!/usr/bin/python

from cortex import app
import cortex.lib.ldapc
import cortex.lib.core
from flask import Flask, request, session, redirect, url_for, flash, g, abort, make_response, render_template, jsonify
import os
import re
import pwd
import MySQLdb as mysql
from functools import wraps
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
			session['next'] = request.url
			return redirect(url_for('root'))
		return f(*args, **kwargs)
	return decorated_function

################################################################################

def is_logged_in():
	"""Returns a boolean indicating whether the current session has a logged
	in user."""

	return session.get('logged_in', False)

################################################################################

def clear_session():
	"""Ends the logged in user's login session. The session remains but it 
	is marked as being not logged in."""

	if 'username' in session:
		cortex.lib.core.log(__name__, 'cortex.logout', session['username'] + ' logged out using ' + request.user_agent.string)

	# Remove the following items from the session
	session.pop('logged_in', None)
	session.pop('username', None)
	session.pop('id', None)

################################################################################

def logon_ok(username):
	"""This function is called post-logon or post TOTP logon to complete the
	logon sequence"""

	# Mark as logged on
	session['username'] = username.lower()
	session['logged_in'] = True
	
	# Update the user's realname in the cache table
	try:
		get_user_realname(session['username'], from_cache=False)
	except:
		pass

	# Log a successful login
	cortex.lib.core.log(__name__, 'cortex.login', '' + session['username'] + ' logged in using ' + request.user_agent.string)

	# Determine if "next" variable is set (the URL to be sent to)
	next = session.pop('next', None)

	if next == None:
		return redirect(url_for('dashboard'))
	else:
		return redirect(next)

################################################################################
# Authentication

def authenticate(username, password):
	"""Determines whether the given username and password combo is valid."""

	if len(username) == 0:
		return False
	if len(password) == 0:
		return False

	return cortex.lib.ldapc.auth(username,password)

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

	# We cache the groups a user has in MySQL because Active Directory is VERY
	# slow and we don't want to have to wait for AD every time a user wants to
	# access something (or list the systems they have access to). We don't use
	# REDIS cos we need to do complicated SQL queries to determine a users
	# systems they can access and its much faster with joins/subqueries than
	# thousands of queries 'cos the groups are stored in REDIS.
	# so its in Mysql. So there.

	if from_cache == False:
		return cortex.lib.ldapc.get_users_groups_from_ldap(username)
	else:
		curd = g.db.cursor(mysql.cursors.DictCursor)

		## Get from the cache (if it hasn't expired)
		curd.execute('SELECT 1 FROM `ldap_group_cache_expire` WHERE `username` = %s AND `expiry_date` > CURDATE()', (username,))
		if curd.fetchone() is not None:
			## The cache has not expired, return the list
			curd.execute('SELECT `group` FROM `ldap_group_cache` WHERE `username` = %s ORDER BY `group`', (username,))
			groupdict = curd.fetchall()
			groups = []
			for group in groupdict:
				groups.append(group['group'])

			return groups

		else:
			## teh cache has expired, return them from LDAP directly (but also cache)
			return cortex.lib.ldapc.get_users_groups_from_ldap(username)

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
		return cortex.lib.ldapc.get_user_realname_from_ldap(username)
	else:
		# Check the cache to see if it already has entries for the user
		# we use a key to set whether we /have/ cached the users //
		try:
			curd = g.db.cursor(mysql.cursors.DictCursor)
			curd.execute('SELECT `realname` AS `name` FROM `realname_cache` WHERE `username` = %s', (username,))
			user = curd.fetchone()
			curd.close()
		except Exception as ex:
			app.logger.warning('Failed to retrieve user from cache: ' + str(ex) + 'Falling back to LDAP lookup')
			return cortex.lib.ldapc.get_user_realname_from_ldap(username)

		if user is None:
			return cortex.lib.ldapc.get_user_realname_from_ldap(username)
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
		app.logger.debug("User " + str(user) + " did not have permission(s) " + str(perm))
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

	# Iterate over the groups, getting the roles (and thus permissions) for
	# that group
	for group in ldap_groups:
		curd.execute('SELECT LOWER(`role_perms`.`perm`) AS `perm` FROM `role_who` JOIN `role_perms` ON `role_who`.`role_id` = `role_perms`.`role_id` JOIN `roles` ON `roles`.`id` = `role_perms`.`role_id` WHERE `role_who`.`who` = %s AND `role_who`.`type` = %s', (group.lower(), ROLE_WHO_LDAP_GROUP))

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
	app.logger.debug("User " + str(user) + " did not have permission(s) " + str(perm))
	return False

#############################################################################

def does_user_have_workflow_permission(perm, user=None):
	"""Shortcut function to determine if a user has the permission specified,
		or 'workflows.all' which bypasses all workflow permissions. """
	if not perm.startswith("workflows."):
		perm = "workflows." + perm

	if does_user_have_permission(perm, user) or does_user_have_permission("workflows.all", user):
		return True

	return False

#############################################################################

def does_user_have_system_permission(system_id,sysperm,perm=None,user=None):
	"""Returns a boolean indicating if a user has the specified permission
	on the system specified in system_id. If 'perm' is supplied then the function
	returns true if the user has the global 'perm' instead (e.g. a global
	override permission).

	  system_id: The Cortex system id of the system (as found in the
                     systems table)
	  sysperm: A string containing the system permission to check for
	  perm: The global permission, which is the user has, overrides system
			permissions and causes the function to return True irrespective
			of whether the user has the system permission or not. Defaults to 
			None (no global permission is checked for)
	  user: The user whose permissions should be checked. Defaults to
	        None, which checks the currently logged in user."""

	# Default to using the current user
	if user is None:
		if 'username' in session:
			user = session['username']
		else:
			# User not logged in - they definitely don't have permission!
			return False

	## Global permission override
	if perm is not None:
		if does_user_have_permission(perm,user):
			return True

	app.logger.debug("Checking system permissions for user " + str(user) + " on system " + str(system_id))

	# Query the system_perms table to see if the user has the system
	# explicitly given access to them
	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute('SELECT 1 FROM `system_perms` WHERE `system_id` = %s AND `who` = %s AND `type` = %s AND `perm` = %s', (system_id, user, ROLE_WHO_USER, sysperm))

	# If a row is returned then they have the permission
	if len(curd.fetchall()) > 0:
		return True

	# Get the (possibly cached) list of groups for the user
	ldap_groups = get_users_groups(user)

	# Iterate over the groups, checking each group for the permission
	for group in ldap_groups:
		# Query the system_perms table to see if the permission is granted
		# to the group the user is in
		curd.execute('SELECT 1 FROM `system_perms` WHERE `system_id` = %s AND `who` = %s AND `type` = %s AND `perm` = %s', (system_id, group.lower(), ROLE_WHO_LDAP_GROUP, sysperm))

		# If a row is returned then they have access to the workflow
		if len(curd.fetchall()) > 0:
			return True

	return False

################################################################################

#############################################################################

def does_user_have_any_system_permission(sysperm,user=None):
	"""Returns a boolean indicating if a user has a per-system permission on
	any system. This exists because some functions return data that can only
	be accessed if a user has a permission on at least one system, but it does
	not matter which system

	  sysperm: A string containing the system permission to check for"""

	# Default to using the current user
	if user is None:
		if 'username' in session:
			user = session['username']
		else:
			# User not logged in - they definitely don't have permission!
			return False

	app.logger.debug("Checking to see if " + str(user) + " has system permission " + sysperm + " on any system")

	# Query the system_perms table to see if the user has the system
	# explicitly given access to them
	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute('SELECT 1 FROM `system_perms` WHERE `who` = %s AND `type` = %s AND `perm` = %s', (user, ROLE_WHO_USER, sysperm))

	# If a row is returned then they have the permission
	if len(curd.fetchall()) > 0:
		app.logger.debug("The user " + str(user) + " has system permission " + sysperm + " on at least one system")
		return True

	# Get the (possibly cached) list of groups for the user
	ldap_groups = get_users_groups(user)

	# Iterate over the groups, checking each group for the permission
	for group in ldap_groups:
		# Query the system_perms table to see if the permission is granted
		# to the group the user is in
		curd.execute('SELECT 1 FROM `system_perms` WHERE `who` = %s AND `type` = %s AND `perm` = %s', (group.lower(), ROLE_WHO_LDAP_GROUP, sysperm))

		# If a row is returned then they have access to the workflow
		if len(curd.fetchall()) > 0:
			app.logger.debug("The user " + str(user) + " has system permission " + sysperm + " on at least one system")
			return True

	app.logger.debug("The user " + str(user) + " does NOT have system permission " + sysperm + " on any system")
	return False

################################################################################

def does_user_exist(username):

	try:
		passwd = pwd.getpwnam(username)
		return True
	except KeyError as e:
		return False
