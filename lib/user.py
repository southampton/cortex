#!/usr/bin/python

from cortex import app
from flask import Flask, request, session, redirect, url_for, flash, g, abort, make_response, render_template, jsonify
import os 
import re
import MySQLdb as mysql
from functools import wraps
import ldap

################################################################################

def login_required(f):
	"""This is a decorator function that when called ensures the user has logged in.
	Usage is as such: @cortex.lib.user.login_required
	"""
	@wraps(f)
	def decorated_function(*args, **kwargs):
		if not is_logged_in():
			flash('You must login first!','alert-danger')
			args = url_encode(request.args)
			return redirect(url_for('login', next=request.script_root + request.path + "?" + args))
		return f(*args, **kwargs)
	return decorated_function

################################################################################

## NOT CURRENTLY IN USE
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

## NOT CURRENTLY IN USE
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
	return session.get('logged_in', False)

################################################################################

def clear_session():
	"""Ends the logged in user's login session. The session remains but it is marked as being not logged in."""
	app.logger.info('User "' + session['username'] + '" logged out from "' + request.remote_addr + '" using ' + request.user_agent.string)

	# Remove the following items from the session
	session.pop('logged_in', None)
	session.pop('username', None)
	session.pop('id', None)


################################################################################

def logon_ok(): 
	"""This function is called post-logon or post TOTP logon to complete the logon sequence
	"""

	## Mark as logged on
	session['logged_in'] = True

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

def authenticate(username, password):
	if len(username) == 0:
		return False
	if len(password) == 0:
		return False

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

	## Now search for the user object to bind as
	try:
		results = l.search_s(app.config['LDAP_SEARCH_BASE'], ldap.SCOPE_SUBTREE,(app.config['LDAP_USER_ATTRIBUTE']) + "=" + username)
	except ldap.LDAPError as e:
		return False

	## handle the search results
	for result in results:
		dn	= result[0]
		attrs	= result[1]

		if dn == None:
			## No dn returned. Return false.
			return False
		else:
			## Found the DN. Yay! Now bind with that DN and the password the user supplied
			try:
				lauth = ldap.initialize(app.config['LDAP_URI'])
				lauth.set_option(ldap.OPT_REFERRALS, 0)
				lauth.simple_bind_s( (dn), (password) )
			except ldap.LDAPError as e:
				## password was wrong
				return False

			## Return that LDAP auth succeeded
			return True

	## Catch all return false for LDAP auth
	return False

################################################################################
#### Authentication

def get_users_groups(username, from_cache=True):
	"""Returns a set (not a list) of groups that a user belongs to. The result is 
	cached to improve performance and to lessen the impact on the LDAP server. The 
	results are returned from the cache unless you set "from_cache" to be 
	False. 

	This function will return None in all cases where the user was not found
	or where the user has no groups. It is not expeceted that a user will ever
	be in no groups, and if they are, then they probably shouldn't be using cortex.
	"""

	## This uses REDIS to cache the LDAP response
	## because Active Directory is dog slow and takes forever to respond
	## with a list of groups, making pages load really slowly. 

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

		## Now search for the user object
		try:
			results = l.search_s(app.config['LDAP_SEARCH_BASE'], ldap.SCOPE_SUBTREE,(app.config['LDAP_USER_ATTRIBUTE']) + "=" + username)
		except ldap.LDAPError as e:
			return None

		## handle the search results
		for result in results:
			dn	= result[0]
			attrs	= result[1]

			if dn == None:
				return None
			else:
				## Found the DN. Yay! Now bind with that DN and the password the user supplied

				if 'memberOf' in attrs:
					if len(attrs['memberOf']) > 0:
						for group in attrs['memberOf']:
							g.redis.sadd("ldap/user/groups/" + username,group)
						g.redis.expire("ldap/user/groups/" + username,app.config['LDAP_GROUPS_CACHE_EXPIRE'])
						return attrs['memberOf']
					else:
						return None
				else:
					return None

		return None

