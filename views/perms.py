
from cortex import app
import cortex.lib.perms
import cortex.lib.user
import cortex.lib.systems
import cortex.lib.core
from cortex.lib.user import does_user_have_permission
from flask import request, session, redirect, url_for, flash, g, abort, render_template, jsonify
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
		return render_template('perms/roles.html', active='perms', title="Roles", roles=roles, manage_role_route='perms_role')

	## Create new role
	elif request.method == 'POST':

		# Validate class name/prefix
		name = request.form['name']
		if len(name) < 3 or len(name) > 64:
			flash('The name you chose is invalid. It must be between 3 and 64 characters long.', 'alert-danger')
			return redirect(url_for('perms_roles'))

		# Validate the description
		desc = request.form['description']
		if len(desc) < 3 or len(desc) > 512:
			flash('The description you chose was invalid. It must be between 3 and 512 characters long.', 'alert-danger')
			return redirect(url_for('perms_roles'))

		# Check if the class already exists
		curd.execute('SELECT 1 FROM `roles` WHERE `name` = %s;', (name,))
		if curd.fetchone() is not None:
			flash('A role already exists with that name', 'alert-danger')
			return redirect(url_for('perms_roles'))

		# SQL insert
		curd.execute('''INSERT INTO `roles` (`name`, `description`) VALUES (%s, %s)''', (name, desc))
		g.db.commit()
		cortex.lib.core.log(__name__, "permissions.role.create", "Permission role '" + name + "' created")

		flash("Role created", "alert-success")
		return redirect(url_for('perms_roles'))


################################################################################

@app.route('/permissions/system/roles',methods=['GET','POST'])
@cortex.lib.user.login_required
def system_perms_roles():

	# Check user permissions
	if not does_user_have_permission("admin.permissions"):
		abort(403)

	# Cursor for the DB
	curd = g.db.cursor(mysql.cursors.DictCursor)

	## View list
	if request.method == 'GET':
		# Get the list of roles from the database
		roles = cortex.lib.perms.get_system_roles()

		# Render the page
		return render_template('perms/roles.html', active='perms', title="System Roles", roles=roles, manage_role_route='system_perms_role')
	
	## Create new role
	elif request.method == 'POST':

		# Validate role name/prefix
		name = request.form['name']
		if len(name) < 3 or len(name) > 64:
			flash('The name you chose is invalid. It must be between 3 and 64 characters long.', 'alert-danger')
			return redirect(url_for('system_perms_roles'))

		# Validate the description
		desc = request.form['description']
		if len(desc) < 3 or len(desc) > 512:
			flash('The description you chose was invalid. It must be between 3 and 512 characters long.', 'alert-danger')
			return redirect(url_for('system_perms_roles'))

		# Check if the class already exists
		curd.execute('SELECT 1 FROM `system_roles` WHERE `name` = %s;', (name,))
		if curd.fetchone() is not None:
			flash('A role already exists with that name', 'alert-danger')
			return redirect(url_for('system_perms_roles'))

		# SQL insert
		curd.execute("INSERT INTO `system_roles` (`name`, `description`) VALUES (%s, %s)", (name, desc))
		g.db.commit()
		cortex.lib.core.log(__name__, "permissions.system.role.create", "Permission system role '" + name + "' created")

		flash("System Role created", "alert-success")
		return redirect(url_for('system_perms_roles'))

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
			curd.execute('''DELETE FROM `roles` WHERE `id` = %s''', (id,))
			g.db.commit()

			cortex.lib.core.log(__name__, "permissions.role.delete", "Role '" + role['name'] + "' (" + str(id) + ")" + " deleted")
			flash("The role `" + role['name'] + "` has been deleted", "alert-success")
			return redirect(url_for('perms_roles'))

		# Change the name and/or description of the role
		elif action == 'edit':
			# Validate class name/prefix
			name = request.form['name']
			if len(name) < 3 or len(name) > 64:
				flash('The name you chose was invalid. It must be between 3 and 64 characters long.', 'alert-danger')
				return redirect(url_for('perms_role', id=id))

			# Validate the description
			desc = request.form['description']
			if len(desc) < 3 or len(desc) > 512:
				flash('The description you chose was invalid. It must be between 3 and 512 characters long.', 'alert-danger')
				return redirect(url_for('perms_role', id=id))

			curd.execute('''UPDATE `roles` SET `name` = %s, `description` = %s WHERE `id` = %s''', (name, desc, id))
			g.db.commit()
			cortex.lib.core.log(__name__, "permissions.role.edit", "Role '" + role['name'] + "' (" + str(id) + ")" + " name/description edited")

			flash("Role updated", "alert-success")
			return redirect(url_for('perms_role', id=id))

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
					cortex.lib.core.log(__name__, "permissions.role.revoke", "Permission '" + perm['name'] + "' removed from role '" + role['name'] + "' (" + str(id) + ")")
					changes += 1

				elif should_exist and not exists:
					curd.execute('''INSERT INTO `role_perms` (`role_id`, `perm`) VALUES (%s, %s)''', (id, perm['name']))
					g.db.commit()
					cortex.lib.core.log(__name__, "permissions.role.grant", "Permission '" + perm['name'] + "' added to role '" + role['name'] + "' (" + str(id) + ")")
					changes += 1

			if changes == 0:
				flash("Permissions were not updated - no changes requested", "alert-warning")
			else:
				flash("Permissions for the role were successfully updated", "alert-success")

			return redirect(url_for('perms_role', id=id))

		## Add a user or group to the role
		elif action == 'add':
			name = request.form['name']
			if not re.match(r'^[a-zA-Z0-9\-\_]{3,255}$', name):
				flash("The user or group name you sent was invalid", "alert-danger")
				return redirect(url_for('perms_role', id=id))

			ptype = request.form['type']
			if not re.match(r'^[0-9]+$',ptype):
				flash("The type you sent was invalid", "alert-danger")
				return redirect(url_for('perms_role', id=id))
			else:
				ptype = int(ptype)

			if ptype not in [0, 1]:
				flash("The type you sent was invalid", "alert-danger")
				return redirect(url_for('perms_role', id=id))

			if ptype == 0:
				hstr = "user"

				if not cortex.lib.user.does_user_exist(name):
					flash("The username you sent does not exist", "alert-danger")
					return redirect(url_for('perms_role', id=id))

			elif ptype == 1:
				hstr = "group"

				if not cortex.lib.ldapc.does_group_exist(name):
					flash("The Active Directory group you specified does not exist", "alert-danger")
					return redirect(url_for('perms_role', id=id))

			# Ensure the user/group combo was not already added
			curd.execute('SELECT 1 FROM `role_who` WHERE `role_id` = %s AND `who` = %s AND `type` = %s', (id,name,ptype))
			if curd.fetchone() is not None:
				flash('That user/group is already added to the role', 'alert-warning')
				return redirect(url_for('perms_role', id=id))

			curd.execute('''INSERT INTO `role_who` (`role_id`, `who`, `type`) VALUES (%s, %s, %s)''', (id, name, ptype))
			g.db.commit()
			cortex.lib.core.log(__name__, "permissions.role.member.add", hstr + " '" + name + "' added to role '" + role['name'] + "' (" + str(id) + ")")

			flash("The " + hstr + " " + name + " was added to the role", "alert-success")
			return redirect(url_for('perms_role', id=id))

		## Remove a user or group from the role
		elif action == 'remove':
			wid = request.form['wid']
			if not re.match(r'^[0-9]+$',wid):
				flash("The user/group ID you sent was invalid", "alert-danger")
				return redirect(url_for('perms_role', id=id))

			# Ensure the permission was not already granted
			curd.execute('SELECT `who` FROM `role_who` WHERE `id` = %s', (wid,))
			who_row = curd.fetchone()
			if who_row is None:
				flash('That user/group is not added to the role', 'alert-warning')
				return redirect(url_for('perms_role', id=id))

			curd.execute('''DELETE FROM `role_who` WHERE `id` = %s''', (wid,))
			g.db.commit()
			cortex.lib.core.log(__name__, "permissions.role.member.remove", "The user/group '" + who_row['who'] + "' was removed from role '" + role['name'] + "' (" + str(id) + ")")

			flash("The user or group was revoked from the role", "alert-success")
			return redirect(url_for('perms_role', id=id))
		else:
			abort(400)


################################################################################

@app.route('/permissions/system/role/<int:id>',methods=['GET','POST'])
@cortex.lib.user.login_required
def system_perms_role(id):
	"""View function to let administrators view and manage a role"""
	
	# Check user permissions
	if not does_user_have_permission("admin.permissions"):
		abort(403)

	# Cursor for the DB
	curd = g.db.cursor(mysql.cursors.DictCursor)

	# Get the system role from the database
	role = cortex.lib.perms.get_system_role(id)

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

		systems = cortex.lib.systems.get_systems(order='id', order_asc=False) 

		# Render the page
		return render_template('perms/role.html', active='perms', title="System Role", role=role, system_perms=app.system_permissions, rperms=plist, systems=systems)

	## Edit role, delete role
	elif request.method == 'POST':
		action = request.form['action']

		# delete        - delete the role
		# edit          - change name/desc of the role
		# update        - Update the list of permissions 
		# add           - Give a user this role
		# remove        - Revoke from a user this role
		# add_system    - Add a system to this role.
		# remove_system - Remove a system from this role.

		# Delete the role
		if action == 'delete':
			curd.execute('''DELETE FROM `system_roles` WHERE `id` = %s''', (id,))
			g.db.commit()

			cortex.lib.core.log(__name__, "permissions.system.role.delete", "Role '" + role['name'] + "' (" + str(id) + ")" + " deleted")
			flash("The system role `" + role['name'] + "` has been deleted", "alert-success")
			return redirect(url_for('system_perms_roles'))

		# Change the name and/or description of the role
		elif action == 'edit':
			# Validate class name/prefix
			name = request.form['name']
			if len(name) < 3 or len(name) > 64:
				flash('The name you chose is invalid. It must be between 3 and 64 characters long.', 'alert-danger')
				return redirect(url_for('system_perms_role', id=id))

			# Validate the description
			desc = request.form['description']
			if len(desc) < 3 or len(desc) > 512:
				flash('The description you chose was invalid. It must be between 3 and 512 characters long.', 'alert-danger')
				return redirect(url_for('system_perms_role', id=id))

			curd.execute('''UPDATE `system_roles` SET `name` = %s, `description` = %s WHERE `id` = %s''', (name, desc, id))
			g.db.commit()
			cortex.lib.core.log(__name__, "permissions.system.role.edit", "Role '" + role['name'] + "' (" + str(id) + ")" + " name/description edited")

			flash("System Role updated", "alert-success")
			return redirect(url_for('system_perms_role', id=id))

		elif action == 'update':
			# Loop over all the permissions available, check if it is in the form
			# if it isn't, make sure to delete from the table
			# if it is, make sure it is in the table
			perms = app.system_permissions
			changes = 0

			for perm in perms:
				## Check if the role already has this permission or not
				curd.execute('SELECT 1 FROM `system_role_perms` WHERE `system_role_id` = %s AND `perm` = %s', (id,perm['name']))
				if curd.fetchone() is None:
					exists = False
				else:
					exists = True

				should_exist = False
				if perm['name'] in request.form:
					if request.form[perm['name']] == 'yes':
						should_exist = True

				if not should_exist and exists:
					curd.execute('''DELETE FROM `system_role_perms` WHERE `system_role_id` = %s AND `perm` = %s''', (id, perm['name']))
					g.db.commit()
					cortex.lib.core.log(__name__, "permissions.system.role.revoke", "Permission '" + perm['name'] + "' removed from system role '" + role['name'] + "' (" + str(id) + ")")
					changes += 1

				elif should_exist and not exists:
					curd.execute('''INSERT INTO `system_role_perms` (`system_role_id`, `perm`) VALUES (%s, %s)''', (id, perm['name']))
					g.db.commit()
					cortex.lib.core.log(__name__, "permissions.system.role.grant", "Permission '" + perm['name'] + "' added to system role '" + role['name'] + "' (" + str(id) + ")")
					changes += 1

			if changes == 0:
				flash("Permissions were not updated - no changes requested", "alert-warning")
			else:
				flash("Permissions for the system role were successfully updated", "alert-success")
			return redirect(url_for('system_perms_role', id=id))

		## Add a user or group to the role
		elif action == 'add':
			name = request.form['name']
			if not re.match(r'^[a-zA-Z0-9\-\_]{3,255}$', name):
				flash("The user or group name you sent was invalid", "alert-danger")
				return redirect(url_for('system_perms_role', id=id))

			ptype = request.form['type']
			if not re.match(r'^[0-9]+$',ptype):
				flash("The type you sent was invalid", "alert-danger")
				return redirect(url_for('system_perms_role', id=id))
			else:
				ptype = int(ptype)

			if ptype not in [0, 1]:
				flash("The type you sent was invalid", "alert-danger")
				return redirect(url_for('system_perms_role', id=id))

			if ptype == 0:
				hstr = "user"

				if not cortex.lib.user.does_user_exist(name):
					flash("The username you sent does not exist", "alert-danger")
					return redirect(url_for('system_perms_role', id=id))

			elif ptype == 1:
				hstr = "group"

				if not cortex.lib.ldapc.does_group_exist(name):
					flash("The Active Directory group you specified does not exist", "alert-danger")
					return redirect(url_for('system_perms_role', id=id))

			# Ensure the user/group combo was not already added
			curd.execute('SELECT 1 FROM `system_role_who` WHERE `system_role_id` = %s AND `who` = %s AND `type` = %s', (id,name,ptype))
			if curd.fetchone() is not None:
				flash('That user/group is already added to the system role', 'alert-warning')
				return redirect(url_for('system_perms_role', id=id))

			curd.execute('''INSERT INTO `system_role_who` (`system_role_id`, `who`, `type`) VALUES (%s, %s, %s)''', (id, name, ptype))
			g.db.commit()
			cortex.lib.core.log(__name__, "permissions.system.role.member.add", hstr + " '" + name + "' added to system role '" + role['name'] + "' (" + str(id) + ")")

			flash("The " + hstr + " " + name + " was added to the system role", "alert-success")
			return redirect(url_for('system_perms_role', id=id))

		## Remove a user or group from the role
		elif action == 'remove':
			wid = request.form['wid']
			if not re.match(r'^[0-9]+$',wid):
				flash("The user/group ID you sent was invalid", "alert-danger")
				return redirect(url_for('system_perms_role', id=id))

			# Ensure the permission was not already granted
			curd.execute('SELECT `who` FROM `system_role_who` WHERE `id` = %s', (wid,))
			who_row = curd.fetchone()
			if who_row is None:
				flash('That user/group is not added to the system role', 'alert-warning')
				return redirect(url_for('system_perms_role', id=id))

			curd.execute('''DELETE FROM `system_role_who` WHERE `id` = %s''', (wid,))
			g.db.commit()
			cortex.lib.core.log(__name__, "permissions.system.role.member.remove", "The user/group '" + who_row['who'] + "' was removed from system role '" + role['name'] + "' (" + str(id) + ")")

			flash("The user or group was revoked from the system role", "alert-success")
			return redirect(url_for('system_perms_role', id=id))

		## Add a system to the role.
		elif action == 'add_system':
			name = request.form['name']
			if not re.match(r'^[a-zA-Z0-9\-\_]{3,255}$', name):
				flash("The system name you sent was invalid", "alert-danger")
				return redirect(url_for('system_perms_role', id=id))

			# Get the system.
			system = cortex.lib.systems.get_system_by_name(name)
			if system is None:
				flash('The system you sent does not exist.', 'alert-danger')
				return redirect(url_for('system_perms_role', id=id))

			# Ensure the system isn't already added.
			curd.execute("SELECT 1 FROM `system_role_what` WHERE `system_role_id`=%s and `system_id`=%s", (id, system['id']))
			if curd.fetchone() is not None:
				flash('That system has already been added to the system role.')
				return redirect(url_for('system_perms_role', id=id))

			# Add the system.
			curd.execute("INSERT INTO `system_role_what` (`system_role_id`, `system_id`) VALUES (%s, %s);", (id, system['id']))
			g.db.commit()
			cortex.lib.core.log(__name__, "permissions.system.role.system.add", "The system '" + system['name'] + "' (" + str(system['id']) + ") was added to the system role '" + role['name'] + "' (" + str(id) + ")")

			flash("The system was added from the system role", "alert-success")
			return redirect(url_for('system_perms_role', id=id))

		## Remove a system from this role.
		elif action == 'remove_system':
			sid = request.form['sid']
			if not re.match(r'^[0-9]+$',sid):
				flash("The system ID you sent was invalid", "alert-danger")
				return redirect(url_for('system_perms_role', id=id))

			# Ensure this system is attached to this role.
			curd.execute("SELECT 1 FROM `system_role_what` WHERE `system_role_id`=%s AND `system_id`=%s", (id, sid))
			what_row = curd.fetchone()
			if what_row is None:
				flash('That system is not added to the system role', 'alert-warning')
				return redirect(url_for('system_perms_role', id=id))
				
			curd.execute("DELETE FROM `system_role_what` WHERE `system_role_id`=%s AND `system_id`=%s", (id, sid))
			g.db.commit()
			cortex.lib.core.log(__name__, "permissions.system.role.system.remove", "System ID '" + str(sid) + "'was removed from the system role '" + role['name'] + "' (" + str(id) + ")")

			flash("The system was removed from the system role", "alert-success")
			return redirect(url_for('system_perms_role', id=id))

		else:
			abort(400)


################################################################################

@app.route('/permissions/system/<int:id>',methods=['GET','POST'])
@cortex.lib.user.login_required
def perms_system(id):
	"""View function to let administrators view and manage a role"""

	# Check user permissions
	if not does_user_have_permission("admin.permissions"):
		abort(403)

	# Get the system
	system = cortex.lib.systems.get_system_by_id(id)

	# Ensure that the system actually exists, and return a 404 if it doesn't
	if system is None:
		abort(404)

	# Cursor for the DB
	curd = g.db.cursor(mysql.cursors.DictCursor)

	if request.method == 'GET':

		system_perms = []

		# Get the list of distinct users/groups/etc added to this system explicitly
		curd.execute('SELECT DISTINCT `type`, `who` FROM `system_perms` WHERE `system_id` = %s', (system['id'],))
		results = curd.fetchall()

		for entry in results:
			# Get perms for this system/user/type combo
			curd.execute('SELECT `perm` FROM `system_perms` WHERE `system_id` = %s AND `who` = %s AND `type` = %s', (system['id'], entry['who'], entry['type']))
			perms = curd.fetchall()

			# Create a object to add to the system_perms list.
			obj = {
				'who': entry['who'],
				'type': entry['type'],
				'is_editable': True,
				'perms': [p['perm'] for p in perms]
			}

			# Add the constructed object to the system_perms list.
			system_perms.append(obj)

		# Get the list of distinct users/groups/etc added to this system via a system role.
		curd.execute('SELECT DISTINCT `system_role_id`, `system_role_name`, `type`, `who` FROM `system_role_perms_view` WHERE `system_id` = %s', (system['id'],))
		results = curd.fetchall()
		
		for entry in results:
			# Get perms for this system/user/type combo
			curd.execute('SELECT `perm` FROM `system_role_perms_view` WHERE `system_id` = %s AND `who` = %s AND `type` = %s and `system_role_id`=%s and `system_role_name`=%s', (system['id'], entry['who'], entry['type'], entry['system_role_id'], entry['system_role_name']))
			perms = curd.fetchall()

			# Create a object to add to the system_perms list.
			obj = {
				'who': entry['who'],
				'type': entry['type'],
				'is_editable': False, # System Role Perms cannot be edited here!!
				'system_role_id': entry['system_role_id'],
				'system_role_name': entry['system_role_name'],
				'perms': [p['perm'] for p in perms]
			}

			# Add the constructed object to the system_perms list.
			system_perms.append(obj)

		return render_template('perms/system.html', active='systems', title="Server permissions", system=system, system_perms=system_perms, sysperms=app.system_permissions)		

	else:
		action = request.form['action']

		## Make changes to an existing user/group
		if action == 'edit':

			## Get the 'who' and the 'type'
			who   = request.form['who']
			wtype = request.form['type']

			# Loop over all the per-system permissions available. Check if the 
			# permission is in the form data sent by the browser.
			# if it isn't, make sure to delete from the table
			# if it is, make sure it is in the table
			changes = 0

			for perm in app.system_permissions:
				## Check if the role already has this permission or not
				curd.execute('SELECT 1 FROM `system_perms` WHERE `system_id` = %s AND `who` = %s AND `type` = %s AND `perm` = %s', (id,who,wtype,perm['name']))
				if curd.fetchone() is None:
					exists = False
				else:
					exists = True

				should_exist = False
				if perm['name'] in request.form:
					if request.form[perm['name']] == 'yes':
						should_exist = True

				if not should_exist and exists:
					curd.execute('''DELETE FROM `system_perms` WHERE `system_id` = %s AND `who` = %s AND `type` = %s AND `perm` = %s''', (id, who, wtype, perm['name']))
					g.db.commit()
					if wtype == 0:
						cortex.lib.core.log(__name__, "permissions.system.revoke.user", "System permission '" + perm['name'] + "' revoked for user '" + who + "' on system " + str(id))
					else:
						cortex.lib.core.log(__name__, "permissions.system.revoke.group", "System permission '" + perm['name'] + "' revoked for group '" + who + "' on system " + str(id))
					changes += 1

				elif should_exist and not exists:
					curd.execute('''INSERT INTO `system_perms` (`system_id`, `who`, `type`, `perm`) VALUES (%s, %s, %s, %s)''', (id, who, wtype, perm['name']))
					g.db.commit()
					if wtype == 0:
						cortex.lib.core.log(__name__, "permissions.system.grant.user", "System permission '" + perm['name'] + "' granted for user '" + who + "' on system " + str(id))
					else:
						cortex.lib.core.log(__name__, "permissions.system.grant.group", "System permission '" + perm['name'] + "' granted for group '" + who + "' on system " + str(id))
					changes += 1

			if changes == 0:
				flash("Permissions were not updated - no changes requested", "alert-warning")
			else:
				flash("Permissions for the system were successfully updated", "alert-success")
			return redirect(url_for('perms_system', id=id))

		elif action == 'add':
			name = request.form['name']
			if not re.match(r'^[a-zA-Z0-9\-\_&]{3,255}$', name):
				flash("The user or group name you sent was invalid", "alert-danger")
				return redirect(url_for('perms_system', id=id))

			wtype = request.form['type']
			if not re.match(r'^[0-9]+$',wtype):
				flash("The type you sent was invalid", "alert-danger")
				return redirect(url_for('perms_system', id=id))
			else:
				wtype = int(wtype)

			if wtype not in [0, 1]:
				flash("The type you sent was invalid", "alert-danger")
				return redirect(url_for('perms_system', id=id))

			if wtype == 0:
				hstr = "user"

				if not cortex.lib.user.does_user_exist(name):
					flash("The username you specified does not exist", "alert-danger")
					return redirect(url_for('perms_system', id=id))

			elif wtype == 1:
				hstr = "group"

				if not cortex.lib.ldapc.does_group_exist(name):
					flash("The Active Directory group you specified does not exist", "alert-danger")
					return redirect(url_for('perms_system', id=id))

			## Check the user/group/type combo doesn't already exist
			curd.execute('SELECT 1 FROM `system_perms` WHERE `system_id` = %s AND `who` = %s AND `type` = %s', (id,name,wtype))
			if curd.fetchone() is not None:
				flash('That user/group is already added to the system, please select it from the list below and change permissions as required', 'alert-warning')
				return redirect(url_for('perms_system', id=id))

			changes = 0

			## Now loop over the per-system permissions available to us
			for perm in app.system_permissions:
				## If the form has the checkbox for this perm checked...
				if perm['name'] in request.form:
					if request.form[perm['name']] == 'yes':
						## Insert the permission for this name/type/perm combo
						changes = changes + 1
						curd.execute('''INSERT INTO `system_perms` (`system_id`, `who`, `type`, `perm`) VALUES (%s, %s, %s, %s)''', (id, name, wtype, perm['name']))
						g.db.commit()
						if wtype == 0:
							cortex.lib.core.log(__name__, "permissions.system.grant.user", "System permission '" + perm['name'] + "' granted for user '" + name + "' on system " + str(id))
						else:
							cortex.lib.core.log(__name__, "permissions.system.grant.group", "System permission '" + perm['name'] + "' granted for group '" + name + "' on system " + str(id))

			if changes == 0:
				flash("The " + hstr + " " + name + " was not added because no permissions were selected", "alert-danger")
			else:
				flash("The " + hstr + " " + name + " was added to the system", "alert-success")
			return redirect(url_for('perms_system', id=id))

		elif action == 'remove':
			name = request.form['name']
			if not re.match(r'^[a-zA-Z0-9\-\_&]{3,255}$', name):
				flash("The user or group name you sent was invalid", "alert-danger")
				return redirect(url_for('perms_system', id=id))

			wtype = request.form['type']
			if not re.match(r'^[0-9]+$',wtype):
				flash("The type you sent was invalid", "alert-danger")
				return redirect(url_for('perms_system', id=id))
			else:
				wtype = int(wtype)

			if wtype not in [0, 1]:
				flash("The type you sent was invalid", "alert-danger")
				return redirect(url_for('perms_system', id=id))

			if wtype == 0:
				hstr = "user"
			elif wtype == 1:
				hstr = "group"

			curd.execute('''DELETE FROM `system_perms` WHERE `system_id` = %s AND `who` = %s AND `type` = %s''', (id, name, wtype))
			g.db.commit()
			cortex.lib.core.log(__name__, "permissions.system.purge", "System permissions purged for " + hstr + " '" + name + "' on system " + str(id))

			flash("The " + hstr + " " + name + " was removed from the system", "alert-success")
			return redirect(url_for('perms_system', id=id))
		
		else:
			abort(400)
