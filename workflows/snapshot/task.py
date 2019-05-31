from pyVmomi import vim

def run(helper, options):

	systems = options['fields']['systems']
	for name in systems:
		
		helper.event('vm_locate', 'Finding {}'.format(name))
		system = helper.lib.get_system_by_name(name, must_have_vmware_uuid=True)

		if system is not None:
			
			# Connect to vCenter
			vcenter_tag = system['vmware_vcenter'].split('.')[0]
			si = helper.lib.vmware_smartconnect(vcenter_tag)

			content = si.RetrieveContent()

			vm = helper.lib.vmware_get_obj(content, [vim.VirtualMachine], name)

			if not vm:
				helper.end_event(success=False, warning=True, description='Failed to find {}'.format(name))
				continue
			else:
				helper.end_event(description='Found {} - {}'.format(system['name'], system['allocation_comment']))

				memory = False
				if options['fields']['cold']:
					# Power Off
					helper.event('vm_poweroff', 'Powering off {} for a cold snapshot'.format(name))

					# Attempt to shutdown the guest.
					task = vm.ShutdownGuest()
					if not helper.lib.vmware_wait_for_poweroff(vm):
						# Shutdown task failed.
						if vm.runtime.powerState == vim.VirtualMachinePowerState.poweredOn:
							task = vm.PowerOffVM_Task()
							if not helper.lib.vmware_task_wait(task, timeout=30):
								raise RuntimeError('Failed to power off VM')

					helper.end_event()
				elif options['fields']['memory']:
					# Snapshot the VM's memory:
					memory = True


				helper.event('vm_snapshot', 'Attempting to snapshot VM')
				description_text = 'Delete After: {0}\nTaken By: {1}\nTask: {2}\nAdditional Comments: {3}\n'.format(options['fields']['expiry'], options['fields']['username'], options['fields']['task'], options['fields']['comments'])

				task = helper.lib.vmware_vm_create_snapshot(
					vm,
					options['fields']['name'],
					description_text,
					memory=memory,
					quiesce=False
				)

				if not helper.lib.vmware_task_wait(task):
					raise helper.lib.TaskFatalError(message='Failed to snapshot VM. ({})'.format(name))
				
				helper.end_event(description='Snapshot Complete')

				if options['fields']['cold']:
					# Power On
					helper.event('vm_poweron', 'Powering on {}'.format(name))
					vm.PowerOn()

					if helper.lib.vmware_wait_for_poweron(vm):
						helper.end_event()
					else:
						helper.end_event(success=False, warning=True, description='Failed to power on {}'.format(name))
					
		else:
			helper.end_event(success=False, warning=True, description='Failed to find {}'.format(name))
			continue

