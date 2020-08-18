from flask import abort, flash, redirect, request, session, url_for

import cortex.lib.core
from cortex.lib.systems import get_systems
from cortex.lib.user import (does_user_have_any_system_permission,
                             does_user_have_system_permission,
                             does_user_have_workflow_permission)
from cortex.lib.workflow import CortexWorkflow

workflow = CortexWorkflow(__name__, check_config={})
workflow.add_permission('systems.all.snapshot', 'Create VMware Snapshots on any system')
workflow.add_system_permission('snapshot', 'Create a VMware snapshot for this system')

def snapshot_create_permission_callback():
	return does_user_have_workflow_permission('systems.all.snapshot') or does_user_have_any_system_permission('snapshot')

@workflow.action('system', title='Snapshot', desc='Take a VMware snapshot of this system', system_permission='snapshot', permission='systems.all.snapshot', require_vm=True, methods=['GET', 'POST'])
def snapshot_system(target_id):

	return redirect(url_for('snapshot_create', systems=target_id))

@workflow.route('create', title='Create VMware Snapshot', order=40, permission=snapshot_create_permission_callback, methods=['GET', 'POST'])
def snapshot_create():

	# Get systems depending on permissions.
	if does_user_have_workflow_permission('systems.all.snapshot'):
		# User can snapshot all systems.
		systems = get_systems(order='id', order_asc=False, virtual_only=True)
	elif does_user_have_any_system_permission('snapshot'):
		# Select all VMs where the user has permission to snapshot
		query_where = (
			"""WHERE (`cmdb_id` IS NOT NULL AND `cmdb_operational_status` = "In Service") AND `vmware_uuid` IS NOT NULL AND (`id` IN (SELECT `system_id` FROM `p_system_perms_view` WHERE (`type` = '0' AND `perm` = 'snapshot' AND `who` = %s) OR (`type` = '1' AND `perm` = 'snapshot' AND `who` IN (SELECT `group` FROM `ldap_group_cache` WHERE `username` = %s)))) ORDER BY `id` DESC""",
			(session["username"], session["username"]),
		)
		systems = get_systems(where_clause=query_where)
	else:
		abort(403)

	# Create the values dict.
	values = {}

	if request.method == 'POST':

		values['snapshot_name'] = request.form.get('snapshot_name', 'Snapshot - {}'.format(session['username']))[:80]
		values['snapshot_task'] = request.form.get('snapshot_task', '')
		values['snapshot_expiry'] = request.form.get('snapshot_expiry', None)
		values['snapshot_comments'] = request.form.get('snapshot_comments', '')
		values['snapshot_username'] = session['username']
		values['snapshot_memory'] = 'snapshot_memory' in request.form
		values['snapshot_cold'] = 'snapshot_cold' in request.form

		values['systems'] = list(set(request.form.getlist('systems[]')))
		values['snapshot_systems'] = []

		# Before starting the task check the permissions.
		error = False
		if not does_user_have_workflow_permission('systems.all.snapshot'):
			for system in values['systems']:
				try:
					vm = next(i for i in systems if i['name'] == system)
				except StopIteration:
					flash('You do not have permission to snapshot one or more select VMs. Please try again.', 'alert-danger')
					error = True
				else:
					values['snapshot_systems'].append(vm)
					if not does_user_have_system_permission(vm['id'], 'snapshot'):
						flash('You do not have permission to snapshot {}, please remove this from the list of systems and try again.'.format(vm['name']), 'alert-danger')
						error = True

		if error:
			return workflow.render_template('create.html', title='Create VMware Snapshot', systems=systems, values=values)

		# Task Options
		options = {}
		options['wfconfig'] = workflow.config
		options['values'] = values

		# Everything should be good - start a task.
		neocortex = cortex.lib.core.neocortex_connect()
		task_id = neocortex.create_task(__name__, session['username'], options, description='Create a VMware Snapshot')

		# Redirect to the status page for the task
		return redirect(url_for('task_status', task_id=task_id))

	if 'systems' in request.args:
		values['snapshot_systems'] = []
		for system in request.args['systems'].strip(',').split(','):
			try:
				vm = next(i for i in systems if i['id'] == int(system))
			except StopIteration:
				pass # System not in Systems List (Likely not a VM then).
			except ValueError:
				pass    # System was not an int.
			else:
				values['snapshot_systems'].append(vm)

	return workflow.render_template('create.html', title='Create VMware Snapshot', systems=systems, values=values)
