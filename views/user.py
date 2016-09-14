#!/usr/bin/python

from cortex import app
import cortex.lib.user
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
				return redirect(url_for('login'))
			
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
	cortex.lib.user.clear_session()
	
	# Tell the user
	flash('You were logged out successfully', 'alert-success')
	
	# Redirect the user to the login page
	return redirect(url_for('login'))

################################################################################

@app.route('/user/groups')
@cortex.lib.user.login_required
def user_groups():
	"""Handles the page which shows the user all the AD groups they are in."""

	# Get all the LDAP groups
	ldap_groups = cortex.lib.user.get_users_groups(session['username'])
	groups = []

	# Build a list of groups as a dictionary with 'name' and 'dn' components,
	# rathern than just the CNs which ldap_groups is
	for lgroup in ldap_groups:
		p = re.compile("^(cn|CN)=([^,;]+),")
		matched = p.match(lgroup)
		if matched:
			name = matched.group(2)
			groups.append({"name": name, "dn": lgroup})
	

	# Display the page
	return render_template('user/groups.html', active='user', groups=groups, title="AD Groups")
