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
from random import randint    ## used in before_request
import time                   ## used in before_request
import random                 ## used in pwgen            
import string                 ## used in pwgen
import ldap
import MySQLdb as mysql	      ## used in before_request
from random import randint

# For cookie decode
from base64 import b64decode
from itsdangerous import base64_decode
#import zlib
import json
#import uuid

################################################################################

def session_logout():
	"""Ends the logged in user's login session. The session remains but it is marked as being not logged in."""

	app.logger.info('User "' + session['username'] + '" logged out from "' + request.remote_addr + '" using ' + request.user_agent.string)
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
		g.db = mysql.connect(host=app.config['MYSQL_HOST'], port=app.config['MYSQL_PORT'], user=app.config['MYSQL_USER'], passwd=app.config['MYSQL_PW'], db=app.config['MYSQL_DB'])
	except Exception as ex:
		cortex.errors.fatal('Unable to connect to MySQL', str(ex))

	## Check CSRF key is valid
	if request.method == "POST":
		## check csrf token is valid
		token = session.get('_csrf_token')
		if not token or token != request.form.get('_csrf_token'):
			if 'username' in session:
				app.logger.warning('CSRF protection alert: %s failed to present a valid POST token',session['username'])
			else:
				app.logger.warning('CSRF protection alert: a non-logged in user failed to present a valid POST token')

			### the user should not have accidentally triggered this
			### so just throw a 400
			abort(400)


################################################################################

def get_systems(class_name = None, order = None, limit_start = None, limit_length = None):
	"""Returns the list of systems in the database, optionally restricted to those of a certain class (e.g. srv, vhost), and ordered (defaults to "name")"""

	# Build the query
	params = ()
	query = "SELECT `id`, `type`, `class`, `number`, `name`, `allocation_date`, `allocation_who`, `allocation_comment`, `cmdb_id` FROM `systems` "
	if class_name is not None:
		query = query + "WHERE `class` = %s"
		params = (class_name,)
	query = query + " ORDER	BY ";
	if order is None:
		query = query + "`name`"
	if order in ["name", "number", "allocation_date", "allocation_who"]:
		query = query + "`" + order + "`"
	if limit_start is not None or limit_length is not None:
		query = query + " LIMIT "
		if limit_start is not None:
			query = query + str(int(limit_start)) + ","
		if limit_length is not None:
			query = query + str(int(limit_length))

	# Query the database
	cur = g.db.cursor(mysql.cursors.DictCursor)
	cur.execute(query, params)

	# Return the results
	return cur.fetchall()

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
