#!/usr/bin/python

import cortex.lib.core
from cortex.lib.workflow import CortexWorkflow
from cortex.lib.systems import get_systems
from cortex.lib.user import does_user_have_workflow_permission, does_user_have_system_permission
from flask import request, session, redirect, url_for, abort, jsonify
from datetime import datetime

workflow = CortexWorkflow(__name__, check_config={})
workflow.add_permission('systems.all.snapshot', 'Create VMware Snapshots on any system')
workflow.add_system_permission('snapshot', 'Create a VMware snapshot for this system')

def create_values_dict(systems, system_id=None):
	values = {}

	values['snapshot_systems'] = []
	if system_id is not None:
		vm = next(i for i in systems if i['id'] == int(system_id))
		values['snapshot_systems'].append(vm)
	if 'systems' in request.args:
		values['snapshot_systems'] = []
		for system in request.args['systems'].strip(',').split(','):
			try:
				vm = next(i for i in systems if i['id'] == int(system))
			except StopIteration:pass # System not in Systems List (Likely not a VM then).
			except ValueError:pass    # System was not an int.
			else:
				values['snapshot_systems'].append(vm)
	
	if len(values['snapshot_systems']) <= 0:
		del values['snapshot_systems']

	return values

def start_snapshot_task(systems):
	"""Start the task to snapshot the systems"""

	fields = {}
	fields['name'] = request.form.get('snapshot_name', '')
	fields['task'] = request.form.get('snapshot_task', '')
	fields['expiry'] = request.form.get('snapshot_expiry', None)
	fields['comments'] = request.form.get('snapshot_comments', '')
	fields['username'] = session['username']
	fields['memory'] = 'snapshot_memory' in request.form
	fields['cold'] = 'snapshot_cold' in request.form

	fields['systems'] = list(set(request.form.getlist('systems[]')))

	# Before starting the task check the permissions.
	if not does_user_have_workflow_permission('systems.all.snapshot'):
		for system in fields['systems']:
			try:
				vm = next(i for i in systems if i['name'] == system)
			except StopIteration:
				abort(403)
			else:
				if not does_user_have_system_permission(vm['id'], 'snapshot'):
					abort(403)
	
	# Task Options
	options = {}
	options['wfconfig'] = workflow.config
	options['fields'] = fields
			
	# Everything should be good - start a task.
	neocortex = cortex.lib.core.neocortex_connect()
	task_id = neocortex.create_task(__name__, session['username'], options, description='Create a VMware Snapshot')
	
	return task_id

@workflow.action('system', title='Snapshot', desc='Take a VMware snapshot of this system', system_permission='snapshot', permission='systems.all.snapshot', methods=['GET', 'POST'])
def snapshot_system(id):
	
	if does_user_have_workflow_permission('systems.all.snapshot'):
		return redirect(url_for('snapshot_create', systems=id))
	else:
		# User can only snapshot certain systems.
		systems = get_systems(order='id', order_asc=False, virtual_only=True, show_allocated_and_perms=True, only_allocated_by = session['username'])

		if request.method == 'GET':
			# Create the values dict.
			values = create_values_dict(systems, system_id=id)

			return workflow.render_template('create.html', systems=systems, values=values)

		elif request.method == 'POST':
			
			task_id = start_snapshot_task(systems)

			# Redirect to the status page for the task
			return redirect(url_for('task_status', id=task_id))


@workflow.route('create', title='Create VMware Snapshot', order=40, permission="systems.all.snapshot", methods=['GET', 'POST'])
def snapshot_create():
	
	# Get systems.
	systems = get_systems(order='id', order_asc=False, virtual_only=True)
        
	if request.method == 'GET':
		# Create the values dict.
		values = create_values_dict(systems)

		return workflow.render_template('create.html', systems=systems, values=values)

	elif request.method == 'POST':

		task_id = start_snapshot_task(systems)

		# Redirect to the status page for the task
		return redirect(url_for('task_status', id=task_id))

