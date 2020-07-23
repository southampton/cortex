
# pylint: disable=no-name-in-module
from pyVmomi import vim
# pylint: enable=no-name-in-module

def run(helper, options):

	# check if workflows are locked
	if not helper.lib.check_workflow_lock():
		raise Exception("Workflows are currently locked")

	for name in options['values']['systems']:

		helper.event('vm_locate', 'Finding {}'.format(name))
		system = helper.lib.get_system_by_name(name, must_have_vmware_uuid=True)

		if system is not None:
			vm_link = '{{system_link id="' + str(system['id']) + '"}}' + system['name'] + '{{/system_link}}'

			# Connect to vCenter
			vcenter_tag = system['vmware_vcenter'].split('.')[0]
			si = helper.lib.vmware_smartconnect(vcenter_tag)

			content = si.RetrieveContent()

			vm = helper.lib.vmware_get_obj(content, [vim.VirtualMachine], name)

			if not vm:
				helper.end_event(success=False, warning=True, description='Failed to find {}'.format(vm_link))
				continue

			helper.end_event(description='Found {} - {}'.format(vm_link, system['allocation_comment']))

			memory = False
			if options['values']['snapshot_cold']:
				power_on_vm = True

				# Only power off if the VM is on, otherwise VMware raises an error
				if vm.runtime.powerState == vim.VirtualMachinePowerState.poweredOn:
					# Power Off
					helper.event('vm_poweroff', 'Powering off {} for a cold snapshot'.format(vm_link))

					# Attempt to shutdown the guest.
					task = vm.ShutdownGuest()

					# Give the Guest OS three minutes to shutdown
					if not helper.lib.vmware_wait_for_poweroff(vm, timeout=180):
						# Shutdown task failed.
						if vm.runtime.powerState == vim.VirtualMachinePowerState.poweredOn:
							task = vm.PowerOffVM_Task()
							if not helper.lib.vmware_task_wait(task, timeout=30):
								raise RuntimeError('Failed to power off {}'.format(vm_link))

					helper.end_event()
				else:
					helper.event('vm_alreadyoff', 'VM {} is already off'.format(vm_link), oneshot=True, success=True)
					power_on_vm = False

			elif options['values']['snapshot_memory']:
				# Snapshot the VM's memory:
				memory = True

			helper.event('vm_snapshot', 'Attempting to snapshot {}'.format(vm_link))
			description_text = 'Delete After: {0}\nTaken By: {1}\nTask: {2}\nAdditional Comments: {3}\n'.format(options['values']['snapshot_expiry'], options['values']['snapshot_username'], options['values']['snapshot_task'], options['values']['snapshot_comments'])

			task = helper.lib.vmware_vm_create_snapshot(
				vm,
				options['values']['snapshot_name'],
				description_text,
				memory=memory,
				quiesce=False
			)

			if not helper.lib.vmware_task_wait(task):
				raise helper.lib.TaskFatalError(message='Failed to snapshot ({})'.format(vm_link))

			helper.end_event(description='Snapshot Complete')

			if options['values']['snapshot_cold']:
				if power_on_vm:
					# Power On
					helper.event('vm_poweron', 'Powering on {}'.format(vm_link))
					vm.PowerOn()

					if helper.lib.vmware_wait_for_poweron(vm):
						helper.end_event()
					else:
						helper.end_event(success=False, warning=True, description='Failed to power on {}'.format(vm_link))
				else:
					helper.event('vm_notpoweringon', 'Not powering on {} - was already off before snapshot'.format(vm_link), oneshot=True, success=True)

		else:
			helper.end_event(success=False, warning=True, description='Failed to find {}'.format(name))
			continue
