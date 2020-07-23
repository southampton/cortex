
# pylint: disable=no-name-in-module
from pyVmomi import vim
# pylint: enable=no-name-in-module

def run(helper, options):

	# check if workflows are locked
	if not helper.lib.check_workflow_lock():
		raise Exception("Workflows are currently locked")

	# Locate the VM in vCenter
	helper.event("vm_locate", "Finding system by ID: {}".format(options["values"]["adddisk_system_id"]))
	system = helper.lib.get_system_by_id(options["values"]["adddisk_system_id"])
	system_link = '{{system_link id="' + str(system["id"]) + '"}}' + system["name"] + '{{/system_link}}'

	if not system["vmware_uuid"]:
		helper.end_event(success=False, warning=False, description="System {} is not virtual, a disk cannot be added to a system not in VMware".format(system_link))
		raise Exception("A disk cannot be added to a system not linked to VMware")

	vcenter_tag = system["vmware_vcenter"].split(".")[0]
	si = helper.lib.vmware_smartconnect(vcenter_tag)
	content = si.RetrieveContent()
	vm = helper.lib.vmware_get_obj(content, [vim.VirtualMachine], system["name"])

	if not vm:
		helper.end_event(success=False, warning=False, description="Failed to locate {} in VMware (vCenter {})".format(system_link, vcenter_tag))
		raise Exception("Failed to locate {} in VMware (vCenter {})".format(system_link, vcenter_tag))

	helper.end_event(description="Found {} - {}".format(system_link, system["allocation_comment"]))

	# Add disk to the VM
	helper.event("vm_add_disk", "Adding data disk to the VM")
	task = helper.lib.vmware_vm_add_disk(vm, int(options["values"]["adddisk_size"]) * 1024 * 1024 * 1024)
	helper.lib.vmware_task_complete(task, "Could not add data disk to VM")
	helper.end_event(description="Data disk added to VM: {} GiB".format(options["values"]["adddisk_size"]))
