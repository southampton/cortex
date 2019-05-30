#!/usr/bin/python

from cortex.lib.workflow import CortexWorkflow
from flask import render_template

workflow = CortexWorkflow(__name__, check_config={})

@workflow.route('create', title='Create VMware Snapshot', order=40, permission="snapshot.create", methods=['GET', 'POST'])
def snapshot_create():
        
	# Get the workflow settings
	wfconfig = workflow.config

	return workflow.render_template('create.html')

