#!/usr/bin/python


from cortex import app
import cortex.lib.user
from cortex.lib.user import does_user_have_permission
from flask import g, render_template, session, request
import MySQLdb as mysql

@app.route('/favourites')
@cortex.lib.user.login_required
def favourites():

	# Check user permissions
	if not (does_user_have_permission("systems.all.view") or does_user_have_permission("systems.own.view")):
		abort(403)

	# Get the list of active classes (used to populate the tab bar)
	classes = {}
	if does_user_have_permission("systems.all.view"):
		classes = cortex.lib.classes.list()

	# Get the search string, if any
	q = request.args.get('q', None)

	# Strip any leading and or trailing spaces
	if q is not None:
		q = q.strip()

	# Render
	return render_template('favourites.html', classes=classes, active='favourites', title="Favourites", q=q, hide_inactive=False)

