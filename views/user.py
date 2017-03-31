#!/usr/bin/python

from cortex import app
import cortex.lib.user
import cortex.lib.logger
from flask import Flask, request, session, redirect, url_for, flash, g, abort, render_template
import re

################################################################################

@app.route('/', methods=['GET', 'POST'])
def login():
	"""Handles the login page, logging a user in on correct authentication."""

	# If the user is already logged in, just redirect them to their dashboard
	if cortex.lib.user.is_logged_in():
		return redirect(url_for('dashboard'))
	else:
		# On GET requests, just render the login page
		if request.method == 'GET' or request.method == 'HEAD':
			next = request.args.get('next', default=None)
			return render_template('login.html', next=next)

		# On POST requests, authenticate the user
		elif request.method == 'POST':
			result = cortex.lib.user.authenticate(request.form['username'], request.form['password'])

			if not result:
				flash('Incorrect username and/or password', 'alert-danger')
				cortex.lib.logger.log(__name__, 'Login failure: incorrect username/password', request.form['username'].lower())
				return redirect(url_for('login'))

			cortex.lib.logger.log(__name__, 'Login success', request.form['username'].lower())
			# Set the username in the session
			session['username']  = request.form['username'].lower()

			# Permanent sessions
			permanent = request.form.get('sec', default="")

			# Set session as permanent or not
			if permanent == 'sec':
				session.permanent = True
			else:
				session.permanent = False

			# Cache user real name
			try:
				cortex.lib.user.get_user_realname(session['username'],from_cache=False)
			except Exception as ex:
				pass
			
			# Logon is OK to proceed
			return cortex.lib.user.logon_ok()

################################################################################

@app.route('/logout')
@cortex.lib.user.login_required
def logout():
	"""Logs a user out"""

	# Log out of the session
	username = session['username']
	try:
		cortex.lib.user.clear_session()
		cortex.lib.logger.log(__name__, 'Logout success', username)
		flash('You were logged out successfully', 'alert-success')
	except Exception as e:
		cortex.lib.logger.log(__name__, 'Logout failed', username)

	# Tell the user
	
	# Redirect the user to the login page
	return redirect(url_for('login'))

################################################################################

@app.route('/user/groups')
@cortex.lib.user.login_required
def user_groups():
	"""Handles the page which shows the user all the AD groups they are in."""

	# Get all the LDAP groups
	ldap_groups = cortex.lib.user.get_users_groups(session['username'])

	# Display the page
	return render_template('user/groups.html', active='user', groups=ldap_groups, title="AD Groups")

################################################################################

@app.route('/preferences',methods=['POST'])
@cortex.lib.user.login_required
def preferences():
	"""Saves changed to a users preferences"""

	# the only preference right now is interface layout mode
	classic = False
	if 'uihorizontal' in request.form:
		if request.form['uihorizontal'] == "yes":
			classic = True

	if classic:
		g.redis.set("user:" + session['username'] + ":preferences:interface:layout","classic")
	else:
		# if they dont want the classic layout then dont store a preference at all
		g.redis.delete("user:" + session['username'] + ":preferences:interface:layout")

	flash("Your preferences have been saved","alert-success")
	return redirect(url_for('dashboard'))
