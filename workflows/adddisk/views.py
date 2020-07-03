from flask import abort, flash, redirect, request, session, url_for

import cortex.lib.core
from cortex.lib.systems import get_system_by_id, get_systems
from cortex.lib.user import (does_user_have_any_system_permission,
                             does_user_have_system_permission,
                             does_user_have_workflow_permission)
from cortex.lib.workflow import CortexWorkflow

workflow = CortexWorkflow(__name__, check_config={})
workflow.add_permission("systems.all.adddisk", "Add a virtual disk in VMware on any system")
workflow.add_system_permission("adddisk", "Add a virtual disk in VMware to this system")

# Define some disk limits (GiB)
MIN_DISK_SIZE = 10
MAX_DISK_SIZE = 2000

def adddisk_create_permission_callback():
	return does_user_have_workflow_permission("systems.all.adddisk") or does_user_have_any_system_permission("adddisk")

@workflow.action("system", title="Add VMware Disk", desc="Add a virtual disk in VMware to this system", system_permission="adddisk", permission="systems.all.adddisk", require_vm=True, methods=["GET", "POST"])
def adddisk_system(id):

	return redirect(url_for("adddisk_add", system=id))


@workflow.route("add", title="Add VMware Disk", order=50, permission=adddisk_create_permission_callback, methods=["GET", "POST"])
def adddisk_add():

	selected_system = None
	systems = None
	if request.method == "GET" and "system" in request.args and request.args["system"].strip():
		try:
			selected_system = get_system_by_id(int(request.args["system"].strip()))
		except ValueError: pass # System was not an int.
		else:
			# Ensure the system is actually a VM
			selected_system = selected_system if selected_system["vmware_uuid"] else None

		# Check permissions on this system
		if not does_user_have_system_permission(selected_system["id"], "adddisk") and not does_user_have_workflow_permission("systems.all.adddisk"):
			abort(403)

	# If a system was not selected, get all systems
	if not selected_system:
		# Get systems depending on permissions.
		if does_user_have_workflow_permission("systems.all.adddisk"):
			# User can add disks to all systems.
			systems = get_systems(order='id', order_asc=False, virtual_only=True)
		elif does_user_have_any_system_permission("adddisk"):
			# Select all VMs where the user has permission to add disks
			query_where = (
				"""WHERE (`cmdb_id` IS NOT NULL AND `cmdb_operational_status` = "In Service") AND `vmware_uuid` IS NOT NULL AND (`id` IN (SELECT `system_id` FROM `system_perms_view` WHERE (`type` = '0' AND `perm` = 'adddisk' AND `who` = %s) OR (`type` = '1' AND `perm` = 'adddisk' AND `who` IN (SELECT `group` FROM `ldap_group_cache` WHERE `username` = %s)))) ORDER BY `id` DESC""",
				(session["username"],session["username"]),
			)
			systems = get_systems(where_clause = query_where)
		else:
			abort(403)

	if request.method == "POST":
		# Get the values
		values = { k: request.form.get(k) if k in request.form else abort(400) for k in ["adddisk_task", "adddisk_size", "adddisk_system_id"] }
		values["adddisk_task"] = values["adddisk_task"] if values["adddisk_task"] else "unknown"

		try:
			values["adddisk_size"] = int(values["adddisk_size"])
		except ValueError: abort(400)

		if not (MIN_DISK_SIZE <= values["adddisk_size"] <= MAX_DISK_SIZE):
			flash("Invalid disk size! Please choose a size between {} and {} GiB".format(MIN_DISK_SIZE, MAX_DISK_SIZE))
		else:

			# Check permissions before starting task
			if not does_user_have_system_permission(values["adddisk_system_id"], "adddisk") and not does_user_have_workflow_permission("systems.all.adddisk"):
				abort(403)

			# Task Options
			options = {}
			options["wfconfig"] = workflow.config
			options["values"] = values

			# Everything should be good - start a task.
			neocortex = cortex.lib.core.neocortex_connect()
			task_id = neocortex.create_task(__name__, session["username"], options, description="Add VMware disk")

			# Log the Task ID
			cortex.lib.core.log(__name__, "workflow.adddisk.add", "Add disk task {} started by {} with ServiceNow task {}".format(task_id, session["username"], values["adddisk_task"]))

			# Redirect to the status page for the task
			return redirect(url_for("task_status", id=task_id))

	return workflow.render_template("add.html", title="Add VMware Disk", selected_system = selected_system, systems = systems)
