
import MySQLdb as mysql
from flask import abort, flash, g, jsonify, render_template, request, session

import cortex.lib.user
from cortex import app
from cortex.lib.user import does_user_have_permission

################################################################################

@app.route('/favourites', methods=['GET'])
@cortex.lib.user.login_required
def favourites(display='all'):

	# Check user permissions
	if not (does_user_have_permission("systems.all.view") or does_user_have_permission("systems.own.view")):
		abort(403)

	# Get the list of active classes (used to populate the tab bar)
	classes = {}
	if does_user_have_permission("systems.all.view"):
		classes = cortex.lib.classes.list()

	# Validate system type
	flag = False
	if classes and display != 'all':
		for c in classes:
			if display == c["name"]:
				flag = True
				break
	else:
		flag = True

	if not flag:
		flash('System type %s does not exist.'%(display), category='alert-info')
		display = 'all'

	# Get the search string, if any
	q = request.args.get('q', None)

	# Strip any leading and or trailing spaces
	if q is not None:
		q = q.strip()

	# Render
	return render_template('systems/list.html', classes=classes, active='favourites', title="Favourites", favourites=1, q=q, hide_inactive=False, display=display)

################################################################################

@app.route('/favourites/<string:system_type>', methods=['GET'])
@cortex.lib.user.login_required
def favourites_by_type(system_type):
	return favourites(system_type)

################################################################################

@app.route('/favourites', methods=['POST'])
@cortex.lib.user.login_required
def favourites_json():
	"""
	Add / Remove a system from your favourites.
	"""
	if all(field in request.form for field in ['system_id', 'status']):

		try:
			system_id = int(request.form["system_id"])
		except ValueError:
			abort(400)
		else:

			# Get a cursor to the database
			curd = g.db.cursor(mysql.cursors.DictCursor)

			if request.form["status"] == "1":
				curd.execute("INSERT INTO `system_user_favourites` (`username`, `system_id`) VALUES (%s, %s) ON DUPLICATE KEY UPDATE `system_id`=`system_id`", (session.get('username'), system_id))
			else:
				curd.execute("DELETE FROM `system_user_favourites` WHERE `username` = %s AND `system_id` = %s", (session.get('username'), system_id))
			
			g.db.commit()

			return jsonify({"success":True})
	else:
		abort(400)
