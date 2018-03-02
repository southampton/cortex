#!/usr/bin/python

from cortex import app
from cortex.lib.workflow import CortexWorkflow
import cortex.lib.core
import cortex.lib.systems
import cortex.views
from flask import Flask, request, session, redirect, url_for, flash, g, abort, render_template, jsonify

# For DNS queries
import socket

# For NLB API
import requests

workflow = CortexWorkflow(__name__)
workflow.add_permission('nlbweb.create', 'Creates NLB Web Service')

@workflow.route('create', title='Create NLB Web Service', order=40, permission="nlbweb.create")
def nlbweb_create():
	# Get the workflow settings
	wfconfig = workflow.config

	## Show form
	return render_template(__name__ + "::nlbweb.html", title="Create NLB Web Service", envs=wfconfig['ENVS'], partition=wfconfig['DEFAULT_PARTITION'], ssl_providers=wfconfig['SSL_PROVIDERS'], default_ssl_provider=wfconfig['DEFAULT_SSL_PROVIDER'])

@workflow.route('validate', title='Create NLB Web Service', permission="nlbweb.create", methods=['POST'], menu=False)
def nlbweb_validate():
	# Get the workflow settings
	wfconfig = workflow.config
	
	# If we've got the confirmation, start the task:
	if 'confirm' in request.form and int(request.form['confirm']) == 1:
		options = {}
		options['wfconfig'] = wfconfig

		# Connect to NeoCortex and start the task
		neocortex = cortex.lib.core.neocortex_connect()
		task_id = neocortex.create_task(__name__, session['username'], options, description="Creates the necessary objects on the NLB to run a basic HTTP(S) website / service")

		# Redirect to the status page for the task
		return redirect(url_for('task_status', id=task_id))

	# We've not got confirmation, figure out what we're about to do:
	else:
		# TODO

		return render_template(__name__ + "::validate.html", title="Create NLB Web Service")

@workflow.route('dnslookup', permission="nlbweb.create", menu=False)
def nlbweb_dns_lookup():
	host = request.args['host']
	add_default_domain = False
	if host.find('.') == -1:
		add_default_domain = True
	else:
		host_parts = host.split('.')
		if len(host_parts) == 2:
			if host_parts[1] in workflow.config['KNOWN_DOMAIN_SUFFIXES']:
				add_default_domain = True

	if add_default_domain:
		host = host + '.' + workflow.config['DEFAULT_DOMAIN']

	result = {'success': 0}
	try:
		result['ip'] = socket.gethostbyname(host)
		result['success'] = 1
	except Exception, e:
		pass

	return jsonify(result)
