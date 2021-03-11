import MySQLdb as mysql
from flask import g

################################################################################

class CortexPermissions:

	# Default permissions
	permissions = []
	workflow_permissions = []
	system_permissions = []
	puppet_permissions = []

	def __init__(self, config):
		"""Initialise the Cortex permissions system"""

		self._config = config
		self._init_permissions()
		self._init_permissions_db()

	def _get_db(self):
		"""Connect to Cortex DB"""
		try:
			db = mysql.connect(host=self._config['MYSQL_HOST'], port=self._config['MYSQL_PORT'], user=self._config['MYSQL_USER'], passwd=self._config['MYSQL_PASS'], db=self._config['MYSQL_NAME'])
		except Exception as ex:
			raise Exception("Could not connect to MySQL server: " + str(type(ex)) + " - " + str(ex))
		else:
			return db

	def _add_db_permission(self, table, name, desc):
		"""Add additional permissions to the database"""

		## Open a connection and cursor to the database
		temp_db = self._get_db()
		cursor = temp_db.cursor()
		cursor.connection.autocommit(True)

		if table not in ["p_perms", "p_system_perms", "p_puppet_perms"]:
			raise Exception("Could not add permission {name} - Invalid database table {table}".format(name=name, table=table))

		## Insert the permission into the appropriate table
		cursor.execute(
			"INSERT INTO `{table}` (`perm`, `description`, `active`) VALUES (%s, %s, 1) ON DUPLICATE KEY UPDATE `active`=1, `description`=%s".format(table=table),
			(name, desc, desc)
		)

		## Close database connection
		temp_db.close()

	def add_permission(self, name, desc):
		self._add_db_permission("p_perms", name, desc)
		self.permissions.append({"name": name, "desc": desc})

	def add_workflow_permission(self, name, desc):
		self._add_db_permission("p_perms", name, desc)
		self.workflow_permissions.append({"name": name, "desc": desc})

	def add_system_permission(self, name, desc):
		self._add_db_permission("p_system_perms", name, desc)
		self.system_permissions.append({"name": name, "desc": desc})

	def add_puppet_permission(self, name, desc):
		self._add_db_permission("p_puppet_perms", name, desc)
		self.puppet_permissions.append({"name": name, "desc": desc})

	def get_all(self):
		"""Get all permissions"""
		return {
			"permissions": self.permissions,
			"workflow": self.workflow_permissions,
			"system": self.system_permissions,
			"puppet": self.puppet_permissions,
		}

	def _init_permissions_db(self):
		"""Reconcile Cortex permissions with the DB"""

		## Open a connection and cursor to the database
		temp_db = self._get_db()
		cursor = temp_db.cursor()
		cursor.connection.autocommit(True)

		## Deactivate all permissions before starting
		cursor.execute("""UPDATE `p_perms` SET `active`=0""")
		cursor.execute("""UPDATE `p_system_perms` SET `active`=0""")
		cursor.execute("""UPDATE `p_puppet_perms` SET `active`=0""")

		## Ensure we have a default administrator role
		cursor.execute("""INSERT INTO `p_roles` (`id`, `name`, `description`) VALUES (1, 'Administrator', 'Has full access to everything') ON DUPLICATE KEY UPDATE `name`='Administrator', `description`='Has full access to everything'""")

		## Add global permissions to the database, and assign to Administrator
		for perm in self.permissions:
			cursor.execute("""INSERT INTO `p_perms` (`perm`, `description`, `active`) VALUES (%s, %s, 1) ON DUPLICATE KEY UPDATE `id`=LAST_INSERT_ID(`id`), `active`=1, `description`=%s""", (perm["name"], perm["desc"], perm["desc"]))
			cursor.execute("""INSERT IGNORE INTO `p_role_perms` (`role_id`, `perm_id`) VALUES (1, LAST_INSERT_ID())""")

		## Add workflow permissions to the database
		## These do not need to be assigned to any roles (Admin has workflows.all)
		for perm in self.workflow_permissions:
			cursor.execute("""INSERT INTO `p_perms` (`perm`, `description`, `active`) VALUES (%s, %s, 1) ON DUPLICATE KEY UPDATE `active`=1, `description`=%s""", (perm["name"], perm["desc"], perm["desc"]))

		## Add system permissions to the database
		## These do not need to be assigned to any roles
		for perm in self.system_permissions:
			cursor.execute("""INSERT INTO `p_system_perms` (`perm`, `description`, `active`) VALUES (%s, %s, 1) ON DUPLICATE KEY UPDATE `active`=1, `description`=%s""", (perm["name"], perm["desc"], perm["desc"]))

		## Add puppet permissions to the database
		## These do not need to be assigned to any roles
		for perm in self.puppet_permissions:
			cursor.execute("""INSERT INTO `p_puppet_perms` (`perm`, `description`, `active`) VALUES (%s, %s, 1) ON DUPLICATE KEY UPDATE `active`=1, `description`=%s""", (perm["name"], perm["desc"], perm["desc"]))

		## Close database connection
		temp_db.close()

	def _init_permissions(self):
		"""Sets up the list of permissions that can be assigned, must be run
		before workflows are run"""

		# pylint: disable=bad-whitespace

		## The ORDER MATTERS! It determines the order used on the Roles page
		self.permissions = [
			{'name': 'cortex.admin',                       'desc': 'Cortex Administrator'},

			{'name': 'systems.all.view',                   'desc': 'View any system'},
			{'name': 'systems.own.view',                   'desc': 'View systems allocated by the user'},
			{'name': 'systems.all.view.puppet',            'desc': 'View Puppet reports and facts on any system'},
			{'name': 'systems.all.view.puppet.classify',   'desc': 'View Puppet classify on any system'},
			{'name': 'systems.all.view.puppet.catalog',    'desc': 'View Puppet catalog on any system'},
			{'name': 'systems.all.view.rubrik',            'desc': 'View Rubrik backups for any system'},
			{'name': 'systems.all.edit.expiry',            'desc': 'Modify the expiry date of any system'},
			{'name': 'systems.all.edit.review',            'desc': 'Modify the review status of any system'},
			{'name': 'systems.all.edit.vmware',            'desc': 'Modify the VMware link on any system'},
			{'name': 'systems.all.edit.cmdb',              'desc': 'Modify the CMDB link on any system'},
			{'name': 'systems.all.edit.comment',           'desc': 'Modify the comment on any system'},
			{'name': 'systems.all.edit.puppet',            'desc': 'Modify Puppet settings on any system'},
			{'name': 'systems.all.edit.rubrik',            'desc': 'Modify Rubrik settings on any system'},
			{'name': 'systems.all.edit.owners',            'desc': 'Modify the system owners on any system'},
			{'name': 'systems.add_existing',               'desc': 'Add existing (legacy) systems to Cortex'},
			{'name': 'systems.allocate_name',              'desc': 'Allocate system names (Administrators only)'},

			{'name': 'puppet.dashboard.view',              'desc': 'View the Puppet dashboard'},
			{'name': 'puppet.nodes.view',                  'desc': 'View the list of Puppet nodes'},
			{'name': 'puppet.default_classes.view',        'desc': 'View the list of Puppet default classes'},
			{'name': 'puppet.default_classes.edit',        'desc': 'Modify the list of Puppet default classes'},
			{'name': 'puppet.documentation.view',          'desc': 'View the Puppet documentation'},
			{'name': 'puppet.environments.all.create',     'desc': 'Create all types of Puppet environments'},
			{'name': 'puppet.environments.all.view',       'desc': 'View all Puppet environments'},
			{'name': 'puppet.environments.all.classify',   'desc': 'Classify systems with any Puppet environment'},
			{'name': 'puppet.environments.all.delete',     'desc': 'Delete all Puppet environments'},

			{'name': 'classes.view',                       'desc': 'View the list of system class definitions'},
			{'name': 'classes.edit',                       'desc': 'Edit system class definitions'},
			{'name': 'tasks.view',                         'desc': 'View the details of all tasks (not just your own)'},
			{'name': 'events.view',                        'desc': 'View the details of all events (not just your own)'},
			{'name': 'specs.view',                         'desc': 'View the VM Specification Settings'},
			{'name': 'specs.edit',                         'desc': 'Edit the VM Specification Settings'},
			{'name': 'vmware.view',                        'desc': 'View VMware data and statistics'},

			{'name': 'maintenance.vmware',                 'desc': 'Run VMware maintenance tasks'},
			{'name': 'maintenance.cmdb',                   'desc': 'Run CMDB maintenance tasks'},
			{'name': 'maintenance.expire_vm',              'desc': 'Run the Expire VM maintenance task'},
			{'name': 'maintenance.sync_puppet_servicenow', 'desc': 'Run the Sync Puppet with ServiceNow task'},
			{'name': 'maintenance.cert_scan',              'desc': 'Run the Certificate Scan task'},
			{'name': 'maintenance.student_vm',             'desc': 'Run the Student VM Build task'},
			{'name': 'maintenance.lock_workflows',         'desc': 'Run the Lock/Unlock Workflows task'},
			{'name': 'maintenance.rubrik_policy_check',    'desc': 'Run the Rubrik Policy check task'},

			{'name': 'admin.permissions',                  'desc': 'Modify Cortex permissions (Administrators only)'},
			{'name': 'workflows.all',                      'desc': 'Use any workflow or workflow function'},

			{'name': 'control.all.vmware.power',           'desc': 'Contol the power settings of any VM'},

			{'name': 'api.register',                       'desc': 'Manually register Linux machines (rebuilds / physical machines)'},
			{'name': 'api.get',                            'desc': 'Send GET requests to the Cortex API'},
			{'name': 'api.post',                           'desc': 'Send POST requests to the Cortex API'},
			{'name': 'api.put',                            'desc': 'Send PUT requests to the Cortex API'},
			{'name': 'api.delete',                         'desc': 'Send DELETE requests to the Cortex API'},

			{'name': 'certificates.view',                  'desc': 'View the list of discovered certificates and their details'},
			{'name': 'certificates.stats',                 'desc': 'View the statistics about certificates'},
			{'name': 'certificates.add',                   'desc': 'Adds a certificate to the list of tracked certificates'},

			{'name': 'tenable.view',                       'desc': 'View information from Tenable.io'},
			{'name': 'dsc.view', 			       'desc': 'View DSC information about system'},
		]

		self.workflow_permissions = []

		self.system_permissions = [
			{'name': 'view.overview',        'desc': 'View the system overview'},
			{'name': 'view.detail',          'desc': 'View the system details'},
			{'name': 'view.puppet',          'desc': 'View the system\'s Puppet reports and facts'},
			{'name': 'view.puppet.classify', 'desc': 'View the system\'s Puppet classification'},
			{'name': 'view.puppet.catalog',  'desc': 'View the system\'s Puppet catalog'},
			{'name': 'edit.expiry',          'desc': 'Change the expiry date of the system'},
			{'name': 'edit.review',          'desc': 'Change the review status of the system'},
			{'name': 'edit.vmware',          'desc': 'Change the VMware VM link'},
			{'name': 'edit.cmdb',            'desc': 'Change the CMDB link'},
			{'name': 'edit.comment',         'desc': 'Change the comment'},
			{'name': 'edit.owners',          'desc': 'Change the system owners'},
			{'name': 'edit.puppet',          'desc': 'Change Puppet settings'},
			{'name': 'edit.rubrik',          'desc': 'Change Rubrik backup settings'},
			{'name': 'control.vmware.power', 'desc': 'Control the VMware power state'},
			{'name': 'view.dsc', 		 'desc': 'View the DSC settings'}
		]

		self.puppet_permissions = [
			{'name': 'view',     'desc': 'View the Puppet environment\'s settings'},
			{'name': 'classify', 'desc': 'Classify systems with the Puppet environment'},
			{'name': 'delete',   'desc': 'Delete the Puppet environment'},
		]

		# pylint: enable=bad-whitespace


################################################################################

def get_roles():
	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute("SELECT * FROM `p_roles` ORDER BY `name`")
	return curd.fetchall()

################################################################################

def get_role(role_id):
	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute("SELECT `id`, `name`, `description` FROM `p_roles` WHERE `id`=%s", (role_id,))
	role = curd.fetchone()

	## Return None if the role was not found
	if role is None:
		return None

	# Add on the permissions assigned to the role
	curd.execute("SELECT `p_perms`.`perm` AS `perm` FROM `p_perms` JOIN `p_role_perms` ON `p_perms`.`id`=`p_role_perms`.`perm_id` WHERE `p_perms`.`active`=1 AND `p_role_perms`.`role_id`=%s", (role_id,))
	role["perms"] = [r["perm"] for r in (curd.fetchall() or [])] # Return a list of the permissions e.g. ['perm1', 'perm2'], or [] if None

	# Add on the system permissions assigned to the role
	curd.execute("SELECT `p_system_perms`.`perm` AS `perm`, `p_role_system_perms`.`system_id` AS `system_id`, `systems`.`name` AS `system_name` FROM `p_system_perms` JOIN `p_role_system_perms` ON `p_system_perms`.`id`=`p_role_system_perms`.`perm_id` LEFT JOIN `systems` ON `p_role_system_perms`.`system_id`=`systems`.`id` WHERE `p_system_perms`.`active`=1 AND `p_role_system_perms`.`role_id`=%s", (role_id,))

	role["system_perms"] = {}
	for row in (curd.fetchall() or []):
		if row["system_id"] not in role["system_perms"]:
			role["system_perms"][row["system_id"]] = {"name": row["system_name"], "perms": []}
		role["system_perms"][row["system_id"]]["perms"].append(row["perm"])

	# Add on the puppet permissions assigned to the role
	curd.execute("SELECT `p_puppet_perms`.`perm` AS `perm`, `p_role_puppet_perms`.`environment_id` AS `environment_id`, `puppet_environments`.`environment_name` AS `environment_name` FROM `p_puppet_perms` JOIN `p_role_puppet_perms` ON `p_puppet_perms`.`id`=`p_role_puppet_perms`.`perm_id` LEFT JOIN `puppet_environments` ON `p_role_puppet_perms`.`environment_id`=`puppet_environments`.`id` WHERE `p_puppet_perms`.`active`=1 AND `p_role_puppet_perms`.`role_id`=%s", (role_id,))

	role["puppet_perms"] = {}
	for row in (curd.fetchall() or []):
		if row["environment_id"] not in role["puppet_perms"]:
			role["puppet_perms"][row["environment_id"]] = {"name": row["environment_name"], "perms": []}
		role["puppet_perms"][row["environment_id"]]["perms"].append(row["perm"])

	# Add on the list of users assigned to the role
	curd.execute("SELECT `p_role_who`.`id` AS `id`, `p_role_who`.`who` AS `who`, `p_role_who`.`type` AS `type`, `realname_cache`.`realname` FROM `p_role_who` LEFT JOIN `realname_cache` ON `p_role_who`.`who` = `realname_cache`.`username` WHERE `role_id`=%s", (role_id,))
	role["who"] = curd.fetchall() or []

	return role
