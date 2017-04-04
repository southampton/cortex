#!/usr/bin/python

from cortex import app
import cortex.lib.user
from flask import Flask, request, session, redirect, url_for, flash, g, abort, render_template
import re
from cas_client import CASClient

################################################################################
#CAS client init
cas_client = CASClient(app.config['CAS_SERVER_URL'], app.config['CAS_SERVICE_URL'], verify_certificates=True)

################################################################################

@app.route('/', methods=['GET', 'POST'])
@app.disable_csrf_check
def root():
	if request.method == 'POST' and 'logoutRequest' in request.form:
		cortex.lib.user.clear_session()
		return ('', 200)
	else:
		return login()

################################################################################

@app.route('/login', methods=['GET', 'POST'])
def login():
	"""Handles the login page, logging a user in on correct authentication."""

	# If the user is already logged in, just redirect them to their dashboard
	if cortex.lib.user.is_logged_in():
		return redirect(url_for('dashboard'))

	# LDAP login
	if request.method == 'POST':
		if all(field in request.form for field in ['username', 'password']):
			result = cortex.lib.user.authenticate(request.form['username'], request.form['password'])

			if not result:
				flash('Incorrect username and/or password', 'alert-danger')
				return render_template('login.html')
			
			# Permanent sessions
			permanent = request.form.get('sec', default="")

			# Set session as permanent or not
			if permanent == 'sec':
				session.permanent = True
			else:
				session.permanent = False
			# Logon is OK to proceed
			return cortex.lib.user.logon_ok(request.form['username'])
		abort(400)

	# present LDAP auth
	elif request.args.get('bypasscas', None) == '1':
		return render_template('login.html')

	#otherwise perform cas auth
	else:
		ticket = request.args.get('ticket')
		if ticket:
			try:
				cas_response = cas_client.perform_service_validate(ticket=ticket)
			except:
				#CAS is not working falling back to LDAP
				flash("CAS SSO is not working, falling back to LDAP authentication", 'alert-warning')
				return render_template('login.html')
			if cas_response and cas_response.success:
				try:
					return cortex.lib.user.logon_ok(cas_response.attributes.get('uid'))
				except KeyError:
					#required user attributes not returned fallback to LDAP
					alert("CAS SSO authentication successful but missing information, falling back to LDAP authentication", 'alert-warning')
					return render_template('login.html')
		return redirect(cas_client.get_login_url())

################################################################################

@app.route('/logout')
@cortex.lib.user.login_required
def logout():
	"""Logs a user out"""

	# destroy the session
	cortex.lib.user.clear_session()
	
	# Tell cas about the logout
	return redirect(cas_client.get_logout_url())

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
