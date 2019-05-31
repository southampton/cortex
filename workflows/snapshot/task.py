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
				helper.event('vm_snapshot', 'Attempting to snapshot VM')

				description_text = 'Delete After: {0}\nTaken By: {1}\nTask: {2}\nAdditional Comments: {3}\n'.format(options['fields']['expiry'], options['fields']['username'], options['fields']['task'], options['fields']['comments'])
				task = helper.lib.vmware_vm_create_snapshot(
					vm,
					options['fields']['name'],
					description_text,
					memory=False,
					quiesce=False
				)

				if not helper.lib.vmware_task_wait(task):
					raise helper.lib.TaskFatalError(message='Failed to snapshot VM. ({})'.format(name))
				
				helper.end_event(description='Snapshot Complete')
	
		else:
			helper.end_event(success=False, warning=True, description='Failed to find {}'.format(name))
			continue

