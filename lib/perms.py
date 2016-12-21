#!/usr/bin/python

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
