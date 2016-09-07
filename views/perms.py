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

	## View list
	if request.method == 'GET':
		# Render the page
		return render_template('perms/role.html', active='perms', title="Role", role=role)

	## Edit role, delete role
	elif request.method == 'POST':
		action = request.form['action']

		# delete  - delete the role
		# edit    - change name/desc of the role
		# grant   - Give the role an additional permission
		# revoke  - Revoke a permission from this role
		# enable  - Give a user this role
		# disable - Revoke from a user this role

		if action == 'delete':
			curd.execute('''DELETE FROM `roles` WHERE `id` = %s''', (id))
			g.db.commit()

			flash("The role `" + role['name'] + "` has been deleted", "alert-success")
			return redirect(url_for('perms_roles'))

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

		elif action == 'grant':
			permission_name = request.form['permission']
			if not re.match(r'^[a-zA-Z0-9\.]{3,255}$', permission_name):
				flash("The permission you entered was invalid. It must only contain letters, numbers or a full stop.", "alert-danger")
				return redirect(url_for('perms_role',id=id))

			# Ensure the permission was not already granted
			curd.execute('SELECT 1 FROM `role_perms` WHERE `role_id` = %s AND `perm` = %s', (id,permission_name))
			if curd.fetchone() is not None:
				flash('That permission is already granted to the role', 'alert-warning')
				return redirect(url_for('perms_role',id=id))

			curd.execute('''INSERT INTO `role_perms` (`role_id`, `perm`) VALUES (%s,%s)''', (id, permission_name))
			g.db.commit()

			flash("Permission " + permission_name + " was added to the role", "alert-success")
			return redirect(url_for('perms_role',id=id))
		elif action == 'revoke':
			pid = request.form['pid']
			if not re.match(r'^[0-9]+$',pid):
				flash("The permission ID you sent was invalid", "alert-danger")
				return redirect(url_for('perms_role',id=id))				
		
			# Ensure the permission was not already granted
			curd.execute('SELECT 1 FROM `role_perms` WHERE `id` = %s', (pid))
			if curd.fetchone() is None:
				flash('That permission is not granted to the role', 'alert-warning')
				return redirect(url_for('perms_role',id=id))

			curd.execute('''DELETE FROM `role_perms` WHERE `id` = %s''', (pid))
			g.db.commit()

			flash("The permission was revoked from the role", "alert-success")
			return redirect(url_for('perms_role',id=id))
		elif action == 'enable':
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


		elif action == 'disable':
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
