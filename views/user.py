#!/usr/bin/python

from cortex import app
import cortex.lib.user
import cortex.lib.core
from flask import Flask, request, session, redirect, url_for, flash, g, abort, render_template
import re
from cas_client import CASClient

################################################ DEBUG, remove when done
from flask import jsonify


################################################################################

@app.route('/', methods=['GET', 'POST'])
@app.disable_csrf_check
def root():
	# If the user is already logged in, just redirect them to their dashboard
	if cortex.lib.user.is_logged_in():
		return redirect(url_for('dashboard'))
	else:
		if app.config['DEFAULT_USER_AUTH'] == 'cas':
			return cas()
		else:
			return login()

###############################################################################

@app.route('/login', methods=['GET', 'POST'])
def login():
	if request.method == 'POST':
		if all(field in request.form for field in ['username', 'password']):
			result = cortex.lib.user.authenticate(request.form['username'], request.form['password'])

			if not result:
				flash('Incorrect username and/or password', 'alert-danger')
				# Do we want this? Could fill up the database volume (DoS)
				#cortex.lib.core.log(__name__, 'Login failure: incorrect username/password', request.form['username'].lower())
				return redirect(url_for('login'))

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
	return render_template('login.html')

###############################################################################


@app.route('/cas', methods=['GET', 'POST'])
@app.disable_csrf_check
def cas():
	"""Handles the login page, logging a user in on correct authentication."""

	#CAS client init
	cas_client = CASClient(app.config['CAS_SERVER_URL'], app.config['CAS_SERVICE_URL'], verify_certificates=True)

	#SLO
	if request.method == 'POST' and session.get('cas_ticket') is not None and 'logoutRequest' in request.form:
		#check the verify the ticket to prevent cross orign attacks
		message = cas_client.parse_logout_request(request.form.get('logoutRequest'))
		if message.get('session_index', None) == session.get('cas_ticket'):
			cortex.lib.user.clear_session()
			return ('', 200)
		else:
			abort(400)


	# If the user is already logged in, just redirect them to their dashboard
	if cortex.lib.user.is_logged_in():
		return redirect(url_for('dashboard'))

	ticket = request.args.get('ticket', None)
	if ticket is not None:
		try:
			cas_response = cas_client.perform_service_validate(ticket=ticket)
		except:
			return root()
		if cas_response and cas_response.success:
			try:
				# keep the ticket for SLO
				session['cas_ticket'] = ticket
				return cortex.lib.user.logon_ok(cas_response.attributes.get('uid'))
			except KeyError:
				# required user attributes not returned
				flash("CAS SSO authentication successful but missing required information consider using LDAP authentication", 'alert-warning')
				return root()

	return redirect(cas_client.get_login_url())

################################################################################

@app.route('/logout')
@cortex.lib.user.login_required
def logout():
	"""Logs a user out"""

	#CAS client init
	cas_client = CASClient(app.config['CAS_SERVER_URL'], app.config['CAS_SERVICE_URL'], verify_certificates=True)

	# destroy the session
	cas_ticket = session.get('cas_ticket', None)
	cortex.lib.user.clear_session()

	if cas_ticket is not None:
		# Tell cas about the logout
		return redirect(cas_client.get_logout_url())
	else:
		return login()

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
		# if they dont want the classic layout then don't store a preference at all
		g.redis.delete("user:" + session['username'] + ":preferences:interface:layout")

	theme = 'default'
	if 'theme' in request.form:
		if request.form['theme'] == "dark":
			theme = "dark"
			
	if theme == 'dark':
		g.redis.set("user:" + session['username'] + ":preferences:interface:theme","dark")
	else:
		# if they dont want a different theme then don't store a preference at all
		g.redis.delete("user:" + session['username'] + ":preferences:interface:theme")

	sidebar_expand = False
	if 'sidebar_expand' in request.form and request.form['sidebar_expand'] == 'yes':
		g.redis.set('user:' + session['username'] + ':preferences:interface:sidebar', 'expand')
	else:
		g.redis.delete('user:' + session['username'] + ':preferences:interface:sidebar')
	

	# return jsonify({'a':session['username']})
	flash("Your preferences have been saved","alert-success")
	return redirect(url_for('dashboard'))
