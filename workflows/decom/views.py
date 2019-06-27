#!/usr/bin/python

from cortex import app
from cortex.lib.workflow import CortexWorkflow
from cortex.lib.errors import stderr
import cortex.lib.core
import cortex.lib.systems
from cortex.corpus import Corpus
from flask import Flask, request, session, redirect, url_for, flash, g, abort, render_template, jsonify
from pyVmomi import vim
import itsdangerous
from itsdangerous import JSONWebSignatureSerializer
import requests
import requests.exceptions
from urllib.parse import urljoin
import ldap

workflow = CortexWorkflow(__name__)
workflow.add_permission('systems.all.decom', 'Decommission any system')
workflow.add_system_permission('decom', 'Decommission system')

## Helper Functions
################################################################################

def get_system_actions_from_redis(task):
	# Defaults
	signed_actions = None

	# Redis Key Prefix
	prefix = 'decom/' +  str(task['id']) + '/'

	if g.redis.exists(prefix + 'actions') and g.redis.exists(prefix + 'system'):
		signed_actions = str(g.redis.get(prefix + 'actions'),'utf-8')
		system_id = str(g.redis.get(prefix + 'system'), 'utf-8')
	else:
		raise RuntimeError("Required keys don't exist in Redis. You must complete a decommission within an hour of starting it.")

	if signed_actions is not None:
		# Decode the Signed Actions / System Data. 
		signer = JSONWebSignatureSerializer(app.config['SECRET_KEY'])
		try:
			actions = signer.loads(signed_actions)
		except itsdangerous.BadSignature:
			abort(400)

	try:
		system_id = int(system_id)
	except ValueError:
		raise RuntimeError("System ID is not an integer")

	return system_id, actions, signed_actions

################################################################################

@workflow.action("prepare",title='Decommission', desc="Begins the process of decommissioning this system", system_permission="decom", permission="systems.all.decom")
def decom_step_prepare(id):

	system = cortex.lib.systems.get_system_by_id(id)
	if system is None:
		abort(404)

	return workflow.render_template("prepare.html", system=system, title="Decommission system")

@workflow.action("check_start",title='Decomission', system_permission="decom", permission="systems.all.decom",menu=False)
def decom_step_check_start(id):
	# in this step we work out what steps to perform
	# then we load this into a list of steps, each step being a dictionary
	# this is used on the page to list the steps to the user
	# the list is also used to generate a JSON document which we sign using
	# app.config['SECRET_KEY'] and then send that onto the page as well.

	# Build the options
	options = {}
	options['wfconfig'] = workflow.config 
	options['actions'] = [{'id':'system.check', 'desc':'Checking system for decommissioning', 'data':{'system_id':id}}]

	# Everything is fine. Start the task
	neocortex = cortex.lib.core.neocortex_connect()
	task_id = neocortex.create_task(__name__, session['username'], options, description="Check a system for decommissioning")

	return redirect(url_for('decom_step_check_wait', id=task_id))

@workflow.action("check_wait", title='Decomission', system_permission="decom", permission="systems.all.decom", methods=['GET'], menu=False)
def decom_step_check_wait(id):

	# Check that the task exists
	task = cortex.lib.core.task_get(id)
	if task is None:
		abort(404)
	if task['module'] != 'decom':
		abort(400)

	return workflow.render_template('check_wait.html', title='Checking System...', task_id=int(task['id']))

@workflow.action("check_complete", title='Decomission', system_permission="decom", permission="systems.all.decom", methods=['GET'], menu=False)
def decom_step_check_complete(id):

	# Check that the task exists
	task = cortex.lib.core.task_get(id)
	
	if task['username'] != session.get('username', None):
		if task['username'] is not None:
			return stderr("Permission Denied","This task was started by {}. You do not have permission to complete a task you did not start.".format(task['username']),403)
		else:
			raise RuntimeError("Task (ID: {}) username cannot be None.".format(task['id']))

	if task['status'] == 0:
		# Still in progress
		return redirect(url_for('decom_step_check_wait', id=task['id']))
	elif task['status'] == 1 or task['status'] == 3:
		# Task complete
		system_id, actions, signed_actions = get_system_actions_from_redis(task)
		system = cortex.lib.systems.get_system_by_id(system_id)

		return workflow.render_template("check_complete.html", actions=actions, system=system, json_data=signed_actions, title="Decommission Node")
	else:
		# Task failed.
		return stderr("Bad Request", "Task (ID: {}) failed. You cannot complete the decommission at this time.", 404)

@workflow.action("start",title='Decomission', system_permission="decom", permission="systems.all.decom", menu=False, methods=['POST'])
def decom_step_start(id):
	## Get the actions list 
	actions_data = request.form['actions']

	## Decode it 
	signer = JSONWebSignatureSerializer(app.config['SECRET_KEY'])
	try:
		actions = signer.loads(actions_data)
	except itsdangerous.BadSignature as ex:
		abort(400)

	# Build the options to send on to the task
	options = {'actions': []}
	if request.form.get("runaction", None) is not None:
		for action in request.form.getlist("runaction"):
			options['actions'].append(actions[int(action)])
	options['wfconfig'] = workflow.config

	# Connect to NeoCortex and start the task
	neocortex = cortex.lib.core.neocortex_connect()
	task_id = neocortex.create_task(__name__, session['username'], options, description="Decommissions a system")

	# Redirect to the status page for the task
	return redirect(url_for('task_status', id=task_id))
