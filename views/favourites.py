
import MySQLdb as mysql
from flask import abort, flash, g, jsonify, render_template, request, session

import cortex.lib.user
from cortex import app
from cortex.lib.user import does_user_have_permission

################################################################################

@app.route('/favourites')
@app.route('/favourites/<string:system_type>')
@cortex.lib.user.login_required
def favourites(system_type='all'):

	# Check user permissions
	if not (does_user_have_permission("systems.all.view") or does_user_have_permission("systems.own.view")):
		abort(403)

	# Get the list of active classes (used to populate the tab bar)
	classes = {}
	if does_user_have_permission("systems.all.view"):
		classes = cortex.lib.classes.get_list()

	if system_type != "all" and system_type not in [class_obj["name"] for class_obj in classes]:
		flash("system type {} does not exist.".format(system_type), category="alert-info")

	# Get the search string, if any and strip
	query = request.args["q"].strip() if request.args.get("q", None) is not None else None

	# Render
	return render_template('systems/list.html', classes=classes, active='favourites', title="Favourites", favourites=1, q=query, hide_inactive=False, display=system_type)

################################################################################

@app.route('/favourites', methods=['POST'])
@cortex.lib.user.login_required
def favourites_json():
	"""
	Add / Remove a system from your favourites.
	"""
	if not all(field in request.form for field in ['system_id', 'status']):
		abort(400)

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
