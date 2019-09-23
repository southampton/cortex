
#from cortex import app
from flask import g
import MySQLdb as mysql

################################################################################

def get_roles():
	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute("SELECT * FROM `roles` ORDER BY `name`")
	return curd.fetchall()

################################################################################

def get_role(id):
	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute("SELECT * FROM `roles` WHERE `id` = %s", (id,))
	role = curd.fetchone()

	## Return None if the role was not found
	if role == None:
		return None

	# Add on the permissions assigned to the role
	curd.execute("SELECT * FROM `role_perms` WHERE `role_id` = %s", (id,))
	perms = curd.fetchall()

	# Attach the perms to the 'role' dictionary
	if perms != None:
		role['perms'] = perms
	else:
		role['perms'] = []

	# Add on the list of users assigned to the role
	curd.execute("SELECT `role_who`.`id` AS `id`, `role_who`.`role_id` AS `role_id`, `role_who`.`who` AS `who`, `role_who`.`type` AS `type`, `realname_cache`.`realname` FROM `role_who` LEFT JOIN `realname_cache` ON `role_who`.`who` = `realname_cache`.`username` WHERE `role_id` = %s", (id,))
	who = curd.fetchall()

	# Attach the perms to the 'role' dictionary
	if who != None:
		role['who'] = who
	else:
		role['who'] = []

	return role

################################################################################

def get_system_roles():
	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute("SELECT * FROM `system_roles` ORDER BY `name`")
	return curd.fetchall()

################################################################################

def get_system_role(id):
	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute("SELECT * FROM `system_roles` WHERE `id` = %s", (id,))
	role = curd.fetchone()
	
	## Return None if the role was not found
	if role == None:
		return None

	# Add on the permissions assigned to the role
	curd.execute("SELECT * FROM `system_role_perms` WHERE `system_role_id` = %s", (id,))
	perms = curd.fetchall()

	# Attach the perms to the 'role' dictionary
	if perms != None:
		role['perms'] = perms
	else:
		role['perms'] = []

	# Add on the list of users assigned to the role
	curd.execute("SELECT `system_role_who`.`id` AS `id`, `system_role_who`.`system_role_id` AS `system_role_id`, `system_role_who`.`who` AS `who`, `system_role_who`.`type` AS `type`, `realname_cache`.`realname` FROM `system_role_who` LEFT JOIN `realname_cache` ON `system_role_who`.`who` = `realname_cache`.`username` WHERE `system_role_id` = %s", (id,))
	who = curd.fetchall()

	# Attach the perms to the 'role' dictionary
	if who != None:
		role['who'] = who
	else:
		role['who'] = []

	# Add on the list of systems assigned to the role.
	curd.execute("SELECT `system_role_what`.`system_id`, `systems`.`name` FROM `system_role_what` LEFT JOIN `systems` ON `system_role_what`.`system_id`=`systems`.`id` WHERE `system_role_id`=%s", (id,))
	what = curd.fetchall()

	# Attach the systems to the role dictionary.
	if what != None:
		role['what'] = what
	else:
		role['what'] = []

	return role


