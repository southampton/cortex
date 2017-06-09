import requests

def run(helper, options):

	# Iterate over the actions that we have to perform
	for action in options['actions']:
		# Start the event
		helper.event(action['id'], action['desc'])

		if action['id'] == "vm.poweroff":
			r = action_vm_poweroff(action, helper)
		elif action['id'] == "vm.delete":
			r = action_vm_delete(action, helper)
		elif action['id'] == "cmdb.update":
			r = action_cmdb_update(action, helper)
		elif action['id'] == "dns.delete":
			r = action_dns_delete(action, helper)
		elif action['id'] == "puppet.cortex.delete":
			r = action_puppet_cortex_delete(action, helper)
		elif action['id'] == "puppet.master.delete":
			r = action_puppet_master_delete(action, helper)
		elif action['id'] == "ad.delete":
			r = action_ad_delete(action, helper)
		elif action['id'] == "ticket.ops":
			r = action_ticket_ops(action, helper, options['wfconfig'])
		elif action['id'] == "tsm.decom":
			r = action_tsm_decom(action, helper)

		# End the event (don't change the description) if the action
		# succeeded. The action_* functions either raise Exceptions or
		# end the events with a failure message on errors.
		if r:
			helper.end_event()

################################################################################

def action_vm_poweroff(action, helper):
	# Get the managed VMware VM object
	vm = helper.lib.vmware_get_vm_by_uuid(action['data']['uuid'], action['data']['vcenter'])

	# Not finding the VM is fatal:
	if not vm:
		raise helper.lib.TaskFatalError(message="Failed to power off VM. Could not locate VM in vCenter")

	# Power off the VM
	task = helper.lib.vmware_vm_poweroff(vm)

	# Wait for the task to complete
	helper.lib.vmware_task_wait(task)

	return True

################################################################################

def action_vm_delete(action, helper):
	# Get the managed VMware VM object
	vm = helper.lib.vmware_get_vm_by_uuid(action['data']['uuid'], action['data']['vcenter'])

	# Not finding the VM is fatal:
	if not vm:
		raise helper.lib.TaskFatalError(message="Failed to delete VM. Could not locate VM in vCenter")

	# Delete the VM
	task = helper.lib.vmware_vm_delete(vm)

	# Wait for the task to complete
	if not helper.lib.vmware_task_wait(task):
		raise helper.lib.TaskFatalError(message="Failed to delete the VM. Check vCenter for more information")

	return True

################################################################################

def action_cmdb_update(action, helper):
	try:
		# This will raise an Exception if it fails, but it is not fatal
		# to the decommissioning process
		helper.lib.servicenow_mark_ci_deleted(action['data'])
		return True
	except Exception as e:
		helper.end_event(success=False, description=str(e))
		return False

################################################################################

def action_dns_delete(action, helper):
	try:
		helper.lib.infoblox_delete_host_record_by_ref(action['data'])
		return True
	except Exception as e:
		helper.end_event(success=False, description=str(e))
		return False

################################################################################

def action_puppet_cortex_delete(action, helper):
	try:
		helper.lib.puppet_enc_remove(action['data'])
		return True
	except Exception as e:
		helper.end_event(success=False, description="Failed to remove Puppet node from ENC: " + str(e))
		return False

################################################################################

def action_puppet_master_delete(action, helper):
	# Build the URL
	base_url = helper.config['PUPPET_AUTOSIGN_URL']
	if not base_url.endswith('/'):
		base_url += '/'
	clean_url = base_url + 'cleannode/' + str(action['data'])
	deactivate_url = base_url + 'deactivatenode/' + str(action['data'])

	# Send the request to Cortex Puppet Bridge to clean the node
	try:
		r = requests.get(clean_url, headers={'X-Auth-Token': helper.config['PUPPET_AUTOSIGN_KEY']}, verify=helper.config['PUPPET_AUTOSIGN_VERIFY'])
	except Exception as ex:
		helper.end_event(success=False, description="Failed to remove node from Puppet Master: " + str(ex))
		return False

	# Check return code
	if r.status_code != 200:
		helper.end_event(success=False, description="Failed to remove node from Puppet Master. Cortex Puppet Bridge returned error code " + str(r.status_code))
		return False

	# Send the request to Cortex Puppet Bridge to deactivate the node
	try:
		r = requests.get(deactivate_url, headers={'X-Auth-Token': helper.config['PUPPET_AUTOSIGN_KEY']}, verify=helper.config['PUPPET_AUTOSIGN_VERIFY'])
	except Exception as ex:
		helper.end_event(success=False, description="Failed to deactivate node on Puppet Master: " + str(ex))
		return False

	# Check return code
	if r.status_code != 200:
		helper.end_event(success=False, description="Failed to deactivate node on Puppet Master. Cortex Puppet Bridge returned error code " + str(r.status_code))
		return False

	return True

################################################################################

def action_ad_delete(action, helper):
	try:
		helper.lib.windows_delete_computer_object(action['data']['env'], action['data']['hostname'])
		return True
	except Exception as e:
		helper.end_event(success=False, description="Failed to remove AD object: " + str(e))
		return False

################################################################################

def action_ticket_ops(action, helper, wfconfig):
	try:
		short_desc = "Finish manual decommissioning steps of " + action['data']['hostname']
		message  = 'Cortex has decommissioned the system ' + action['data']['hostname'] + '.\n\n'
		message += 'Please perform the final, manual steps of the decommissioning process:\n'
		message += ' - Remove the system from monitoring\n'
		message += ' - Remove any associated perimeter firewall rules\n'
		message += ' - Remove the system from backups\n'

		helper.lib.servicenow_create_ticket(short_desc, message, wfconfig['TICKET_OPENER_SYS_ID'], wfconfig['TICKET_TEAM'])
		return True
	except Exception as e:
		helper.end_event(success=False, description="Failed to raise ticket: " + str(e))
		return False

def action_tsm_decom(action, helper):
    try:
        helper.lib.tsm_decom_system(action['data']['NAME'], action['data']['SERVER'])
        return True
    except Exception as e:
        helper.end_event(success=False, description="Failed to decomission system in TSM")
        return False
