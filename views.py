#!/usr/bin/python
#

from cortex import app
import cortex.core
from flask import Flask, request, session, redirect, url_for, flash, g, abort, make_response, render_template
import os 
import time
import json
import re
import werkzeug
import ldap

################################################################################
#### HOME PAGE / LOGIN PAGE

@app.route('/', methods=['GET', 'POST'])
def login():
	if cortex.core.is_user_logged_in():
		return redirect(url_for('dashboard'))
	else:
		if request.method == 'GET' or request.method == 'HEAD':
			next = request.args.get('next',default=None)
			return render_template('login.html', next=next)

		elif request.method == 'POST':
			result = cortex.core.auth_user(request.form['username'], request.form['password'])

			if not result:
				flash('Incorrect username and/or password','alert-danger')
				return redirect(url_for('login'))
			
			## Set the username in the session
			session['username']  = request.form['username'].lower()
			
			## Check if two-factor is enabled for this account
			## TWO STEP LOGONS
			if app.config['TOTP_ENABLED']:
				if cortex.totp.totp_user_enabled(session['username']):
					app.logger.debug('User "' + session['username'] + '" has two step enabled. Redirecting to two-step handler')
					return redirect(url_for('totp_logon_view',next=request.form.get('next',default=None)))

			## Successful logon without 2-step needed
			return cortex.core.logon_ok()


################################################################################
#### LOGOUT

@app.route('/logout')
@cortex.core.login_required
def logout():
	## Log out of the session
	cortex.core.session_logout()
	
	## Tell the user
	flash('You were logged out successfully','alert-success')
	
	## redirect the user to the logon page
	return redirect(url_for('login'))

#### HELP PAGES

@app.route('/about')
def about():
	return render_template('about.html', active='help')

@app.route('/about/changelog')
def changelog():
	return render_template('changelog.html', active='help')

@app.route('/nojs')
def nojs():
	return render_template('nojs.html')
	
@app.route('/test')
def test():
	return render_template('test.html')

@app.route('/dashboard')
def dashboard():
	return render_template('dashboard.html')

@app.route('/systems')
def systems():
	systems = cortex.core.get_systems()
	classes = cortex.core.get_classes(True)
	return render_template('systems.html', systems=systems, classes=classes)

@app.route('/systems/reserve')
def systems_reserve():
	classes = cortex.core.get_classes(True)
	return render_template('systems-reserve.html', classes=classes)

