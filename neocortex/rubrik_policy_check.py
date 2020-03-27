from corpus import rubrik
import MySQLdb as mysql

def run(helper, options):
	## GET ALL THE VMS

	helper.event('_get_current_status', 'Getting the current Cortex-defined backup status of systems')
	curd = helper.db.cursor(mysql.cursors.DictCursor)
	curd.execute("SELECT * FROM `systems_info_view` WHERE `decom_date` IS NULL AND `enable_backup` != 2")
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
		vm_link = '{{system_link id="' + str(cortex_vm_data['id']) + '"}}' + cortex_vm_data['name'] + '{{/system_link}}'

		# Retrieving the info that Rubrik has on the device
		try:
			rubrik_vm_data = rubrik_connection.get_vm(cortex_vm_data)
		except Exception as e:
			rubrik_vm_data = None

		# Get the system's OS type using the cmdb_os field:
		if cortex_vm_data["cmdb_os"] and "linux" in cortex_vm_data["cmdb_os"].lower():
			os_type = "linux"
		elif cortex_vm_data["cmdb_os"] and "windows" in cortex_vm_data["cmdb_os"].lower():
			os_type = "windows"
		else:
			os_type = "unknown"

		# If Rubrik doesn't have any data on it, there's nothing we can do. This should NOT happen though - it's possibly pointing to user error
		if rubrik_vm_data is None:
			helper.event("_rubrik_unknown", "{vm_link} does not exist in Rubrik", oneshot=True, success=False, warning=True)
		else:
			# Create an empty dictionary for updating the VM
			updated_vm = {}

			# Backup Policy: If cortex is not in the 'unknown - do not change' mode:
			if cortex_vm_data['enable_backup'] != 2:
				# If Cortex is set to backup but Rubrik isn't, update the Rubrik to the default for the box's environment
				if cortex_vm_data['enable_backup'] == 1 and rubrik_vm_data['effectiveSlaDomainId'] == 'UNPROTECTED':
					if cortex_vm_data['cmdb_environment'] is not None:
						helper.event("_rubrik_changed", "{vm_link} has no Rubrik SLA domain - setting default for environment".format(vm_link=vm_link), oneshot=True, changed=True)
						# Map the SLA domain to the default for the environment, and then map it to
						# it's ID (we can't set it in Rubrik by name)
						#updated_vm['configuredSlaDomainId'] = sla_name_id_map[env_to_sla_map[cortex_vm_data['cmdb_environment']]]
					else:
						helper.event("_rubrik_warn", "{vm_link} has no CMDB environment set - unable to set a default SLA domain".format(vm_link=vm_link), oneshot=True, warning=True)

				# If Cortex is not backing up but Rubrik is, DO NOT change but instead report this.
				elif cortex_vm_data['enable_backup'] == 0 and rubrik_vm_data['effectiveSlaDomainId'] != 'UNPROTECTED':
					helper.event("_rubrik_warn", "{vm_link} is set to not backup but has a Rubrik SLA domain set - please check and confirm that this is correct".format(vm_link=vm_link), oneshot=True, warning=True)

				# If Cortex is set to not backup, and Rubrik isn't backing up, don't change anything
				elif cortex_vm_data['enable_backup'] == 0 and rubrik_vm_data['effectiveSlaDomainId'] == 'UNPROTECTED':
					helper.event("_rubrik_correct", "{vm_link} is configured to not backup and has no Rubrik SLA domain set".format(vm_link=vm_link), oneshot=True)

				# If Cortex and Rubrik are both backing up, don't change anything
				elif cortex_vm_data['enable_backup'] == 1 and rubrik_vm_data['configuredSlaDomainName'] in local_domains:
					helper.event("_rubrik_correct", "{vm_link} is configured to backup and has a Rubrik SLA domain set".format(vm_link=vm_link), oneshot=True)

				else:
					# Logically, we shouldn't get here
					helper.event("_rubrik_error", "Something went wrong with {vm_link}".format(vm_link=vm_link), oneshot=True, success=False)


			# Backup Scripts: If cortex is not in the 'unknown - do not change' mode:
			if cortex_vm_data["enable_backup_scripts"] != 2:
				# If Cortex is set to enable backup scripts but could not find them in Rubrik we change them
				if cortex_vm_data["enable_backup_scripts"] == 1 and not all(k in rubrik_vm_data for k in ["preBackupScript", "postSnapScript", "postBackupScript"]):
					helper.event("_rubrik_changed", "{vm_link} has no backup scripts configured - setting the default for OS type {os_type}".format(vm_link=vm_link, os_type=os_type.title()), oneshot=True, changed=True)
					# Update the VM based on the backup script config.
					for key, value in helper.config["RUBRIK_BACKUP_SCRIPT_CONFIG"].get(os_type, {}).items():
						updated_vm[key] = value
				# If Cortex is set to disable backup scripts but one or more are configured in Rubrik
				elif cortex_vm_data["enable_backup_scripts"] == 0 and any(k in rubrik_vm_data for k in ["preBackupScript", "postSnapScript", "postBackupScript"]):
					helper.event("_rubrik_warn", "{vm_link} has backup scripts disabled in Cortex but one or more configured in Rubrik".format(vm_link=vm_link), oneshot=True, warning=True)
				# If Cortex is set to disable backup scripts and none are configured in Rubrik
				elif cortex_vm_data["enable_backup_scripts"] == 0 and all(k not in rubrik_vm_data for k in ["preBackupScript", "postSnapScript", "postBackupScript"]):
					helper.event("_rubrik_correct", "{vm_link} has backup scripts disabled in Cortex and none configured in Rubrik".format(vm_link=vm_link), oneshot=True)
				# If Cortex and Rubrik both have the backup scripts configured
				elif cortex_vm_data["enable_backup_scripts"] == 1 and all(k in rubrik_vm_data for k in ["preBackupScript", "postSnapScript", "postBackupScript"]):
					helper.event("_rubrik_correct", "{vm_link} has backup scripts enabled in both Cortex and Rubrik".format(vm_link=vm_link), oneshot=True)
				# Logically, we shouldn't get here
				else:
					helper.event("_rubrik_error", "Something went wrong when attempting to set backup scripts for {vm_link}".format(vm_link=vm_link), oneshot=True, warning=True)

			# If changes are required to the VM make them
			if updated_vm:
				helper.event("_rubrik_apply_changes", "Applying changes in Rubrik for {vm_link}".format(vm_link=vm_link))
				rubrik_connection.update_vm(rubrik_vm_data['id'], updated_vm)
				changes = changes + 1
				helper.end_event(description="Changes applied successfully for {vm_link}".format(vm_link=vm_link), changed=True)

	# Oneshot this as the original _vm_task event above may have already ended
	helper.event("_rubrik_end", "VM SLA assignments updated: {} changes made".format(changes), oneshot=True)

