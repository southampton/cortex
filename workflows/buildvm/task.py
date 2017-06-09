#### Combined standard/sandbox VM Workflow Task
import time

def run(helper, options):

	# Find out which workflow we're wanting to run
	workflow = options['workflow']

	# Configuration of task
	if workflow == 'standard':
		prefix = options['wfconfig']['PREFIX']
		vcenter_tag = options['wfconfig']['VCENTER_TAG']
		domain = options['wfconfig']['DOMAIN']
		network = options['wfconfig']['NETWORK']
		gateway = options['wfconfig']['GATEWAY']
		netmask = options['wfconfig']['NETMASK']
		dns_servers = options['wfconfig']['DNS_SERVERS']
		dns_domain = options['wfconfig']['DNS_DOMAIN']
		puppet_cert_domain = options['wfconfig']['PUPPET_CERT_DOMAIN']
		win_full_name = options['wfconfig']['WIN_FULL_NAME']
		win_org_name = options['wfconfig']['WIN_ORG_NAME']
		win_location = options['wfconfig']['WIN_LOCATION']
		win_os_domain = options['wfconfig']['WIN_OS_DOMAIN']
		win_dev_os_domain = options['wfconfig']['WIN_DEV_OS_DOMAIN']
		sn_location = options['wfconfig']['SN_LOCATION']
		network_name = options['wfconfig']['NETWORK_NAME']
		cluster_storage_pools = options['wfconfig']['CLUSTER_STORAGE_POOLS']
		cluster_rpool = options['wfconfig']['CLUSTER_RPOOL']
		notify_emails = options['notify_emails']
		win_groups = options['wfconfig']['WIN_GROUPS']
		os_templates = options['wfconfig']['OS_TEMPLATES']
		os_names = options['wfconfig']['OS_NAMES']
		os_disks = options['wfconfig']['OS_DISKS']
		vm_folder_name = None
	elif workflow == 'sandbox':
		prefix = options['wfconfig']['SB_PREFIX']
		vcenter_tag = options['wfconfig']['SB_VCENTER_TAG']
		domain = options['wfconfig']['SB_DOMAIN']
		puppet_cert_domain = options['wfconfig']['SB_PUPPET_CERT_DOMAIN']
		win_full_name = options['wfconfig']['SB_WIN_FULL_NAME']
		win_org_name = options['wfconfig']['SB_WIN_ORG_NAME']
		win_location = options['wfconfig']['SB_WIN_LOCATION']
		win_os_domain = options['wfconfig']['SB_WIN_OS_DOMAIN']
		win_dev_os_domain = options['wfconfig']['SB_WIN_DEV_OS_DOMAIN']
		sn_location = options['wfconfig']['SB_SN_LOCATION']
		network_name = options['wfconfig']['SB_NETWORK_NAME']
		cluster_storage_pools = options['wfconfig']['SB_CLUSTER_STORAGE_POOLS']
		cluster_rpool = options['wfconfig']['SB_CLUSTER_RPOOL']
		win_groups = options['wfconfig']['SB_WIN_GROUPS']
		os_templates = options['wfconfig']['SB_OS_TEMPLATES']
		os_names = options['wfconfig']['SB_OS_NAMES']
		os_disks = options['wfconfig']['SB_OS_DISKS']
		vm_folder_name = None
	elif workflow == 'student':
		prefix = options['wfconfig']['STU_PREFIX']
		vcenter_tag = options['wfconfig']['STU_VCENTER_TAG']
		domain = options['wfconfig']['STU_DOMAIN']
		win_full_name = options['wfconfig']['STU_WIN_FULL_NAME']
		win_org_name = options['wfconfig']['STU_WIN_ORG_NAME']
		win_location = options['wfconfig']['STU_WIN_LOCATION']
		win_os_domain = options['wfconfig']['STU_WIN_OS_DOMAIN']
		win_dev_os_domain = options['wfconfig']['STU_WIN_DEV_OS_DOMAIN']
		sn_location = options['wfconfig']['STU_SN_LOCATION']
		network_name = options['wfconfig']['STU_NETWORK_NAMES'][options['network']]
		cluster_storage_pools = options['wfconfig']['STU_CLUSTER_STORAGE_POOLS']
		win_groups = options['wfconfig']['STU_WIN_GROUPS']
		os_templates = options['wfconfig']['STU_OS_TEMPLATES']
		os_names = options['wfconfig']['STU_OS_NAMES']
		os_disks = options['wfconfig']['STU_OS_DISKS']
		vm_folder_name = option['wfconfig']['STU_VM_FOLDER']

	## Allocate a hostname #################################################

	# Start the task
	helper.event("allocate_name", "Allocating a '" + prefix + "' system name")

	# Allocate the name
	system_info = helper.lib.allocate_name(prefix, options['purpose'], helper.username, expiry=options['expiry'])

	# system_info is a dictionary containg a single { 'hostname': database_id }. Extract both of these:
	system_name = system_info.keys()[0]
	system_dbid = system_info.values()[0]

	# End the event
	helper.end_event(description="Allocated system name " + system_name)



	## Allocate an IPv4 Address and create a host object (standard only) ###

	if workflow == 'standard':
		# Start the event
		helper.event("allocate_ipaddress", "Allocating an IP address from " + network)

		# Allocate an IP address
		ipv4addr = helper.lib.infoblox_create_host(system_name + "." + domain, network)

		# Handle errors - this will stop the task
		if ipv4addr is None:
			raise Exception('Failed to allocate an IP address')

		# End the event
		helper.end_event(description="Allocated the IP address " + ipv4addr)
	else:
		ipv4addr = None



	## Create the virtual machine post-clone specification #################

	# Start the event
	helper.event("vm_clone", "Creating the virtual machine using VMware API")

	# Pull some information out of the configuration
	template_name = os_templates[options['template']]
	os_name =       os_names[options['template']]
	os_disk_size =  os_disks[options['template']]

	# For RHEL6, RHEL7 or Ubuntu:
	if options['template'] in ['rhel6', 'rhel7', 'rhel6c', 'ubuntu_14.04_lts']:
		os_type = helper.lib.OS_TYPE_BY_NAME['Linux']
		vm_spec = None

	# For Server 2012R2
	elif options['template'] == 'windows_server_2012' or options['template'] == 'windows_server_2016' or options['template'] == 'windows_server_2016_core':
		os_type = helper.lib.OS_TYPE_BY_NAME['Windows']

		# Build a customisation spec depending on the environment to use the correct domain details
		if workflow == 'standard':
			if options['env'] == 'dev':
				vm_spec = helper.lib.vmware_vm_custspec(dhcp=False, gateway=gateway, netmask=netmask, ipaddr=ipv4addr, dns_servers=dns_servers, dns_domain=dns_domain, os_type=os_type, os_domain='devdomain.soton.ac.uk', timezone=85, domain_join_user=helper.config['AD_DEV_JOIN_USER'], domain_join_pass=helper.config['AD_DEV_JOIN_PASS'], fullname=win_full_name, orgname=win_org_name)
			else:
				vm_spec = helper.lib.vmware_vm_custspec(dhcp=False, gateway=gateway, netmask=netmask, ipaddr=ipv4addr, dns_servers=dns_servers, dns_domain=dns_domain, os_type=os_type, os_domain='soton.ac.uk', timezone=85, domain_join_user=helper.config['AD_PROD_JOIN_USER'], domain_join_pass=helper.config['AD_PROD_JOIN_PASS'], fullname=win_full_name, orgname=win_org_name)
		elif workflow in ['sandbox', 'student']:
			if options['env'] == 'dev':
				vm_spec = helper.lib.vmware_vm_custspec(dhcp=True, os_type=os_type, os_domain=win_dev_os_domain, timezone=85, domain_join_user=helper.config['AD_DEV_JOIN_USER'], domain_join_pass=helper.config['AD_DEV_JOIN_PASS'], fullname=win_full_name, orgname=win_org_name)
			else:
				vm_spec = helper.lib.vmware_vm_custspec(dhcp=True, os_type=os_type, os_domain=win_os_domain, timezone=85, domain_join_user=helper.config['AD_PROD_JOIN_USER'], domain_join_pass=helper.config['AD_PROD_JOIN_PASS'], fullname=win_full_name, orgname=win_org_name)


	# Anything else
	else:
		raise RuntimeError("Unknown template specified")

	# Connect to vCenter
	si = helper.lib.vmware_smartconnect(vcenter_tag)

	# Get the vm folder to use if any
	vm_folder = None
	if vm_folder_name is not None:
		vm_folder = vm_folder_name

	elif "default_folder" in helper.config['VMWARE'][vcenter_tag]:
		vm_folder = helper.config['VMWARE'][vcenter_tag]['default_folder']

	# Get the vm resource pool to use if any
	vm_rpool = cluster_rpool.get(options['cluster'], "Root Resource Pool")

	# Launch the task to clone the virtual machine
	task = helper.lib.vmware_clone_vm(si, template_name, system_name, vm_rpool=vm_rpool, vm_cluster=options['cluster'], custspec=vm_spec, vm_folder=vm_folder, vm_network=network_name, vm_datastore_cluster=cluster_storage_pools[options['cluster']])
	helper.lib.vmware_task_complete(task, "Failed to create the virtual machine")

	# End the event
	helper.end_event(description="Created the virtual machine successfully")

	# Get the VM object (so we can reconfigure it)
	vm = task.info.result

	# If we don't have a VM, then kill the task
	if vm == None:
		raise RuntimeError("VM creation failed: VMware API did not return a VM object reference")



	## Configure vCPUs #####################################################

	# Start the event
	helper.event("vm_reconfig_cpu", "Setting VM CPU configuration")

	# Get total CPUs desired from our options
	total_cpu = int(options['sockets']) * int(options['cores'])

	# Get number of cores per socket
	cpus_per_core = int(options['cores'])
	
	# Reconfigure the VM
	task = helper.lib.vmware_vmreconfig_cpu(vm, total_cpu, cpus_per_core)
	helper.lib.vmware_task_complete(task, "Failed to set vCPU configuration")

	# End the event
	helper.end_event(description="VM vCPU configuation saved")



	## Configure RAM #######################################################

	# Start the event
	helper.event("vm_reconfig_ram", "Setting VM RAM configuration")

	# Reconfigure the VM
	task = helper.lib.vmware_vmreconfig_ram(vm, int(options['ram']) * 1024)
	helper.lib.vmware_task_complete(task, "Failed to set RAM configuration")

	# End the event
	helper.end_event(description="VM RAM configuation saved")



	## Configure Disk ######################################################

	# Add disk to the VM
	if int(options['disk']) > 0:
		# Start the event
		helper.event("vm_add_disk", "Adding data disk to the VM")

		# Reconfigure the VM to add the disk
		task = helper.lib.vmware_vm_add_disk(vm, int(options['disk']) * 1024 * 1024 * 1024)
		helper.lib.vmware_task_complete(task, "Could not add data disk to VM")

		# End the event
		helper.end_event(description="Data disk added to VM")



	## Set up annotation ###################################################

	# Start the event
	helper.event("vm_config_notes", "Setting VM notes annotation")

	# Failure of the following does not kill the task
	try:
		# Set the notes
		task = helper.lib.vmware_vmreconfig_notes(vm, options['purpose'])

		# End the event
		helper.lib.vmware_task_complete(task, "VM notes annotation set")
	except Exception as e:
		helper.end_event(success=False, description="Failed to set VM notes annotation: " + str(e))



	## Update Cortex Cache #################################################

	# We do this so that we don't have to wait for the next run of the 
	# scheduled VMware import). We do this before powering the VM on 'cos
	# the cache must be up to date before the installers run inside the VM.

	# Start the event
	helper.event("update_cache", "Updating Cortex VM cache item")

	# Failure of this does not kill the task
	try:
		# Update the cache item
		helper.lib.update_vm_cache(vm, vcenter_tag)

		# End the event
		helper.end_event("Updated Cortex VM cache item")
	except Exception as e:
		helper.end_event(success=False, description="Failed to update Cortex VM cache item - VMware information may be incorrect")



	## Power on the VM #####################################################

	# Start the event
	helper.event("vm_poweron", "Powering the VM on for the first time")

	# Set up the necessary values in redis
	helper.lib.redis_set_vm_data(vm, "hostname", system_name)
	if workflow == 'standard':
		helper.lib.redis_set_vm_data(vm, "ipaddress", ipv4addr)
	elif workflow in ['sandbox', 'student']:
		helper.lib.redis_set_vm_data(vm, "ipaddress", 'dhcp')

	# Power on the VM
	task = helper.lib.vmware_vm_poweron(vm)
	helper.lib.vmware_task_complete(task, "Could not power on the VM")

	# If we've not powered on within 30 seconds, fail
	if not helper.lib.vmware_wait_for_poweron(vm, 30):
		helper.end_event(success=False, description="VM not powered on after 30 seconds. Check vCenter for more information")

	# End the event
	helper.end_event(description="VM powered up")	



	## Register Linux VMs with the built in Puppet ENC #####################

	# Only for Linux VMs...
	if os_type == helper.lib.OS_TYPE_BY_NAME['Linux'] and options['template'] != 'rhel6c':
		# Start the event
		helper.event("puppet_enc_register", "Registering with Puppet ENC")

		# Register with the Puppet ENC
		helper.lib.puppet_enc_register(system_dbid, system_name + "." + puppet_cert_domain, options['env'])

		# End the event
		helper.end_event("Registered with Puppet ENC")



	## Create the ServiceNow CMDB CI #######################################

	# Start the event
	helper.event("sn_create_ci", "Creating ServiceNow CMDB CI")
	sys_id = None
	cmdb_id = None

	# Failure does not kill the task
	try:
		# Create the entry in ServiceNow
		(sys_id, cmdb_id) = helper.lib.servicenow_create_ci(ci_name=system_name, os_type=os_type, os_name=os_name, sockets=int(options['sockets']), cores_per_socket=int(options['cores']), ram_mb=int(options['ram']) * 1024, disk_gb=int(options['disk']) + os_disk_size, environment=options['env'], short_description=options['purpose'], comments=options['comments'], location=sn_location, ipaddr=ipv4addr)

		# Update Cortex systems table row with the sys_id
		helper.lib.set_link_ids(system_dbid, cmdb_id=sys_id, vmware_uuid=vm.config.uuid)

		# End the event
		helper.end_event(success=True, description="Created ServiceNow CMDB CI")
	except Exception as e:
		helper.end_event(success=False, description="Failed to create ServiceNow CMDB CI")



	## Link ticket to CI (standard VM only) ################################

	# If we succeeded in creating a CI, try linking the task
	if workflow == 'standard' and sys_id is not None and options['task'] is not None and len(options['task'].strip()) != 0:
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



	## Wait for the VM to finish building ##################################

	# Linux has separate events for installation starting and installation
	# finishing, but windows only has installation finishing
	if os_type == helper.lib.OS_TYPE_BY_NAME['Linux']:
		# Start the event
		helper.event('guest_installer_progress', 'Waiting for in-guest installation to start')

		# Wait for the in-guest installer to set the state to 'progress' or 'done'
		wait_response = helper.lib.wait_for_guest_notify(vm, ['inprogress', 'done'])

		# When it returns, end the event
		if wait_response is None or wait_response not in ['inprogress', 'done']:
			helper.end_event(success=False, description='Timed out waiting for in-guest installation to start')

			# End the task here
			return
		else:
			helper.end_event(success=True, description='In-guest installation started')

	# Start another event
	helper.event('guest_installer_done', 'Waiting for in-guest installation to finish')

	# Wait for the in-guest installer to set the state to 'progress' or 'done'
	wait_response = helper.lib.wait_for_guest_notify(vm, ['done'])

	# When it returns, end the event
	if wait_response is None or wait_response not in ['done']:
		helper.end_event(success=False, description='Timed out waiting for in-guest installation to finish')
	else:
		helper.end_event(success=True, description='In-guest installation finished')



	## For Windows VMs, join groups and stuff ##############################

	if os_type == helper.lib.OS_TYPE_BY_NAME['Windows']:
		# Put in Default OU (failure does not kill task)
		try:
			# Start the event
			helper.event('windows_move_ou', 'Moving Computer object to Default OU')

			# Run RPC to put in default OU
			helper.lib.windows_move_computer_to_default_ou(system_name, options['env'])

			# End the event
			helper.end_event(success=True, description='Moved Computer object to Default OU')
		except Exception as e:
			helper.end_event(success=False, description='Failed to put Computer object in OU: ' + str(e))

		# Join default groups (failure does not kill task)
		try:
			# Start the event
			helper.event('windows_join_groups', 'Joining default groups')

			# Run RPC to join groups
			helper.lib.windows_join_groups(system_name, options['env'], win_groups[options['env']])

			# End the event
			helper.end_event(success=True, description='Joined default groups')
		except Exception as e:
			helper.end_event(success=False, description='Failed to join default groups: ' + str(e))

		# Set up computer information (failure does not kill task)
		try:
			# Start the event
			helper.event('windows_set_info', 'Setting Computer object attributes')

			# Run RPC to set information
			helper.lib.windows_set_computer_details(system_name, options['env'], options['purpose'], win_location)

			# End the event
			helper.end_event(success=True, description='Computer object attributes set')
		except Exception as e:
			helper.end_event(success=False, description='Failed to set Computer object attributes: ' + str(e))

		# Wait for 60 seconds to allow time for the VM to come back up
		# This feels like a bit of a hack currently, but we don't have
		# a way currently of knowing if the VM is up.
		helper.event('windows_delay', 'Wait and restart guest')
		time.sleep(60)

		# Restart the guest
		helper.lib.vmware_vm_restart_guest(vm)
		helper.end_event(success=True, description='Initiated guest restart')



	## Send success email ##################################################

	# Build the text of the message
	message  = 'Cortex has finished building your VM. The details of the VM can be found below.\n'
	message += '\n'
	if workflow in ['standard', 'sandbox']:
		if workflow == 'standard':
			message += 'ServiceNow Task: ' + str(options['task']) + '\n'
		message += 'Hostname: ' + str(system_name) + '.' + str(domain) + '\n'
		if ipv4addr is not None:
			message += 'IP Address: ' + str(ipv4addr) + '\n'
		message += 'VMware Cluster: ' + str(options['cluster']) + '\n'
		message += 'Purpose: ' + str(options['purpose']) + '\n'
		message += 'Operating System: ' + str(os_name) + '\n'
		message += 'CPUs: ' + str(total_cpu) + '\n'
		message += 'RAM: ' + str(options['ram']) + ' GiB\n'
		message += 'Data Disk: ' + str(options['disk']) + ' GiB\n'
		message += '\n'
		message += 'The event log for the task can be found at https://' + str(helper.config['CORTEX_DOMAIN']) + '/task/status/' + str(helper.task_id) + '\n'
		message += 'More information about the VM, can be found on the Cortex systems page at https://' + str(helper.config['CORTEX_DOMAIN']) + '/systems/edit/' + str(system_dbid) + '\n'
		if sys_id is not None:
			message += 'The ServiceNow CI entry is available at ' + (helper.config['CMDB_URL_FORMAT'] % sys_id) + '\n'
		else:
			message += 'A ServiceNow CI was not created. For more information, see the task event log.\n'

		message += '\nPlease remember to move the virtual machine into an appropriate folder in vCenter'
		if os_type == helper.lib.OS_TYPE_BY_NAME['Windows']:
			message += ' and to an appropriate OU in Active Directory'
		message += '\n'
	else:
		message += 'Purpose: ' + str(options['purpose']) + '\n'
		message += 'Operating System: ' + str(os_name) + '\n'
		message += 'CPUs: ' + str(total_cpu) + '\n'
		message += 'RAM: ' + str(options['ram']) + ' GiB\n'
		message += '\n'
		message += 'The event log for the task can be found at https://' + str(helper.config['CORTEX_DOMAIN']) + '/task/status/' + str(helper.task_id) + '\n'
		message += 'More information about the VM, can be found on the Cortex systems page at https://' + str(helper.config['CORTEX_DOMAIN']) + '/systems/edit/' + str(system_dbid) + '\n'
		

	# Send the message to the user who started the task (if they want it)
	if options['sendmail']:
		helper.lib.send_email(helper.username, 'Cortex has finished building your VM, ' + str(system_name), message)

	# For standard VMs only, always notify people in the notify_emails list
	if workflow == 'standard':
		for email in notify_emails: 
			helper.lib.send_email(email, 'Cortex has finished building a VM, ' + str(system_name), message)
