from corpus import rubrik
import MySQLdb as mysql

def run(helper, options):
	# helper
	helper.event('_connection test', 'Connecting to Rubrik')
	rubrik_connection = rubrik.Rubrik(helper)
	helper.end_event(description="Successful Connection")

	# Getting all of the VMs
	helper.event('get_current_status', 'Getting the current status of workflows')
	curd = helper.db.cursor(mysql.cursors.DictCursor)
	curd.execute("SELECT `id`, `name`, `enable_backup` FROM `systems` WHERE `decom_date` IS NULL")
	vms_in_server = curd.fetchall()
	helper.end_event(description='Retrieved all the systems')

	helper.event('_retrieve_sla_doms', 'Getting SLA domains')
	# retrieve the domains
	sla_domains = rubrik_connection.get_sla_domains()
	local_domains = []
	# go through the domains and keep the domains
	for domain in sla_domains['data']:
		local_domains.append(domain['name'])
	helper.end_event(description='SLA domains retrieved')

	helper.event('_vm_task', 'Finding details for VMs')

	for cortex_vm_data in vms_in_server:
		# retrieving the info that Rubrik has on the device
		rubrik_vm_data = rubrik_connection.get_vm(cortex_vm_data['name'])
		
		# if rubrik doesn't have any data on it, there's nothing we can do.
		# this should NOT happen though - it's possbily pointing to user error.
		if rubrik_vm_data == None:
			helper.event("flash_1", cortex_vm_data['name'] + ' does not exist in Rubrik', oneshot=True, success=False, warning=True)
		# if cortex is set to backup but rubrik isn't, update the rubrik to the default for the box's environment
		elif cortex_vm_data['enable_backup'] == 1 and rubrik_vm_data['configuredSlaDomainName'] == 'Do Not Protect':
			helper.event("flash_1", cortex_vm_data['name'] + " has no rubrik SLA domain, setting default for environment", oneshot=True, success=True, warning=False)
			updated_vm = rubrik_vm_data
			curd.execute("SELECT `cmdb_environment` FROM `systems_info_view` WHERE name = " + cortex_vm_data['name'])
			updated_vm['configuredSlaDomainName'] = curd.fetchone()
			rubrik_connection.update_vm(cortex_vm_data['id'], update_vm)
		# if cortex is not backing up but rubrik is, DO NOT change but instead report this.
		elif cortex_vm_data['enable_backup'] == 0 and rubrik_vm_data['configuredSlaDomainName'] != 'Do Not Protect':
			helper.event("flash_1", cortex_vm_data['name'] + " is set to not backup but this system is set to backup in Rubrik. Please check and confirm that this is correct.", oneshot=True, success=True, warning=True)
		# if cortex and rubrik are both doing the correct thing, don't change anything
		elif cortex_vm_data['enable_backup'] == 1 and rubrik_vm_data['configuredSlaDomainName'] in local_domains:
			helper.event("flash_1", cortex_vm_data['name'] + " is in rubrik and is set to backup", oneshot=True, success=True, warning=False)
		else:
			helper.event("flash_1", "Something went wrong with " + cortex_vm_data['name'], oneshot=True, success=False, warning=False)
	
	helper.end_event(description=vms_in_server)