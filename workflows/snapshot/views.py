#!/usr/bin/python

import cortex.lib.core
from cortex.lib.workflow import CortexWorkflow
from cortex.lib.systems import get_systems
from flask import request, session, redirect, url_for
from datetime import datetime

workflow = CortexWorkflow(__name__, check_config={})

@workflow.route('create', title='Create VMware Snapshot', order=40, permission="snapshot.create", methods=['GET', 'POST'])
def snapshot_create():
        
	if request.method == 'GET':
	
		# Get systems.
		systems = get_systems(virtual_only=True)

		return workflow.render_template('create.html', systems=systems)

	elif request.method == 'POST':

		fields = {}
		fields['name'] = request.form.get('snapshot_name', '')
		fields['task'] = request.form.get('snapshot_task', '')
		fields['expiry'] = request.form.get('snapshot_expiry', None)
		fields['comments'] = request.form.get('snapshot_comments', '')
		fields['username'] = session['username']

		fields['systems'] = list(set(request.form.getlist('systems[]')))
		
		# Task Options
		options = {}
		options['wfconfig'] = workflow.config
		options['fields'] = fields
				
		# Everything should be good - start a task.
		neocortex = cortex.lib.core.neocortex_connect()
		task_id = neocortex.create_task(__name__, session['username'], options, description='Create a VMware Snapshot')
		
		# Redirect to the status page for the task
		return redirect(url_for('task_status', id=task_id))
