
import re

import MySQLdb as mysql
from flask import abort, flash, g, redirect, render_template, request, url_for

import cortex.lib.core
import cortex.lib.perms
import cortex.lib.puppet
import cortex.lib.systems
import cortex.lib.user
from cortex import app
from cortex.lib.user import does_user_have_permission

################################################################################

@app.route('/permissions/roles', methods=['GET', 'POST'])
@cortex.lib.user.login_required
def perms_roles():
	"""View function to let administrators view and manage the list of roles"""

	# Check user permissions
	if not does_user_have_permission("admin.permissions"):
		abort(403)

	# Cursor for the DB
	curd = g.db.cursor(mysql.cursors.DictCursor)

	## Create new role
	if request.method == 'POST':

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
		curd.execute("SELECT 1 FROM `p_roles` WHERE `name` = %s", (name,))
		if curd.fetchone() is not None:
			flash('A role already exists with that name', 'alert-danger')
			return redirect(url_for('perms_roles'))

		# SQL insert
		curd.execute("INSERT INTO `p_roles` (`name`, `description`) VALUES (%s, %s)", (name, desc))
		g.db.commit()
		cortex.lib.core.log(__name__, "permissions.role.create", "Permission role '" + name + "' created")

		flash("Role created", "alert-success")
		return redirect(url_for('perms_roles'))

	## View list
	# Get the list of roles from the database
	roles = cortex.lib.perms.get_roles()

	# Render the page
	return render_template('perms/roles.html', active='perms', title="Roles", roles=roles, manage_role_route='perms_role')


################################################################################

@app.route('/permissions/role/<int:role_id>', methods=['GET', 'POST'])
@cortex.lib.user.login_required
def perms_role(role_id):
	"""View function to let administrators view and manage a role"""

	# Check user permissions
	if not does_user_have_permission("admin.permissions"):
		abort(403)

	# Cursor for the DB
	curd = g.db.cursor(mysql.cursors.DictCursor)

	# Get the role from the database
	role = cortex.lib.perms.get_role(role_id)

	# Catch when no role exists
	if role is None:
		abort(404)

	# Tab to show
	active_tab = request.args.get("t", "global") if request.args.get("t", "global") in ["global", "systems", "puppet"] else "global"

	## Edit role, delete role
	if request.method == 'POST':
		action = request.form['action']

		# delete_role        - delete the role
		# edit_role          - change name/desc of the role
		# update_perms       - Update the list of permissions
		# add_user           - Give a user this role
		# remove_user        - Revoke from a user this role
		# add_system         - Add a system to this role
		# remove_system      - Remove a system from this role
		# edit_system        - Edit an system's permissions
		# add_environment    - Add an environment to this role
		# remove_environment - Remove an environment from this role
		# edit_environment   - Edit an environment's permissions

		## Delete the role
		if action == 'delete_role':
			curd.execute("DELETE FROM `p_roles` WHERE `id` = %s", (role_id,))
			g.db.commit()

			cortex.lib.core.log(__name__, "permissions.role.delete", "Role '" + role['name'] + "' (" + str(role_id) + ")" + " deleted")
			flash("The role `" + role['name'] + "` has been deleted", "alert-success")
			return redirect(url_for('perms_roles'))

		## Change the name and/or description of the role
		if action == 'edit_role':
			# Validate class name/prefix
			name = request.form['name']
			if len(name) < 3 or len(name) > 64:
				flash('The name you chose was invalid. It must be between 3 and 64 characters long.', 'alert-danger')
				return redirect(url_for('perms_role', role_id=role_id))

			# Validate the description
			desc = request.form['description']
			if len(desc) < 3 or len(desc) > 512:
				flash('The description you chose was invalid. It must be between 3 and 512 characters long.', 'alert-danger')
				return redirect(url_for('perms_role', role_id=role_id))

			curd.execute("UPDATE `p_roles` SET `name` = %s, `description` = %s WHERE `id` = %s", (name, desc, role_id))
			g.db.commit()
			cortex.lib.core.log(__name__, "permissions.role.edit", "Role '" + role['name'] + "' (" + str(role_id) + ")" + " name/description edited")

			flash("Role updated", "alert-success")
			return redirect(url_for('perms_role', role_id=role_id))

		## Update role permissions
		if action == 'update_perms':
			# Loop over all the permissions available, check if it is in the form
			# if it isn't, make sure to delete from the table
			# if it is, make sure it is in the table
			perms = app.permissions.permissions + app.permissions.workflow_permissions
			changes = 0

			for perm in perms:
				## Check if the role already has this permission or not
				curd.execute("SELECT `p_role_perms`.`perm_id` from `p_role_perms` JOIN `p_perms` ON `p_role_perms`.`perm_id`=`p_perms`.`id` WHERE `p_role_perms`.`role_id`=%s AND `p_perms`.`perm`=%s", (role_id, perm['name']))
				row = curd.fetchone()
				perm_id = row["perm_id"] if row is not None else None

				should_exist = False
				if perm['name'] in request.form:
					if request.form[perm['name']] == 'yes':
						should_exist = True

				# If it shouldn't exist but does
				if not should_exist and perm_id is not None:
					curd.execute("DELETE FROM `p_role_perms` WHERE `role_id` = %s AND `perm_id` = %s", (role_id, perm_id))
					g.db.commit()
					cortex.lib.core.log(__name__, "permissions.role.revoke", "Permission '" + perm['name'] + "' removed from role '" + role['name'] + "' (" + str(role_id) + ")")
					changes += 1
				# If it should exist but doesn't
				elif should_exist and perm_id is None:


					curd.execute("INSERT INTO `p_role_perms` (`role_id`, `perm_id`) VALUES (%s, (SELECT `id` FROM `p_perms` WHERE `perm`=%s))", (role_id, perm['name']))
					g.db.commit()
					cortex.lib.core.log(__name__, "permissions.role.grant", "Permission '" + perm['name'] + "' added to role '" + role['name'] + "' (" + str(role_id) + ")")
					changes += 1

			if changes == 0:
				flash("Permissions were not updated - no changes requested", "alert-warning")
			else:
				flash("Permissions for the role were successfully updated", "alert-success")

			return redirect(url_for('perms_role', role_id=role_id))

		## Add a user or group to the role
		if action == 'add_user':
			name = request.form['name']
			if not re.match(r'^[a-zA-Z0-9\-\_]{3,255}$', name):
				flash("The user or group name you sent was invalid", "alert-danger")
				return redirect(url_for('perms_role', role_id=role_id))

			ptype = request.form['type']
			if not re.match(r'^[0-9]+$', ptype):
				flash("The type you sent was invalid", "alert-danger")
				return redirect(url_for('perms_role', role_id=role_id))

			ptype = int(ptype)

			if ptype not in [0, 1]:
				flash("The type you sent was invalid", "alert-danger")
				return redirect(url_for('perms_role', role_id=role_id))

			if ptype == 0:
				hstr = "user"

				if not cortex.lib.user.does_user_exist(name):
					flash("The username you sent does not exist", "alert-danger")
					return redirect(url_for('perms_role', role_id=role_id))

			elif ptype == 1:
				hstr = "group"

				if not cortex.lib.ldapc.does_group_exist(name):
					flash("The Active Directory group you specified does not exist", "alert-danger")
					return redirect(url_for('perms_role', role_id=role_id))

			# Ensure the user/group combo was not already added
			curd.execute("SELECT 1 FROM `p_role_who` WHERE `role_id` = %s AND `who` = %s AND `type` = %s", (role_id, name, ptype))
			if curd.fetchone() is not None:
				flash('That user/group is already added to the role', 'alert-warning')
				return redirect(url_for('perms_role', role_id=role_id))

			curd.execute("INSERT INTO `p_role_who` (`role_id`, `who`, `type`) VALUES (%s, %s, %s)", (role_id, name, ptype))
			g.db.commit()
			cortex.lib.core.log(__name__, "permissions.role.member.add", hstr + " '" + name + "' added to role '" + role['name'] + "' (" + str(role_id) + ")")

			flash("The " + hstr + " " + name + " was added to the role", "alert-success")
			return redirect(url_for('perms_role', role_id=role_id))

		## Remove a user or group from the role
		if action == 'remove_user':
			wid = request.form['wid']
			if not re.match(r'^[0-9]+$', wid):
				flash("The user/group ID you sent was invalid", "alert-danger")
				return redirect(url_for('perms_role', role_id=role_id))

			# Ensure the permission was not already granted
			curd.execute("SELECT `who` FROM `p_role_who` WHERE `id` = %s", (wid,))
			who_row = curd.fetchone()
			if who_row is None:
				flash('That user/group is not added to the role', 'alert-warning')
				return redirect(url_for('perms_role', role_id=role_id))

			curd.execute("DELETE FROM `p_role_who` WHERE `id` = %s", (wid,))
			g.db.commit()
			cortex.lib.core.log(__name__, "permissions.role.member.remove", "The user/group '" + who_row['who'] + "' was removed from role '" + role['name'] + "' (" + str(role_id) + ")")

			flash("The user or group was revoked from the role", "alert-success")
			return redirect(url_for('perms_role', role_id=role_id))

		## Add a system to the role
		if action == "add_system":
			system_id = request.form["system_id"]
			if not re.match(r'^[0-9]+$', system_id):
				flash("The system you sent was invalid", "alert-danger")
				return redirect(url_for("perms_role", role_id=role_id, t="systems"))

			system_id = int(system_id)

			# Check the system is not already assigned to this role
			curd.execute("SELECT 1 FROM `p_role_system_perms` WHERE `role_id`=%s AND `system_id`=%s", (role_id, system_id))
			if curd.fetchone() is not None:
				flash("The system is already added to the role, please select it from the list below and change permissions as required", "alert-warning")
				return redirect(url_for("perms_role", role_id=role_id, t="systems"))

			changes = 0

			# Loop over the system permissions and if provided add
			for perm in app.permissions.system_permissions:
				if perm["name"] in request.form and request.form[perm["name"]] == "yes":
					changes += 1
					curd.execute("INSERT INTO `p_role_system_perms` (`role_id`, `perm_id`, `system_id`) VALUES (%s, (SELECT `id` FROM `p_system_perms` WHERE `perm`=%s), %s)", (role_id, perm["name"], system_id))
					g.db.commit()

					cortex.lib.core.log(__name__, "permissions.role.system.grant", "System permission {perm} granted for role {role_id} on system {system_id}.".format(perm=perm["name"], role_id=role_id, system_id=system_id))

			if changes == 0:
				flash("The system was not added because no permissions were selected", "alert-danger")
			else:
				flash("The system was added to the role successfully", "alert-success")
			return redirect(url_for("perms_role", role_id=role_id, t="systems"))

		## Delete a system from the role
		if action == "remove_system":
			system_id = request.form["system_id"]
			if not re.match(r'^[0-9]+$', system_id):
				flash("The system you sent was invalid", "alert-danger")
				return redirect(url_for("perms_role", role_id=role_id, t="systems"))

			system_id = int(system_id)

			curd.execute("DELETE FROM `p_role_system_perms` WHERE `role_id`=%s AND `system_id`=%s", (role_id, system_id))
			g.db.commit()

			cortex.lib.core.log(__name__, "permissions.role.system.purge", "System permissions purged for role {role_id} on system {system_id}.".format(role_id=role_id, system_id=system_id))

			flash("The system has been removed from the role successfully", "alert-success")
			return redirect(url_for("perms_role", role_id=role_id, t="systems"))

		## Edit a systems permissions
		if action == "edit_system":
			system_id = request.form["system_id"]
			if not re.match(r'^[0-9]+$', system_id):
				flash("The system you sent was invalid", "alert-danger")
				return redirect(url_for("perms_role", role_id=role_id, t="systems"))

			system_id = int(system_id)

			changes = 0

			# Loop over the system permissions and reconcile with the DB
			for perm in app.permissions.system_permissions:
				# Check if the role already has this permission or not
				curd.execute("SELECT `p_role_system_perms`.`perm_id` FROM `p_role_system_perms` JOIN `p_system_perms` ON `p_role_system_perms`.`perm_id`=`p_system_perms`.`id` WHERE `p_role_system_perms`.`role_id`=%s AND `p_role_system_perms`.`system_id`=%s AND `p_system_perms`.`perm`=%s", (role_id, system_id, perm["name"]))
				row = curd.fetchone()
				perm_id = row["perm_id"] if row is not None else None

				should_exist = bool(perm["name"] in request.form and request.form[perm["name"]] == "yes")
				if not should_exist and perm_id is not None:
					changes += 1
					curd.execute("DELETE FROM `p_role_system_perms` WHERE `role_id`=%s AND `system_id`=%s AND `perm_id`=%s", (role_id, system_id, perm_id))
					g.db.commit()
					cortex.lib.core.log(__name__, "permissions.role.system.revoke", "System permission {perm} revoked for role {role_id} on system {system_id}".format(perm=perm["name"], role_id=role_id, system_id=system_id))

				elif should_exist and perm_id is None:
					changes += 1
					curd.execute("INSERT INTO `p_role_system_perms` (`role_id`, `perm_id`, `system_id`) VALUES (%s, (SELECT `id` FROM `p_system_perms` WHERE `perm`=%s), %s)", (role_id, perm["name"], system_id))
					g.db.commit()
					cortex.lib.core.log(__name__, "permissions.role.system.grant", "System permission {perm} granted for role {role_id} on system {system_id}.".format(perm=perm["name"], role_id=role_id, system_id=system_id))

			if changes == 0:
				flash("Permissions were not updated - no changes requested", "alert-warning")
			else:
				flash("Permissions for the system were successfully updated", "alert-success")
			return redirect(url_for("perms_role", role_id=role_id, t="systems"))

		## Add a environment to the role
		if action == "add_environment":
			environment_id = request.form["environment_id"]
			if not re.match(r'^[0-9]+$', environment_id):
				flash("The environment you sent was invalid", "alert-danger")
				return redirect(url_for("perms_role", role_id=role_id, t="puppet"))

			environment_id = int(environment_id)

			# Check the environment is not already assigned to this role
			curd.execute("SELECT 1 FROM `p_role_puppet_perms` WHERE `role_id`=%s AND `environment_id`=%s", (role_id, environment_id))
			if curd.fetchone() is not None:
				flash("The environment is already added to the role, please select it from the list below and change permissions as required", "alert-warning")
				return redirect(url_for("perms_role", role_id=role_id, t="puppet"))

			changes = 0

			# Loop over the puppet permissions and if provided add
			for perm in app.permissions.puppet_permissions:
				if perm["name"] in request.form and request.form[perm["name"]] == "yes":
					changes += 1
					curd.execute("INSERT INTO `p_role_puppet_perms` (`role_id`, `perm_id`, `environment_id`) VALUES (%s, (SELECT `id` FROM `p_puppet_perms` WHERE `perm`=%s), %s)", (role_id, perm["name"], environment_id))
					g.db.commit()

					cortex.lib.core.log(__name__, "permissions.role.puppet.grant", "Puppet permission {perm} granted for role {role_id} on environment {environment_id}.".format(perm=perm["name"], role_id=role_id, environment_id=environment_id))

			if changes == 0:
				flash("The environment was not added because no permissions were selected", "alert-danger")
			else:
				flash("The environment was added to the role successfully", "alert-success")
			return redirect(url_for("perms_role", role_id=role_id, t="puppet"))

		## Delete a environment from the role
		if action == "remove_environment":
			environment_id = request.form["environment_id"]
			if not re.match(r'^[0-9]+$', environment_id):
				flash("The environment you sent was invalid", "alert-danger")
				return redirect(url_for("perms_role", role_id=role_id, t="puppet"))

			environment_id = int(environment_id)

			curd.execute("DELETE FROM `p_role_puppet_perms` WHERE `role_id`=%s AND `environment_id`=%s", (role_id, environment_id))
			g.db.commit()

			cortex.lib.core.log(__name__, "permissions.role.puppet.purge", "Puppet permissions purged for role {role_id} on environment {environment_id}.".format(role_id=role_id, environment_id=environment_id))

			flash("The environment has been removed from the role successfully", "alert-success")
			return redirect(url_for("perms_role", role_id=role_id, t="puppet"))

		## Edit a environment's permissions
		if action == "edit_environment":
			environment_id = request.form["environment_id"]
			if not re.match(r'^[0-9]+$', environment_id):
				flash("The environment you sent was invalid", "alert-danger")
				return redirect(url_for("perms_role", role_id=role_id, t="puppet"))

			environment_id = int(environment_id)

			changes = 0

			# Loop over the puppet permissions and reconcile with the DB
			for perm in app.permissions.puppet_permissions:
				# Check if the role already has this permission or not
				curd.execute("SELECT `p_role_puppet_perms`.`perm_id` FROM `p_role_puppet_perms` JOIN `p_puppet_perms` ON `p_role_puppet_perms`.`perm_id`=`p_puppet_perms`.`id` WHERE `p_role_puppet_perms`.`role_id`=%s AND `p_role_puppet_perms`.`environment_id`=%s AND `p_puppet_perms`.`perm`=%s", (role_id, environment_id, perm["name"]))
				row = curd.fetchone()
				perm_id = row["perm_id"] if row is not None else None

				should_exist = bool(perm["name"] in request.form and request.form[perm["name"]] == "yes")
				if not should_exist and perm_id is not None:
					changes += 1
					curd.execute("DELETE FROM `p_role_puppet_perms` WHERE `role_id`=%s AND `environment_id`=%s AND `perm_id`=%s", (role_id, environment_id, perm_id))
					g.db.commit()
					cortex.lib.core.log(__name__, "permissions.role.puppet.revoke", "Puppet permission {perm} revoked for role {role_id} on environment {environment_id}".format(perm=perm["name"], role_id=role_id, environment_id=environment_id))

				elif should_exist and perm_id is None:
					changes += 1
					curd.execute("INSERT INTO `p_role_puppet_perms` (`role_id`, `perm_id`, `environment_id`) VALUES (%s, (SELECT `id` FROM `p_puppet_perms` WHERE `perm`=%s), %s)", (role_id, perm["name"], environment_id))
					g.db.commit()
					cortex.lib.core.log(__name__, "permissions.role.puppet.grant", "Puppet permission {perm} granted for role {role_id} on environment {environment_id}.".format(perm=perm["name"], role_id=role_id, environment_id=environment_id))

			if changes == 0:
				flash("Permissions were not updated - no changes requested", "alert-warning")
			else:
				flash("Permissions for the environment were successfully updated", "alert-success")
			return redirect(url_for("perms_role", role_id=role_id, t="puppet"))

		# If we get here the action was invalid!
		abort(400)

	## View list
	# Render the page
	return render_template('perms/role.html', active='perms', title="Role", active_tab=active_tab, role=role, permissions=app.permissions.get_all(), systems=cortex.lib.systems.get_systems(order='id', order_asc=False), environments=cortex.lib.puppet.get_puppet_environments())
################################################################################

@app.route('/permissions/system/<int:system_id>', methods=['GET', 'POST'])
@cortex.lib.user.login_required
def perms_system(system_id):
	"""View function to let administrators view and manage a role"""

	# Check user permissions
	if not does_user_have_permission("admin.permissions"):
		abort(403)

	# Get the system
	system = cortex.lib.systems.get_system_by_id(system_id)

	# Ensure that the system actually exists, and return a 404 if it doesn't
	if system is None:
		abort(404)

	# Cursor for the DB
	curd = g.db.cursor(mysql.cursors.DictCursor)

	if request.method == "POST":
		action = request.form['action']

		## Make changes to an existing user/group
		if action == 'edit':
			## Get the 'who' and the 'type'
			who = request.form['who']
			wtype = request.form['type']

			# Loop over all the per-system permissions available. Check if the
			# permission is in the form data sent by the browser.
			# if it isn't, make sure to delete from the table
			# if it is, make sure it is in the table
			changes = 0

			for perm in app.permissions.system_permissions:
				## Check if the role already has this permission or not
				curd.execute('SELECT `p_system_perms_who`.`perm_id` FROM `p_system_perms_who` JOIN `p_system_perms` ON `p_system_perms_who`.`perm_id`=`p_system_perms`.`id` WHERE `system_id` = %s AND `who` = %s AND `type` = %s AND `perm` = %s', (system_id, who, wtype, perm["name"]))
				row = curd.fetchone()
				perm_id = row["perm_id"] if row is not None else None

				should_exist = False
				if perm['name'] in request.form:
					if request.form[perm['name']] == 'yes':
						should_exist = True

				if not should_exist and perm_id is not None:
					curd.execute("DELETE FROM `p_system_perms_who` WHERE `system_id` = %s AND `who` = %s AND `type` = %s AND `perm_id` = %s", (system_id, who, wtype, perm_id))
					g.db.commit()
					if wtype == 0:
						cortex.lib.core.log(__name__, "permissions.system.revoke.user", "System permission '" + perm['name'] + "' revoked for user '" + who + "' on system " + str(system_id))
					else:
						cortex.lib.core.log(__name__, "permissions.system.revoke.group", "System permission '" + perm['name'] + "' revoked for group '" + who + "' on system " + str(system_id))
					changes += 1

				elif should_exist and perm_id is None:
					curd.execute("INSERT INTO `p_system_perms_who` (`system_id`, `who`, `type`, `perm_id`) VALUES (%s, %s, %s, (SELECT `id` FROM `p_system_perms` WHERE `perm`=%s))", (system_id, who, wtype, perm['name']))
					g.db.commit()
					if wtype == 0:
						cortex.lib.core.log(__name__, "permissions.system.grant.user", "System permission '" + perm['name'] + "' granted for user '" + who + "' on system " + str(system_id))
					else:
						cortex.lib.core.log(__name__, "permissions.system.grant.group", "System permission '" + perm['name'] + "' granted for group '" + who + "' on system " + str(system_id))
					changes += 1

			if changes == 0:
				flash("Permissions were not updated - no changes requested", "alert-warning")
			else:
				flash("Permissions for the system were successfully updated", "alert-success")
			return redirect(url_for('perms_system', system_id=system_id))

		if action == 'add':
			name = request.form['name']
			if not re.match(r'^[a-zA-Z0-9\-\_&]{3,255}$', name):
				flash("The user or group name you sent was invalid", "alert-danger")
				return redirect(url_for('perms_system', system_id=system_id))

			wtype = request.form['type']
			if not re.match(r'^[0-9]+$', wtype):
				flash("The type you sent was invalid", "alert-danger")
				return redirect(url_for('perms_system', system_id=system_id))

			wtype = int(wtype)

			if wtype not in [0, 1]:
				flash("The type you sent was invalid", "alert-danger")
				return redirect(url_for('perms_system', system_id=system_id))

			if wtype == 0:
				hstr = "user"

				if not cortex.lib.user.does_user_exist(name):
					flash("The username you specified does not exist", "alert-danger")
					return redirect(url_for('perms_system', system_id=system_id))

			elif wtype == 1:
				hstr = "group"

				if not cortex.lib.ldapc.does_group_exist(name):
					flash("The Active Directory group you specified does not exist", "alert-danger")
					return redirect(url_for('perms_system', system_id=system_id))

			## Check the user/group/type combo doesn't already exist
			curd.execute("SELECT 1 FROM `p_system_perms_who` WHERE `system_id` = %s AND `who` = %s AND `type` = %s", (system_id, name, wtype))
			if curd.fetchone() is not None:
				flash('That user/group is already added to the system, please select it from the list below and change permissions as required', 'alert-warning')
				return redirect(url_for('perms_system', system_id=system_id))

			changes = 0

			## Now loop over the per-system permissions available to us
			for perm in app.permissions.system_permissions:
				## If the form has the checkbox for this perm checked...
				if perm['name'] in request.form:
					if request.form[perm['name']] == 'yes':
						## Insert the permission for this name/type/perm combo
						changes = changes + 1
						curd.execute("INSERT INTO `p_system_perms_who` (`system_id`, `who`, `type`, `perm_id`) VALUES (%s, %s, %s, (SELECT `id` FROM `p_system_perms` WHERE `perm`=%s))", (system_id, name, wtype, perm['name']))
						g.db.commit()
						if wtype == 0:
							cortex.lib.core.log(__name__, "permissions.system.grant.user", "System permission '" + perm['name'] + "' granted for user '" + name + "' on system " + str(system_id))
						else:
							cortex.lib.core.log(__name__, "permissions.system.grant.group", "System permission '" + perm['name'] + "' granted for group '" + name + "' on system " + str(system_id))

			if changes == 0:
				flash("The " + hstr + " " + name + " was not added because no permissions were selected", "alert-danger")
			else:
				flash("The " + hstr + " " + name + " was added to the system", "alert-success")
			return redirect(url_for('perms_system', system_id=system_id))

		if action == 'remove':
			name = request.form['name']
			if not re.match(r'^[a-zA-Z0-9\-\_&]{3,255}$', name):
				flash("The user or group name you sent was invalid", "alert-danger")
				return redirect(url_for('perms_system', system_id=system_id))

			wtype = request.form['type']
			if not re.match(r'^[0-9]+$', wtype):
				flash("The type you sent was invalid", "alert-danger")
				return redirect(url_for('perms_system', system_id=system_id))

			wtype = int(wtype)

			if wtype not in [0, 1]:
				flash("The type you sent was invalid", "alert-danger")
				return redirect(url_for('perms_system', system_id=system_id))

			if wtype == 0:
				hstr = "user"
			elif wtype == 1:
				hstr = "group"

			curd.execute("DELETE FROM `p_system_perms_who` WHERE `system_id` = %s AND `who` = %s AND `type` = %s", (system_id, name, wtype))
			g.db.commit()
			cortex.lib.core.log(__name__, "permissions.system.purge", "System permissions purged for " + hstr + " '" + name + "' on system " + str(system_id))

			flash("The " + hstr + " " + name + " was removed from the system", "alert-success")
			return redirect(url_for('perms_system', system_id=system_id))

		# If we get here the action was invalid!
		abort(400)

	## Handle GET
	system_perms = []
	# Get the list of distinct users/groups/etc added to this system explicitly
	curd.execute("SELECT DISTINCT `type`, `who` FROM `p_system_perms_who` WHERE `system_id` = %s", (system_id,))
	results = curd.fetchall()

	for entry in results:
		# Get perms for this system/user/type combo
		curd.execute("SELECT `p_system_perms`.`perm` AS `perm` FROM `p_system_perms_who` JOIN `p_system_perms` ON `p_system_perms_who`.`perm_id`=`p_system_perms`.`id` WHERE `p_system_perms`.`active`=1 AND `p_system_perms_who`.`who`=%s AND `p_system_perms_who`.`type`=%s AND `p_system_perms_who`.`system_id`=%s", (entry["who"], entry["type"], system_id))
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

	# Get the list of distinct users/groups/etc added to this system via a role.
	curd.execute("SELECT DISTINCT `p_roles`.`id` AS `role_id`, `p_roles`.`name` AS `role_name`, `p_role_who`.`who` AS `who`, `p_role_who`.`type` AS `who_type` FROM `p_role_who` JOIN `p_role_system_perms` ON `p_role_who`.`role_id`=`p_role_system_perms`.`role_id` JOIN `p_roles` ON `p_role_who`.`role_id`=`p_roles`.`id` WHERE `p_role_system_perms`.`system_id`=%s", (system_id,))
	results = curd.fetchall()

	for entry in results:
		# Get perms for this system/user/type combo
		curd.execute("SELECT DISTINCT `p_system_perms`.`perm` AS `perm` FROM `p_role_who` JOIN `p_role_system_perms` ON `p_role_who`.`role_id`=`p_role_system_perms`.`role_id` JOIN `p_system_perms` ON `p_role_system_perms`.`perm_id`=`p_system_perms`.`id` WHERE `p_system_perms`.`active`=1 AND `p_role_system_perms`.`system_id`=%s AND `p_role_who`.`who`=%s AND `p_role_who`.`type`=%s AND `p_role_who`.`role_id`=%s", (system_id, entry["who"], entry["who_type"], entry["role_id"]))

		perms = curd.fetchall()

		# Create a object to add to the system_perms list.
		obj = {
			'who': entry['who'],
			'type': entry['who_type'],
			'is_editable': False, # Role Perms cannot be edited here!!
			'role_id': entry['role_id'],
			'role_name': entry['role_name'],
			'perms': [p['perm'] for p in perms]
		}

		# Add the constructed object to the system_perms list.
		system_perms.append(obj)

	return render_template('perms/system.html', active='systems', title="Server permissions", system=system, system_perms=system_perms, sysperms=app.permissions.system_permissions)
