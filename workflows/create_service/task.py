import time
import Pyro4

# Maybe should add a third parameter that contains the options?
def run(helper, options):
	
	# Get NeoCortex connection
	#neocortex = cortex.lib.core.neocortex_connect()

	neocortex = Pyro4.Proxy('PYRO:neocortex@localhost:1888')
	neocortex._pyroHmacKey = helper.config['NEOCORTEX_KEY']
	neocortex._pyroTimeout = 5
	
	# Create a new event for creating all the VMs
	#helper.event("create_vms", "Creating X VMs")
	for vm_recipe in options['vm_recipes']:
		helper.event("create_vm", "Creating "+ vm_recipe)
		username = "acv1y18"  # THIS IS HARDCODED AND NEEDS TO BE CHANGED
		vm_task_id = neocortex.create_task("buildvm", username, options['vm_recipes'][vm_recipe], description="Creates and sets up a virtual machine (sandbox VMware environment)")
		helper.end_event("Probably created the VM")

	#helper.end_event(description="Successfully set up all the VMs") # this is not the case yet, but I will add code on top of this later
	#Basically
	"""
	subject = 'Cortex has finished setting up your service, ' + str(service_name)

	message  = 'Cortex has finished setting up your service. The details of the service can be found below.\n'
	message += '\n'
	message += 'ServiceNow Task: ' + str(options['task']) + '\n'
	message += 'Purpose: ' + str(options['purpose']) + '\n'
	message += 'CMDB ID: ' + str(cmdb_id) +'\n'
	message += '\n'
	message += 'The event log for the task can be found at https://' + str(helper.config['CORTEX_DOMAIN']) + '/task/status/' + str(helper.task_id) + '\n'
	message += 'More information about the service, can be found on the Cortex systems page at https://' + str(helper.config['CORTEX_DOMAIN']) + '/systems/edit/' + str(system_dbid) + '\n'
	if sys_id is not None:
		message += 'The ServiceNow CI entry is available at ' + (helper.config['CMDB_URL_FORMAT'] % sys_id) + '\n'
	else:
	message += 'A ServiceNow CI was not created. For more information, see the task event log.\n'

	message += '\nPlease remember to move the virtual machine into an appropriate folder in vCenter'
	if os_type == helper.lib.OS_TYPE_BY_NAME['Windows']:
	message += ' and to an appropriate OU in Active Directory'
	message += '\n'
	
	if options['sendmail']:
		helper.lib.send_email(helper.username, subject, message)
	"""
