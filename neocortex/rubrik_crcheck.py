from corpus import rubrik
import MySQLdb as mysql

def run(helper, options):
	## GET ALL THE VMS

	helper.event('get_current_status', 'Getting the current Cortex-defined backup status of systems')
	curd = helper.db.cursor(mysql.cursors.DictCursor)
	curd.execute("SELECT `id`, `name`, `cmdb_environment`, `enable_backup` FROM `systems_info_view` WHERE `decom_date` IS NULL AND `enable_backup` != 2")
	vms_in_server = curd.fetchall()
	helper.end_event(description='Retrieved all the systems')


	## GET SLA DOMAINS FROM RUBRIK

	helper.event('_retrieve_sla_doms', 'Getting SLA domains')

	# Retrieve the domains
	rubrik_connection = rubrik.Rubrik(helper)
	sla_domains = rubrik_connection.get_sla_domains()

	# Go through the domains and keep the domains
	local_domains = [ domain['name'] for domain in sla_domains['data'] ]

	# Create a map of SLA-Domain-Name to SLA-Domain-Id
	sla_name_id_map = { d['name']: d['id'] for d in sla_domains['data'] }

	helper.end_event(description='SLA domains retrieved')

	# Map environment names to SLA domains
	env_to_sla_map = { e['name']: e['rubrik_sla'] for e in helper.config['ENVIRONMENTS'] }


	## UPDATE SLA DOMAINS AS NECESSARY

	helper.event('_vm_task', 'Reviewing VM SLA assignments')
	changes = 0
	for cortex_vm_data in vms_in_server:
		# retrieving the info that Rubrik has on the device
		rubrik_vm_data = rubrik_connection.get_vm(cortex_vm_data['name'])
		
		# If Rubrik doesn't have any data on it, there's nothing we can do. This should NOT happen though - it's possibly pointing to user error
		if rubrik_vm_data == None:
			helper.event("_rubrik_unknown", cortex_vm_data['name'] + ' does not exist in Rubrik', oneshot=True, success=False, warning=True)

		# If Cortex is set to backup but Rubrik isn't, update the Rubrik to the default for the box's environment
		elif cortex_vm_data['enable_backup'] == 1 and rubrik_vm_data['effectiveSlaDomainId'] == 'UNPROTECTED':
			helper.event("_rubrik_setdefault", cortex_vm_data['name'] + " has no Rubrik SLA domain, setting default for environment", oneshot=True, success=True, warning=False)

			cmdb_environment = cortex_vm_data['cmdb_environment']

			if cmdb_environment is not None:
				# Map the SLA domain to the default for the environment, and then map it to 
				# it's ID (we can't set it in Rubrik by name)
				updated_vm = {}
				updated_vm['configuredSlaDomainId'] = sla_name_id_map[env_to_sla_map[cmdb_environment]]

				# Make the change
				rubrik_connection.update_vm(rubrik_vm_data['id'], updated_vm)
				changes = changes + 1
			else:
				helper.event("_rubrik_warn", cortex_vm_data['name'] + " has no CMDB environment set - unable to set a default SLA domain", oneshot=True, success=True, warning=True)

		# If Cortex is not backing up but Rubrik is, DO NOT change but instead report this.
		elif cortex_vm_data['enable_backup'] == 0 and rubrik_vm_data['effectiveSlaDomainId'] != 'UNPROTECTED':
			helper.event("_rubrik_warn", cortex_vm_data['name'] + " is set to not backup but this system is set to backup in Rubrik. Please check and confirm that this is correct", oneshot=True, success=True, warning=True)

		# If Cortex is set to not backup, and Rubrik isn't backing up, don't change anything
		elif cortex_vm_data['enable_backup'] == 0 and rubrik_vm_data['effectiveSlaDomainId'] == 'UNPROTECTED':
			helper.event("_rubrik_correct", cortex_vm_data['name'] + " is not configured to backup", oneshot=True, success=True, warning=False)

		# If Cortex and Rubrik are both backing up, don't change anything
		elif cortex_vm_data['enable_backup'] == 1 and rubrik_vm_data['configuredSlaDomainName'] in local_domains:
			helper.event("_rubrik_correct", cortex_vm_data['name'] + " is in Rubrik and is set to backup", oneshot=True, success=True, warning=False)

		else:
			helper.event("_rubrik_error", "Something went wrong with " + cortex_vm_data['name'], oneshot=True, success=False, warning=False)
	
	# Oneshot this as the original _vm_task event above may have already ended
	helper.event("_rubrik_end", "VM SLA assignments updated: " + str(changes) + " changes made", oneshot=True)
