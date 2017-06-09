#### Allocate server task

def run(helper, options):
	# Configuration of task
	puppet_cert_domain = options['wfconfig']['PUPPET_CERT_DOMAIN']

	## Allocate a hostname #################################################

	# Start the task
	helper.event("allocate_name", "Allocating a '" + options['classname'] + "' system name")

	# Allocate the name
	system_info = helper.lib.allocate_name(options['classname'], options['purpose'], helper.username)

	# system_info is a dictionary containg a single { 'hostname': database_id }. Extract both of these:
	system_name = system_info.keys()[0]
	system_dbid = system_info.values()[0]

	# End the event
	helper.end_event(description="Allocated system name " + system_name)



	## Allocate an IPv4 Address and create a host object ###################

	if options['alloc_ip']:
		# Start the event
		helper.event("allocate_ipaddress", "Allocating an IP address from " + options['network'])
	
		# Allocate an IP address
		ipv4addr = helper.lib.infoblox_create_host(system_name + "." + options['domain'], options['network'])
	
		# Handle errors - this will stop the task
		if ipv4addr is None:
			raise Exception('Failed to allocate an IP address')

		# End the event
		helper.end_event(description="Allocated the IP address " + ipv4addr)
	else:
		ipv4addr = ''



	## Create the ServiceNow CMDB CI #######################################

	# Start the event
	helper.event("sn_create_ci", "Creating ServiceNow CMDB CI")
	sys_id = None
	cmdb_id = None

	if options['os_type'] == helper.lib.OS_TYPE_BY_NAME['Linux']:
		os_name = 'Other Linux'
	elif options['os_type'] == helper.lib.OS_TYPE_BY_NAME['Windows']:
		os_name = 'Not Required'
	elif options['os_type'] == helper.lib.OS_TYPE_BY_NAME['ESXi']:
		os_name = 'ESXi'
	elif options['os_type'] == helper.lib.OS_TYPE_BY_NAME['Solaris']:
		os_name = 'Solaris'

	# Failure does not kill the task
	try:
		# Create the entry in ServiceNow
		(sys_id, cmdb_id) = helper.lib.servicenow_create_ci(ci_name=system_name, os_type=options['os_type'], os_name=os_name, virtual=options['is_virtual'], environment=options['env'], short_description=options['purpose'], comments=options['comments'], ipaddr=ipv4addr)

		# Update Cortex systems table row with the sys_id
		helper.lib.set_link_ids(system_dbid, cmdb_id=sys_id, vmware_uuid=None)

		# End the event
		helper.end_event(success=True, description="Created ServiceNow CMDB CI")
	except Exception as e:
		helper.end_event(success=False, description="Failed to create ServiceNow CMDB CI")



	## Register Linux VMs with the built in Puppet ENC #####################

	# Only for Linux VMs...
	if options['os_type'] == helper.lib.OS_TYPE_BY_NAME['Linux']:
		# Start the event
		helper.event("puppet_enc_register", "Registering with Puppet ENC")

		# Register with the Puppet ENC
		helper.lib.puppet_enc_register(system_dbid, system_name + "." + puppet_cert_domain, options['env'])

		# End the event
		helper.end_event("Registered with Puppet ENC")



	## Link ticket to CI ###################################################

	# If we succeeded in creating a CI, try linking the task
	if sys_id is not None and options['task'] is not None and len(options['task'].strip()) != 0:
		# Start the event
		helper.event("sn_link_task_ci", "Linking ServiceNow Task to CI")

		# Failure does not kill the task
		try:
			# Link the ServiceNow task to the CI
			link_sys_id = helper.lib.servicenow_link_task_to_ci(sys_id, options['task'].strip())

			# End the event
			helper.end_event(success=True, description="Linked ServiceNow Task to CI")
		except Exception as e:
			helper.end_event(success=False, description="Failed to link ServiceNow Task to CI. " + str(e))
