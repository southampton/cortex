import json
import MySQLdb as mysql
import Pyro4
import Pyro4.errors


def run(helper, options):

	env = 'devdomain'

	# Set up cursor to access the DB
	curd = helper.db.cursor(mysql.cursors.DictCursor)


	curd.execute("SELECT `id` FROM `systems` WHERE `name` = %s;", (options['machine'], ))
	system_id = curd.fetchone()['id']
	# dsc_proxy = helper.lib.dsc.dsc_connect()
	# roles = helper.lib.dsc.get_roles(dsc_proxy)
	dsc_config = options['dsc_config']
	config_for_machine = {}
	dsc_proxy = Pyro4.Proxy('PYRO:CortexWindowsRPC@' + str(dsc_config[env]['host']) + ':' + str(dsc_config[env]['port']))
	dsc_proxy._pyroHmacKey = str(dsc_config[env]['key'])

	roles = dsc_proxy.get_roles()
	

	config_for_machine['AllNodes'] = roles['AllNodes']
	generic_roles = [role for role in roles if 'UOSGeneric' in role]
	roles_for_machine = {a : {'length':0} for a in generic_roles}

	# roles_for_machine = {name : {'length':0} for role in generic_roles}
	for x, nested_dictionary in enumerate(config_for_machine['AllNodes']):
		if 'NodeName' in nested_dictionary.keys():
			config_for_machine['AllNodes'][x]['NodeName'] = options['machine']
		if 'Role' in nested_dictionary.keys():
			config_for_machine['AllNodes'][x]['Role'] = list(roles_for_machine.keys())

	# config_for_machine = json.loads(config_for_machine)


	# helper.event("updating db", "Adding machine " + options['machine'] + " to dsc")
	# helper.event('fsd',description='INSERT INTO `dsc_config` (`system_id`, `config`, `roles`) VALUES ( ' + options['machine'] + ', "", "");' )

	curd.execute('INSERT INTO `dsc_config` (`system_id`, `config`, `roles`) VALUES (%s, %s, %s);', (system_id, json.dumps(config_for_machine), json.dumps(roles_for_machine)))
	helper.db.commit()
	helper.end_event("Committed changes")
