#!/usr/bin/python

import cortex.lib.core
from cortex.lib.workflow import CortexWorkflow
from cortex.lib.systems import get_systems
from cortex.lib.user import does_user_have_workflow_permission, does_user_have_system_permission, does_user_have_any_system_permission
from flask import request, session, redirect, url_for, abort, flash
from datetime import datetime

workflow = CortexWorkflow(__name__, check_config={})
workflow.add_permission('systems.all.snapshot', 'Create VMware Snapshots on any system')
workflow.add_permission('systems.snapshot', 'Access the VMware Snapshot form; requires permission on individual systems to snapshot them.')
workflow.add_system_permission('snapshot', 'Create a VMware snapshot for this system')

@workflow.action('system', title='Snapshot', desc='Take a VMware snapshot of this system', system_permission='snapshot', permission='systems.all.snapshot', methods=['GET', 'POST'])
def snapshot_system(id):
	
	return redirect(url_for('snapshot_create', systems=id))

@workflow.route('create', title='Create VMware Snapshot', order=40, permission='systems.snapshot', methods=['GET', 'POST'])
def snapshot_create():
	
	# Get systems depending on permissions.
	if does_user_have_workflow_permission('systems.all.snapshot'):
		# User can snapshot all systems.
		systems = get_systems(order='id', order_asc=False, virtual_only=True)
	elif does_user_have_any_system_permission('snapshot'):
		# User can only snapshot certain systems.
		systems = get_systems(order='id', order_asc=False, virtual_only=True, show_allocated_and_perms=True, only_allocated_by=session['username'])
	else:
		abort(403)
	
	# Create the values dict.
	values = {}

	if request.method == 'GET':
		if 'systems' in request.args:
			values['snapshot_systems'] = []
			for system in request.args['systems'].strip(',').split(','):
				try:
					vm = next(i for i in systems if i['id'] == int(system))
				except StopIteration:pass # System not in Systems List (Likely not a VM then).
				except ValueError:pass    # System was not an int.
				else:
					values['snapshot_systems'].append(vm)
		
		return workflow.render_template('create.html', systems=systems, values=values)

	elif request.method == 'POST':

		values['snapshot_name'] = request.form.get('snapshot_name', '')
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
			return workflow.render_template('create.html', systems=systems, values=values)
		
		# Task Options
		options = {}
		options['wfconfig'] = workflow.config
		options['values'] = values
				
		# Everything should be good - start a task.
		neocortex = cortex.lib.core.neocortex_connect()
		task_id = neocortex.create_task(__name__, session['username'], options, description='Create a VMware Snapshot')
		
		# Redirect to the status page for the task
		return redirect(url_for('task_status', id=task_id))
