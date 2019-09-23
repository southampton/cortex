#### Combined standard/sandbox VM Workflow Task
import requests
import requests.exceptions
import time

def run(helper, options):
	if not helper.lib.checkWorkflowLock():
		raise Exception("Workflows are currently locked")

	# Find out which workflow we're wanting to run
	workflow = options['workflow']

	# Configuration of task
	if workflow == 'standard':
		prefix = options['wfconfig']['PREFIX']
		vcenter_tag = options['wfconfig']['VCENTER_TAG']
		domain = options['wfconfig']['DOMAIN']
		network = options['wfconfig']['NETWORKS'][options['network']]
		gateway = options['wfconfig']['GATEWAYS'][options['network']]
		netmask = options['wfconfig']['NETMASKS'][options['network']]
		if 'NETWORKS6' in options['wfconfig'] and options['network'] in options['wfconfig']['NETWORKS6']:
			network6 = options['wfconfig']['NETWORKS6'][options['network']]
		else:
			network6 = None
		if 'GATEWAYS6' in options['wfconfig'] and options['network'] in options['wfconfig']['GATEWAYS6']:
			gateway6 = options['wfconfig']['GATEWAYS6'][options['network']]
		else:
			gateway6 = None
		if 'NETMASKS6' in options['wfconfig'] and options['network'] in options['wfconfig']['NETMASKS6']:
			netmask6 = options['wfconfig']['NETMASKS6'][options['network']]
		else:
			netmask6 = None
		dns_servers = options['wfconfig']['DNS_SERVERS']
		dns_domain = options['wfconfig']['DNS_DOMAIN']
		puppet_cert_domain = options['wfconfig']['PUPPET_CERT_DOMAIN']
		win_full_name = options['wfconfig']['WIN_FULL_NAME']
		win_org_name = options['wfconfig']['WIN_ORG_NAME']
		win_location = options['wfconfig']['WIN_LOCATION']
		win_os_domain = options['wfconfig']['WIN_OS_DOMAIN']
		win_dev_os_domain = options['wfconfig']['WIN_DEV_OS_DOMAIN']
		sn_location = options['wfconfig']['SN_LOCATION']
		network_name = options['wfconfig']['NETWORK_NAMES'][options['network']]
		cluster_storage_pools = options['wfconfig']['CLUSTER_STORAGE_POOLS']
		cluster_rpool = options['wfconfig']['CLUSTER_RPOOL']
		notify_emails = options['notify_emails']
		win_groups = options['wfconfig']['WIN_GROUPS_BY_TEMPLATE']
		os_templates = options['wfconfig']['OS_TEMPLATES']
		os_names = options['wfconfig']['OS_NAMES']
		os_disks = options['wfconfig']['OS_DISKS']
		os_types = options['wfconfig']['OS_TYPES']
		vm_folder_moid = options['vm_folder_moid']
		dns_aliases = options['dns_aliases']
		set_backup = options['wfconfig']['SET_BACKUP']
		entca_default_san_domain = None
		if 'ENTCA_SERVERS' in options['wfconfig']:
			entca_servers = options['wfconfig']['ENTCA_SERVERS']
		else:   
			entca_servers = None		
	elif workflow == 'sandbox':
		prefix = options['wfconfig']['SB_PREFIX']
		vcenter_tag = options['wfconfig']['SB_VCENTER_TAG']
		domain = options['wfconfig']['SB_DOMAIN']
		dns_domain = options['wfconfig']['SB_DNS_DOMAIN']
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
		win_groups = options['wfconfig']['SB_WIN_GROUPS_BY_TEMPLATE']
		os_templates = options['wfconfig']['SB_OS_TEMPLATES']
		os_names = options['wfconfig']['SB_OS_NAMES']
		os_disks = options['wfconfig']['SB_OS_DISKS']
		os_types = options['wfconfig']['SB_OS_TYPES']
		vm_folder_moid = None
		dns_aliases = []
		set_backup = options['wfconfig']['SB_SET_BACKUP']
		if 'ENTCA_SERVERS' in options['wfconfig']:
			entca_servers = options['wfconfig']['ENTCA_SERVERS']
		else:
			entca_servers = None
		if 'SB_DEFAULT_SAN_DOMAIN' in options['wfconfig']:
			entca_default_san_domain = options['wfconfig']['SB_DEFAULT_SAN_DOMAIN']
		else:
			entca_default_san_domain = None
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
		dns_servers = options['wfconfig']['STU_DNS_SERVERS']
		dns_domain = options['wfconfig']['STU_DNS_DOMAIN']
		network = options['wfconfig']['STU_NETWORKS'][options['network']]
		gateway = options['wfconfig']['STU_GATEWAYS'][options['network']]
		netmask = options['wfconfig']['STU_NETMASKS'][options['network']]
		if 'STU_NETWORKS6' in options['wfconfig'] and options['network'] in options['wfconfig']['STU_NETWORKS6']:
			network6 = options['wfconfig']['STU_NETWORKS6'][options['network']]
		else:
			network6 = None
		if 'STU_GATEWAYS6' in options['wfconfig'] and options['network'] in options['wfconfig']['STU_GATEWAYS6']:
			gateway6 = options['wfconfig']['STU_GATEWAYS6'][options['network']]
		else:
			gateway6 = None
		if 'STU_NETMASKS6' in options['wfconfig'] and options['network'] in options['wfconfig']['STU_NETMASKS6']:
			netmask6 = options['wfconfig']['STU_NETMASKS6'][options['network']]
		else:
			netmask6 = None
		network_name = options['wfconfig']['STU_NETWORK_NAMES'][options['network']]
		cluster_storage_pools = options['wfconfig']['STU_CLUSTER_STORAGE_POOLS']
		cluster_rpool = options['wfconfig']['STU_CLUSTER_RPOOL']
		win_groups = options['wfconfig']['STU_WIN_GROUPS_BY_TEMPLATE']
		os_templates = options['wfconfig']['STU_OS_TEMPLATES']
		os_names = options['wfconfig']['STU_OS_NAMES']
		os_disks = options['wfconfig']['STU_OS_DISKS']
		os_types = options['wfconfig']['STU_OS_TYPES']
		vm_folder_moid = options['wfconfig']['STU_VM_FOLDER']
		dns_aliases = options['dns_aliases']
		set_backup = options['wfconfig']['STU_SET_BACKUP']
		entca_servers = None
		entca_default_san_domain = None

		# Override primary owner to match allocated_by
		options['primary_owner_who'] = helper.username
		options['primary_owner_role'] = 'Student'
	else:
		raise Exception('Invalid buildvm workflow encountered')

	## Allocate a hostname #################################################

	# Start the task
	helper.event("allocate_name", "Allocating a '" + prefix + "' system name")

	# Allocate the name
	system_info = helper.lib.allocate_name(prefix, options['purpose'], helper.username, expiry=options['expiry'], set_backup=set_backup)

	# system_info is a dictionary containg a single { 'name': name, 'id':dbid }. Extract both of these:
	system_name = system_info['name']
	system_dbid = system_info['id']

	# Update the system with some options.
	helper.lib.update_system(
		system_dbid,
		primary_owner_who = options.get('primary_owner_who', None),
		primary_owner_role = options.get('primary_owner_role', None),
		secondary_owner_who = options.get('secondary_owner_who', None),
		secondary_owner_role = options.get('secondary_owner_role', None),	
	)

	# End the event
	helper.end_event(description="Allocated system name: {{system_link id='" + str(system_dbid) + "'}}" + system_name + "{{/system_link}}")

	## Allocate IP Addresses and create a host object (standard or student only) ###

	if workflow in ['standard', 'student']:
		# Generate a network name string
		if network6 is None:
			networkdisplay = network
		else:
			networkdisplay = network + " and " + network6

		# Start the event
		helper.event("allocate_ipaddress", "Allocating an IP addresses from " + networkdisplay)

		# Allocate an IP address
		ipaddrs = helper.lib.infoblox_create_host(system_name + "." + domain, network, network6, aliases=dns_aliases)

		# Handle errors - this will stop the task
		if ipaddrs is None:
			raise Exception('Failed to allocate any IP addresses')
		if ipaddrs["ipv4addr"] is None:
			raise Exception('Failed to allocate an IPv4 address')
		ipv4addr = ipaddrs["ipv4addr"]

		if ipaddrs["ipv6addr"] is None:
			# End the event
			helper.end_event(description="Allocated the IPv4 address " + ipaddrs["ipv4addr"])
		else:
			# End the event
			helper.end_event(description="Allocated the IP addresses " + ipaddrs["ipv4addr"] + " and " + ipaddrs["ipv6addr"])
			ipv6addr = ipaddrs["ipv6addr"]
	else:
		ipv4addr = None
		ipv6addr = None

	## Create the virtual machine post-clone specification #################

	# Start the event
	helper.event("vm_clone", "Creating the virtual machine using VMware API")

	# Pull some information out of the configuration
	template_name = os_templates[options['template']]
	os_name =       os_names[options['template']]
	os_disk_size =  os_disks[options['template']]

	# For RHEL6, RHEL7:
	if options['template'] in os_types['Linux']:
		os_type = helper.lib.OS_TYPE_BY_NAME['Linux']
		vm_spec = None

	# For Server 2012R2
	elif options['template'] in os_types['Windows']:
		os_type = helper.lib.OS_TYPE_BY_NAME['Windows']

		# Build a customisation spec depending on the environment to use the correct domain details
		if workflow == 'standard':
			if options['env'] == 'dev':
				vm_spec = helper.lib.vmware_vm_custspec(dhcp=False, gateway=gateway, netmask=netmask, ipaddr=ipv4addr, dns_servers=dns_servers, dns_domain=dns_domain, os_type=os_type, os_domain='devdomain.soton.ac.uk', timezone=85, domain_join_user=helper.config['AD_DEV_JOIN_USER'], domain_join_pass=helper.config['AD_DEV_JOIN_PASS'], fullname=win_full_name, orgname=win_org_name, ipv6addr=ipv6addr, gateway6=gateway6, netmask6=int(netmask6))
			else:
				vm_spec = helper.lib.vmware_vm_custspec(dhcp=False, gateway=gateway, netmask=netmask, ipaddr=ipv4addr, dns_servers=dns_servers, dns_domain=dns_domain, os_type=os_type, os_domain='soton.ac.uk', timezone=85, domain_join_user=helper.config['AD_PROD_JOIN_USER'], domain_join_pass=helper.config['AD_PROD_JOIN_PASS'], fullname=win_full_name, orgname=win_org_name, ipv6addr=ipv6addr, gateway6=gateway6, netmask6=int(netmask6))
		elif workflow == 'sandbox':
			if options['env'] == 'dev':
				vm_spec = helper.lib.vmware_vm_custspec(dhcp=True, os_type=os_type, os_domain=win_dev_os_domain, timezone=85, domain_join_user=helper.config['AD_DEV_JOIN_USER'], domain_join_pass=helper.config['AD_DEV_JOIN_PASS'], fullname=win_full_name, orgname=win_org_name, ipv6addr=ipv6addr, gateway6=gateway6, netmask6=int(netmask6))
			else:
				vm_spec = helper.lib.vmware_vm_custspec(dhcp=True, os_type=os_type, os_domain=win_os_domain, timezone=85, domain_join_user=helper.config['AD_PROD_JOIN_USER'], domain_join_pass=helper.config['AD_PROD_JOIN_PASS'], fullname=win_full_name, orgname=win_org_name, ipv6addr=ipv6addr, gateway6=gateway6, netmask6=int(netmask6))
		elif workflow == 'student':
			vm_spec = helper.lib.vmware_vm_custspec(dhcp=False, gateway=gateway, netmask=netmask, ipaddr=ipv4addr, dns_servers=dns_servers, dns_domain=dns_domain, os_type=os_type, timezone=85, fullname=win_full_name, orgname=win_org_name, ipv6addr=ipv6addr, gateway6=gateway6, netmask6=int(netmask6))

	# Anything else
	else:
		raise RuntimeError("Unknown template specified")

	# Connect to vCenter
	si = helper.lib.vmware_smartconnect(vcenter_tag)

	# Get the vm folder to use if any
	vm_folder = None
	if vm_folder_moid is not None:
		vm_folder = vm_folder_moid
		folder_is_moid = True

	elif "default_folder" in helper.config['VMWARE'][vcenter_tag]:
		vm_folder = helper.config['VMWARE'][vcenter_tag]['default_folder']
		folder_is_moid = False

	# Get the vm resource pool to use if any
	vm_rpool = cluster_rpool.get(options['cluster'], "Root Resource Pool")

	# Launch the task to clone the virtual machine
	task = helper.lib.vmware_clone_vm(si, template_name, system_name, vm_rpool=vm_rpool, vm_cluster=options['cluster'], custspec=vm_spec, vm_folder=vm_folder, vm_network=network_name, vm_datastore_cluster=cluster_storage_pools[options['cluster']], folder_is_moid=folder_is_moid)
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
	helper.end_event(description="VM vCPU configuation saved: " + str(options['sockets']) + " sockets, " + str(options['cores']) + " cores per socket")



	## Configure RAM #######################################################

	# Start the event
	helper.event("vm_reconfig_ram", "Setting VM RAM configuration")

	# Reconfigure the VM
	task = helper.lib.vmware_vmreconfig_ram(vm, int(options['ram']) * 1024)
	helper.lib.vmware_task_complete(task, "Failed to set RAM configuration")

	# End the event
	helper.end_event(description="VM RAM configuation saved: " + str(options['ram']) + " GiB")



	## Configure Disk ######################################################

	# Add disk to the VM
	if int(options['disk']) > 0:
		# Start the event
		helper.event("vm_add_disk", "Adding data disk to the VM")

		# Reconfigure the VM to add the disk
		task = helper.lib.vmware_vm_add_disk(vm, int(options['disk']) * 1024 * 1024 * 1024)
		helper.lib.vmware_task_complete(task, "Could not add data disk to VM")

		# End the event
		helper.end_event(description="Data disk added to VM: " + str(options['disk']) + " GiB")



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



	## Register Linux VMs with the built in Puppet ENC #####################

	# Only for Linux VMs...
	if workflow != 'student' and os_type == helper.lib.OS_TYPE_BY_NAME['Linux'] and options['template'] != 'rhel6c':
		# Start the event
		helper.event("puppet_enc_register", "Registering with Puppet ENC")

		# Register with the Puppet ENC
		helper.lib.puppet_enc_register(system_dbid, system_name + "." + puppet_cert_domain, options['env'])

		# End the event
		helper.end_event("Registered with Puppet ENC")



	## Create Enterprise CA certificate ####################################

	# Only if we have Enterprise CA configuration and only for Linux VMs...
	if entca_servers is not None and os_type == helper.lib.OS_TYPE_BY_NAME['Linux'] and options['template'] != 'rhel6c':
		# Start the event
		helper.event("entca_create_cert", "Creating certificate on Enterprise CA")

		if type(entca_servers) is str:
			entca_servers = [entca_servers]

		for entca in entca_servers:
			# Build our data for the request
			json_data = {'fqdn': system_name + '.' + entca['entdomain']}
			if entca_default_san_domain is not None:
				json_data = {'sans': [system_name + '.' + entca_default_san_domain]}

			try:
				r = requests.post('https://' + entca['hostname'] + '/create_entca_certificate', json={'fqdn': system_name + '.' + entca['entdomain']}, headers={'Content-Type': 'application/json', 'X-Client-Secret': entca['api_token']}, verify=entca['verify_ssl'])
			except:
				helper.end_event(success=False, description='Error communicating with ' + entca['hostname'])
			else:
				if r.status_code == 200:
					helper.end_event(success=True, description="Created certificate on Enterprise CA")
				else:
					helper.end_event(success=False, description='Error creating certificate on Enterprise CA. Error code: ' + str(r.status_code))



	## Power on the VM #####################################################

	# Start the event
	helper.event("vm_poweron", "Powering the VM on for the first time")

	# Set up the necessary values in redis
	helper.lib.redis_set_vm_data(vm, "hostname", system_name)
	if ipv4addr is not None:
		helper.lib.redis_set_vm_data(vm, "ipaddress", ipv4addr)
		if ipv6addr is not None:
			helper.lib.redis_set_vm_data(vm, "ipv6address", ipv6addr)
	else:
		helper.lib.redis_set_vm_data(vm, "ipaddress", 'dhcp')

	# Power on the VM
	task = helper.lib.vmware_vm_poweron(vm)
	helper.lib.vmware_task_complete(task, "Could not power on the VM")

	# If we've not powered on within 30 seconds, fail
	if not helper.lib.vmware_wait_for_poweron(vm, 30):
		helper.end_event(success=False, description="VM not powered on after 30 seconds. Check vCenter for more information")

	# End the event
	helper.end_event(description="VM powered up")	



	## Create the ServiceNow CMDB CI #######################################

	# Start the event
	helper.event("sn_create_ci", "Creating ServiceNow CMDB CI")
	sys_id = None
	cmdb_id = None

	# Failure does not kill the task
	try:
		# Create the entry in ServiceNow
		if ipv4addr is not None:
			ipaddressstring = ipv4addr
		else:
			ipaddressstring = "dhcp"
		if ipv6addr is not None:
			ipaddressstring = ipaddressstring + ", " + ipv6addr

		(sys_id, cmdb_id) = helper.lib.servicenow_create_ci(ci_name=system_name, os_type=os_type, os_name=os_name, sockets=int(options['sockets']), cores_per_socket=int(options['cores']), ram_mb=int(options['ram']) * 1024, disk_gb=int(options['disk']) + os_disk_size, environment=options['env'], short_description=options['purpose'], comments=options['comments'], location=sn_location, ipaddr=ipaddressstring)

		# Update Cortex systems table row with the sys_id
		helper.lib.set_link_ids(system_dbid, cmdb_id=sys_id, vmware_uuid=vm.config.uuid)

		# End the event
		helper.end_event(success=True, description="Created ServiceNow CMDB CI: " + str(cmdb_id))
	except Exception as e:
		helper.end_event(success=False, description="Failed to create ServiceNow CMDB CI")



	## Link ticket to CI (standard VM only) ################################

	if workflow == 'standard' and 'CREATE_CI_RELS' in options['wfconfig'] and len(options['wfconfig']['CREATE_CI_RELS']) > 0:
		helper.event("sn_create_ci_rels", "Creating default ServiceNow CMDB CI relationships")
		if sys_id is not None:
			fails = 0
			for rel in options['wfconfig']['CREATE_CI_RELS']:
				# Extract relationship details
				rel_parent = rel['parent']
				rel_child = rel['child']
				rel_type = rel['type']

				# Check for config mistakes
				if (rel_parent is None and rel_child is None) or rel_type is None:
					fails += 1
					continue

				# Change parent/child to server CI sys_id where necessary
				if rel_parent is None:
					rel_parent = sys_id
				if rel_child is None:
					rel_child = sys_id

				# Create the relationship
				try:
					helper.lib.servicenow_add_ci_relationship(rel_parent, rel_child, rel_type)
				except Exception as e:
					fails += 1

			# Log the event ending dependant on how well that went
			if fails == 0:
				helper.end_event(success=True, description="Created " + str(len(options['wfconfig']['CREATE_CI_RELS'])) + " ServiceNow CI relationships")
			elif fails == len(options['wfconfig']['CREATE_CI_RELS']):
				helper.end_event(success=False, description="Failed to create any CI relationships")
			else:
				helper.end_event(success=False, warning=True, description="Failed to create " + str(fails) + "/" + str(len(options['wfconfig']['CREATE_CI_RELS'])) + " CI relationships")
		else:
			helper.end_event(success=False, description="Cannot create CMDB CI relationships - server CI creation failed")
	


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
		wait_response = helper.lib.wait_for_guest_notify(vm, ['inprogress', 'done', 'done-with-warnings'])

		# When it returns, end the event
		if wait_response is None or wait_response not in ['inprogress', 'done']:
			helper.end_event(success=False, description='Timed out waiting for in-guest installation to start')

			# End the task here
			return
		else:
			helper.end_event(success=True, description='In-guest installation started')

	# Start another event
	helper.event('guest_installer_done', 'Waiting for in-guest installation to finish')

	# Wait for the in-guest installer to set the state to 'done' or 'done-with-warnings'
	wait_response = helper.lib.wait_for_guest_notify(vm, ['done', 'done-with-warnings'])

	# When it returns, end the event
	if wait_response is None or wait_response not in ['done', 'done-with-warnings']:
		helper.end_event(success=False, description='Timed out waiting for in-guest installation to finish')
	else:
		# Flag if there were warnings
		warning = False
		if wait_response == 'done-with-warnings':
			warning = True

		helper.end_event(success=True, warning=warning, description='In-guest installation finished')



	## For Linux VMs, on Satellite 6, associate ############################

	if os_type == helper.lib.OS_TYPE_BY_NAME['Linux']:
		helper.event('associate_satellite_6', 'Associating VM with Satellite 6 host object')
		helper.lib.satellite6_associate_host(system_dbid, options['cluster'])
		helper.end_event('VM associated with Satellite 6 host object')

	## For Windows VMs, join groups and stuff ##############################

	if workflow != 'student' and os_type == helper.lib.OS_TYPE_BY_NAME['Windows']:
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
			# If this template has groups configured
			if options['template'] in win_groups:
				# If this environment in this template has groups configured
				if options['env'] in win_groups[options['template']]:
					# Start the event
					helper.event('windows_join_groups', 'Joining default groups')

					# Run RPC to join groups
					helper.lib.windows_join_groups(system_name, options['env'], win_groups[options['template']][options['env']])

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
	if workflow in ['standard', 'sandbox']:
		subject = 'Cortex has finished building your VM, ' + str(system_name)

		message  = 'Cortex has finished building your VM. The details of the VM can be found below.\n'
		message += '\n'
		if workflow == 'standard':
			message += 'ServiceNow Task: ' + str(options['task']) + '\n'
		message += 'Hostname: ' + str(system_name) + '.' + str(dns_domain) + '\n'
		if ipv4addr is not None:
			message += 'IP Address: ' + str(ipv4addr) + '\n'
		if ipv6addr is not None:
			message += 'IPv6 Address: ' + str(ipv6addr) + '\n'
		message += 'VMware Cluster: ' + str(options['cluster']) + '\n'
		message += 'Purpose: ' + str(options['purpose']) + '\n'
		message += 'Operating System: ' + str(os_name) + '\n'
		message += 'CPUs: ' + str(total_cpu) + '\n'
		message += 'RAM: ' + str(options['ram']) + ' GiB\n'
		message += 'Data Disk: ' + str(options['disk']) + ' GiB\n'
		message += 'CMDB ID: ' + str(cmdb_id) +'\n'
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
	elif workflow == 'student':
		subject = 'Your VM has been built and is ready to use'

		if options['template'] == 'rhel7':
			message  = 'Your Red Hat Enterprise Linux 7 VM is now built and is ready to be logged in to. '
			message += 'You can access the VM via SSH, either directly from the terminal of another Linux '
			message += 'machine using the ssh command, or from a Windows machine using an SSH client such '
			message += 'as PuTTY. PuTTY is available from https://software.soton.ac.uk/. You can log in to '
			message += 'your VM with the following details:\n'
			message += '\n'
			message += 'Hostname: ' + str(system_name) + '.' + str(domain) + '\n'
			message += 'Hostname Alias: ' + dns_aliases[0] + '\n'
			message += 'Username: ' + helper.username + '\n'
			message += 'Password: ' + helper.lib.system_get_repeatable_password(system_dbid) + '\n'
			message += '\n'
			message += 'This password is also the password for the root account. Please change both '
			message += 'passwords immediately. SSHing in directly as root is disabled by default.\n'
			message += '\n'
			message += 'As an introduction to the build and to Red Hat Enterprise Linux, please look at '
			message += 'the README.UoS file in your home directory on the VM. You can view this file by '
			message += 'running:\n'
			message += '\n'
			message += 'less /home/' + helper.username + '/README.UoS\n'
		elif options['template'] == 'windows_server_2016':
			message  = 'Your Windows Server 2016 VM is now built and is ready to be logged in to. You can '
			message += 'access the VM via Remote Desktop, either using the Microsoft Remote Desktop '
			message += 'client for Windows or Mac, or using a compatible client such as rdesktop, Remmina '
			message += 'or xfreerdp for Linux. You can log in to your VM with the following details:\n'
			message += '\n'
			message += 'Hostname: ' + str(system_name) + '.' + str(domain) + '\n'
			message += 'Hostname Alias: ' + dns_aliases[0] + '\n'
			message += 'Username: ' + helper.username + '\n'
			message += 'Password: ' + helper.lib.system_get_repeatable_password(system_dbid) + '\n'
			message += '\n'
			message += 'This password is also the password for the Administrator account. Please change '
			message += 'both passwords immediately. You can do this by logging in as the user, sending '
			message += 'a Ctrl-Alt-Delete to the VM and choosing the appropriate option from the menu.\n'

		message += '\n'
		message += 'IMPORTANT REMINDER: Your VM is not backed up in any way. It is entirely up to you '
		message += 'to keep safe copies of all your work and the University will not accept any '
		message += 'liability for data loss from this VM, for whatever reason. You cannot use loss of '
		message += 'data as a reason for requesting "Special Considerations".\n'
		message += '\n'
		message += 'If you have any issues with your VM, please contact ServiceLine who will direct '
		message += 'your query to the appropriate team.\n'

	# Send the message to the user who started the task (if they want it)
	if options['sendmail']:
		helper.lib.send_email(helper.username, subject, message)

	# For standard VMs only, always notify people in the notify_emails list
	if workflow == 'standard':
		for email in notify_emails: 
			helper.lib.send_email(email, 'Cortex has finished building a VM, ' + str(system_name), message)
