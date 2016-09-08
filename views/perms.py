#!/usr/bin/python

from cortex import app
import cortex.lib.perms
from cortex.lib.user import does_user_have_permission
from flask import request, session, redirect, url_for, flash, g, abort, render_template
import re
import MySQLdb as mysql

################################################################################

@app.route('/permissions/roles',methods=['GET','POST'])
@cortex.lib.user.login_required
def perms_roles():
	"""View function to let administrators view and manage the list of roles"""

	# Check user permissions
	if not does_user_have_permission("admin.permissions"):
		abort(403)
	
	# Cursor for the DB
	curd = g.db.cursor(mysql.cursors.DictCursor)

	## View list
	if request.method == 'GET':
		# Get the list of roles from the database
		roles = cortex.lib.perms.get_roles()

		# Render the page
		return render_template('perms/roles.html', active='perms', title="Roles", roles=roles)

	## Create new role
	elif request.method == 'POST':

		# Validate class name/prefix
		name = request.form['name']
		if not re.match(r'^[a-zA-Z0-9\s\-\_\'\"\&\@\,\:]{3,64}$', name):
			flash("The name you chose is invalid. It can only contain lowercase letters and be at least 3 characters long and at most 64", "alert-danger")
			return redirect(url_for('perms_roles'))

		# Validate the description
		desc = request.form['description']
		if not re.match(r'^.{3,512}$', desc):
			flash("The description you sent was invalid. It must be between 3 and 512 characters long.", "alert-danger")
			return redirect(url_for('perms_roles'))

		# Check if the class already exists
		curd.execute('SELECT 1 FROM `roles` WHERE `name` = %s;', (name))
		if curd.fetchone() is not None:
			flash('A role already exists with that name', 'alert-danger')
			return redirect(url_for('perms_roles'))

		# SQL insert
		curd.execute('''INSERT INTO `roles` (`name`, `description`) VALUES (%s, %s)''', (name, desc))
		g.db.commit()

		flash("Role created", "alert-success")
		return redirect(url_for('perms_roles'))


################################################################################

@app.route('/permissions/role/<int:id>',methods=['GET','POST'])
@cortex.lib.user.login_required
def perms_role(id):
	"""View function to let administrators view and manage a role"""

	# Check user permissions
	if not does_user_have_permission("admin.permissions"):
		abort(403)
	
	# Cursor for the DB
	curd = g.db.cursor(mysql.cursors.DictCursor)

	# Get the role from the database
	role = cortex.lib.perms.get_role(id)

	# Catch when no role exists
	if role == None:
		abort(404)

	# Build a simple list of all the permissions the role has, for calculating
	# permissions during the view/GET or during updating in a POST
	plist = []
	for perm in role['perms']:
		plist.append(perm['perm'])

	## View list
	if request.method == 'GET':
		# Render the page
		return render_template('perms/role.html', active='perms', title="Role", role=role, perms=app.permissions, wfperms=app.workflow_permissions, rperms=plist)

	## Edit role, delete role
	elif request.method == 'POST':
		action = request.form['action']

		# delete  - delete the role
		# edit    - change name/desc of the role
		# update  - Update the list of permissions 
		# add     - Give a user this role
		# remove  - Revoke from a user this role

		# Delete the role
		if action == 'delete':
			curd.execute('''DELETE FROM `roles` WHERE `id` = %s''', (id))
			g.db.commit()

			flash("The role `" + role['name'] + "` has been deleted", "alert-success")
			return redirect(url_for('perms_roles'))

		# Change the name and/or description of the role
		elif action == 'edit':
			# Validate class name/prefix
			name = request.form['name']
			if not re.match(r'^[a-zA-Z0-9\s\-\_\'\"\&\@\,\:]{3,64}$', name):
				flash("The name you sent was invalid", "alert-danger")
				return redirect(url_for('perms_role',id=id))

			# Validate the description
			desc = request.form['description']
			if not re.match(r'^.{3,512}$', desc):
				flash("The description you sent was invalid. It must be between 3 and 512 characters long.", "alert-danger")
				return redirect(url_for('perms_role',id=id))

			curd.execute('''UPDATE `roles` SET `name` = %s, `description` = %s WHERE `id` = %s''', (name, desc, id))
			g.db.commit()

			flash("Role updated", "alert-success")
			return redirect(url_for('perms_role',id=id))

		elif action == 'update':
			# Loop over all the permissions available, check if it is in the form
			# if it isn't, make sure to delete from the table
			# if it is, make sure it is in the table
			perms = app.permissions + app.workflow_permissions
			changes = 0

			for perm in perms:
				## Check if the role already has this permission or not
				curd.execute('SELECT 1 FROM `role_perms` WHERE `role_id` = %s AND `perm` = %s', (id,perm['name']))
				if curd.fetchone() is None:
					exists = False
				else:
					exists = True

				should_exist = False
				if perm['name'] in request.form:
					if request.form[perm['name']] == 'yes':
						should_exist = True

				if not should_exist and exists:
					curd.execute('''DELETE FROM `role_perms` WHERE `role_id` = %s AND `perm` = %s''', (id, perm['name']))
					g.db.commit()
					changes += 1

				elif should_exist and not exists:
					curd.execute('''INSERT INTO `role_perms` (`role_id`, `perm`) VALUES (%s, %s)''', (id, perm['name']))
					g.db.commit()
					changes += 1

			if changes == 0:
				flash("Permissions were not updated - no changes requested", "alert-warning")
			else:
				flash("Permissions for the role were successfully updated", "alert-success")
			return redirect(url_for('perms_role',id=id))

		## Add a user or group to the role
		elif action == 'add':
			name = request.form['name']
			if not re.match(r'^[a-zA-Z0-9\-\_]{3,255}$', name):
				flash("The user or group name you sent was invalid", "alert-danger")
				return redirect(url_for('perms_role',id=id))

			ptype = request.form['type']
			if not re.match(r'^[0-9]+$',ptype):
				flash("The type you sent was invalid", "alert-danger")
				return redirect(url_for('perms_role',id=id))
			else:
				ptype = int(ptype)

			if ptype not in [0, 1]:
				flash("The type you sent was invalid", "alert-danger")
				return redirect(url_for('perms_role',id=id))

			if ptype == 0:
				hstr = "user"
			elif ptype == 1:
				hstr = "group"

			# Ensure the user/group combo was not already added
			curd.execute('SELECT 1 FROM `role_who` WHERE `role_id` = %s AND `who` = %s AND `type` = %s', (id,name,ptype))
			if curd.fetchone() is not None:
				flash('That user/group is already added to the role', 'alert-warning')
				return redirect(url_for('perms_role',id=id))

			curd.execute('''INSERT INTO `role_who` (`role_id`, `who`, `type`) VALUES (%s, %s, %s)''', (id, name, ptype))
			g.db.commit()

			flash("The " + hstr + " " + name + " was added to the role", "alert-success")
			return redirect(url_for('perms_role',id=id))

		## Remove a user or group from the role
		elif action == 'remove':
			wid = request.form['wid']
			if not re.match(r'^[0-9]+$',wid):
				flash("The user/group ID you sent was invalid", "alert-danger")
				return redirect(url_for('perms_role',id=id))
		
			# Ensure the permission was not already granted
			curd.execute('SELECT 1 FROM `role_who` WHERE `id` = %s', (wid))
			if curd.fetchone() is None:
				flash('That user/group is not added to the role', 'alert-warning')
				return redirect(url_for('perms_role',id=id))

			curd.execute('''DELETE FROM `role_who` WHERE `id` = %s''', (wid))
			g.db.commit()

			flash("The user or group was revoked from the role", "alert-success")
			return redirect(url_for('perms_role',id=id))
		else:
			abort(400)
