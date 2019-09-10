import json
import MySQLdb as mysql

def run(helper, options):

	# Set up cursor to access the DB
	curd = helper.db.cursor(mysql.cursors.DictCursor)


	curd.execute("SELECT `id` FROM `systems` WHERE `name` = %s;", (options['machine'], ))
	system_id = curd.fetchone()['id']

	# dsc_proxy = helper.lib.dsc.dsc_connect()
	# roles = helper.lib.dsc.get_roles(dsc_proxy)
	config_for_machine = {}

	# config_for_machine['AllNodes'] = roles['AllNodes']
	# generic_roles = [role for role in roles if 'UOSGeneric' in role]

	# roles_for_machine = {name : {'length':0} for role in generic_roles}


	#Delete this once the code is working in neocortex
	config_for_machine = {
		"AllNodes": [
			{
				"CertificateFile": "F:\\Certs\\DscPublicKey.cer",
				"NodeName": "XXXXX",
				"PSDscAllowDomainUser": "True"
			},
			{
				"NodeName": "XXXXX",
				"Role": [
					"UOSGeneric_LocalGroupAddRemoveMemeber",
					"UOSGeneric_Package",
					"UOSGeneric_ChocolateyPackage",
					"UOSGeneric_SMBShare",
					"UOSGeneric_SchedledTask",
					"UOSGeneric_SXSFeature"
				]
			}
		]
	}
	for x, nested_dictionary in enumerate(config_for_machine['AllNodes']):
		if 'NodeName' in nested_dictionary.keys():
			config_for_machine['AllNodes'][x]['NodeName'] = options['machine']

	# config_for_machine = json.loads(config_for_machine)
	roles_for_machine = {a : {'length':0} for a in ["UOSGeneric_LocalGroupAddRemoveMemeber","UOSGeneric_Package","UOSGeneric_ChocolateyPackage","UOSGeneric_SMBShare","UOSGeneric_SchedledTask","UOSGeneric_SXSFeature"]}


	# helper.event("updating db", "Adding machine " + options['machine'] + " to dsc")
	# helper.event('fsd',description='INSERT INTO `dsc_config` (`system_id`, `config`, `roles`) VALUES ( ' + options['machine'] + ', "", "");' )

	curd.execute('INSERT INTO `dsc_config` (`system_id`, `config`, `roles`) VALUES (%s, %s, %s);', (system_id, json.dumps(config_for_machine), json.dumps(roles_for_machine)))
	helper.db.commit()
	helper.end_event("Committed changes")
