from pyVmomi import vim
from pyVim.task import WaitForTask

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

				desc_text = 'Delete After: {0}\nTaken By: {1}\nTask: {2}\nAdditional Comments: {3}\n'.format(options['fields']['expiry'], options['fields']['username'], options['fields']['task'], options['fields']['comments'])
				WaitForTask(vm.CreateSnapshot(
					options['fields']['name'], # Snapshot Name
					desc_text,		   # Snapshot Description
					False,			   # Quiesce
					False,			   # Dump Memory
				))

				helper.end_event(description='Snapshot Complete')
	
		else:
			helper.end_event(success=False, warning=True, description='Failed to find {}'.format(name))
			continue

