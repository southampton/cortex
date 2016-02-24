#!/usr/bin/python

from cortex import app
import cortex.lib.user
from flask import Flask, request, session, redirect, url_for, flash, g, abort, render_template
import re

@app.route('/', methods=['GET', 'POST'])
def login():
	if cortex.lib.user.is_logged_in():
		return redirect(url_for('dashboard'))
	else:
		if request.method == 'GET' or request.method == 'HEAD':
			next = request.args.get('next',default=None)
			return render_template('login.html', next=next)

		elif request.method == 'POST':
			result = cortex.lib.user.authenticate(request.form['username'], request.form['password'])

			if not result:
				flash('Incorrect username and/or password','alert-danger')
				return redirect(url_for('login'))
			
			## Set the username in the session
			session['username']  = request.form['username'].lower()

			## Permanent sessions
			permanent = request.form.get('sec',default="")

			## Set session as permanent or not
			if permanent == 'sec':
				session.permanent = True
			else:
				session.permanent = False
			
			## restrict all logons to admins
			if cortex.lib.user.is_global_admin(session['username']):
				return cortex.lib.user.logon_ok()
			else:
				flash('Permission denied','alert-danger')
				return redirect(url_for('login'))

################################################################################

@app.route('/logout')
@cortex.lib.user.login_required
def logout():
	## Log out of the session
	cortex.lib.user.clear_session()
	
	## Tell the user
	flash('You were logged out successfully','alert-success')
	
	## redirect the user to the logon page
	return redirect(url_for('login'))

################################################################################

@app.route('/user/groups')
@cortex.lib.user.login_required
def user_groups():
	ldap_groups = cortex.lib.user.get_users_groups(session['username'])
	groups = []

	for lgroup in ldap_groups:
		p = re.compile("^(cn|CN)=([^,;]+),")
		matched = p.match(lgroup)
		if matched:
			name = matched.group(2)
			groups.append({"name": name, "dn": lgroup})
	

	return render_template('user-groups.html', active='user', groups=groups, title="AD Groups")
