#!/usr/bin/python

from cortex import app
from cortex.lib.workflow import CortexWorkflow
import cortex.lib.core
import cortex.lib.systems
from cortex.corpus import Corpus
from flask import Flask, request, session, redirect, url_for, flash, g, abort, render_template
from pyVmomi import vim
from itsdangerous import JSONWebSignatureSerializer

workflow = CortexWorkflow(__name__)
workflow.add_permission('systems.all.decom', 'Decommission any system')
workflow.add_system_permission('decom', 'Decommission system')



@workflow.action("prepare",title='Decommission', desc="Begins the process of decommissioning this system", system_permission="decom", permission="systems.all.decom")
def decom_step1(id):
	system = cortex.lib.systems.get_system_by_id(id)
	if system is None:
		abort(404)

	return workflow.render_template("step1.html", system=system, title="Decommission system")

@workflow.action("check",title='Decomission', system_permission="decom", permission="systems.all.decom",menu=False)
def decom_step2(id):
	# in this step we work out what steps to perform
	# then we load this into a list of steps, each step being a dictionary
	# this is used on the page to list the steps to the user
	# the list is also used to generate a JSON document which we sign using
	# app.config['SECRET_KEY'] and then send that onto the page as well.

	# load the corpus library
	corpus = Corpus(g.db,app.config)

	system = cortex.lib.systems.get_system_by_id(id)
	if system is None:
		abort(404)

	actions = []

	systemenv = None
	## Find the environment that this VM is in based off of the CMDB env
	if 'cmdb_environment' in system:
		if system['cmdb_environment'] is not None:
			for env in app.config['ENVIRONMENTS']:
				if env['name'] == system['cmdb_environment']:
					# We found the environment matching the system
					systemenv = env
					break


	## Is the system linked to vmware?
	if 'vmware_uuid' in system:
		if system['vmware_uuid'] is not None:
			if len(system['vmware_uuid']) > 0:
				## The system is linked to vmware - e.g. a VM exists

				vmobj = corpus.vmware_get_vm_by_uuid(system['vmware_uuid'],system['vmware_vcenter'])

				if vmobj:
					if vmobj.runtime.powerState == vim.VirtualMachine.PowerState.poweredOn:
						actions.append({'id': 'vm.poweroff', 'desc': 'Power off the virtual machine ' + system['name'], 'detail': 'UUID ' + system['vmware_uuid'] + ' on ' + system['vmware_vcenter'], 'data': {'uuid': system['vmware_uuid'], 'vcenter': system['vmware_vcenter']}})

					actions.append({'id': 'vm.delete', 'desc': 'Delete the virtual machine ' + system['name'], 'detail': ' UUID ' + system['vmware_uuid'] + ' on ' + system['vmware_vcenter'], 'data': {'uuid': system['vmware_uuid'], 'vcenter': system['vmware_vcenter']}})

	## Is the system linked to service now?
	if 'cmdb_id' in system:
		if system['cmdb_id'] is not None:
			if len(system['cmdb_id']) > 0:

				if system['cmdb_is_virtual']:
					if system['cmdb_operational_status'] != u'Deleted':
						actions.append({'id': 'cmdb.update', 'desc': 'Mark the system as Deleted in the CMDB', 'detail': system['cmdb_id'] + " on " + app.config['SN_HOST'], 'data': system['cmdb_id']})
				else:
					if system['cmdb_operational_status'] != u'Decommissioned':
						actions.append({'id': 'cmdb.update', 'desc': 'Mark the system as Decommissioned in the CMDB', 'detail': system['cmdb_id'] + " on " + app.config['SN_HOST'], 'data': system['cmdb_id']})

	## Ask infoblox if a DNS host object exists for the name of the system
	try:
		refs = corpus.infoblox_get_host_refs(system['name'] + ".soton.ac.uk")

		if refs is not None:
			for ref in refs:
				actions.append({'id': 'dns.delete', 'desc': 'Delete the DNS record ' + ref.split(':')[-1], 'detail': 'Delete the name ' + system['name'] + '.soton.ac.uk - Infoblox reference: ' + ref, 'data': ref})

	except Exception as ex:
		flash("Warning - An error occured when communicating with Infoblox: " + str(type(ex)) + " - " + str(ex),"alert-warning")

	## Check if a puppet record exists
	if 'puppet_certname' in system:
		if system['puppet_certname'] is not None:
			if len(system['puppet_certname']) > 0:
				actions.append({'id': 'puppet.cortex.delete', 'desc': 'Delete the Puppet ENC configuration', 'detail': system['puppet_certname'] + ' on ' + request.url_root, 'data': system['id']})
				actions.append({'id': 'puppet.master.delete', 'desc': 'Delete the system from the Puppet Master', 'detail': system['puppet_certname'] + ' on ' + app.config['PUPPET_MASTER'], 'data': system['puppet_certname']})

	## Check if TSM backups exist
	try:
		tsm_client = corpus.tsm_get_system(system['name'])
		#if the TSM client is not decomissioned, then decomission it
		if tsm_client['DECOMMISSIONED'] is None:
			actions.append({'id': 'tsm.decom', 'desc': 'Decommission the system in TSM', 'detail': tsm_client['NAME']  + ' on server ' + tsm_client['SERVER'], 'data': {'NAME': tsm_client['NAME'], 'SERVER': tsm_client['SERVER']}})
	except requests.execptions.HTTPError as e:
		flash("Warning - An error occured when communicating with TSM ", "alert-warning")
	except LookupError:
		pass

	# We need to check all (unique) AD domains as we register development
	# Linux boxes to the production domain
	tested_domains = set()
	for adenv in app.config['WINRPC']:
		try:
			# If we've not tested this CortexWindowsRPC host before
			if app.config['WINRPC'][adenv]['host'] not in tested_domains:
				# Add it to the set of tested hosts
				tested_domains.update([app.config['WINRPC'][adenv]['host']])

				# If an AD object exists, append an action to delete it from that environment
				if corpus.windows_computer_object_exists(adenv, system['name']):
					actions.append({'id': 'ad.delete', 'desc': 'Delete the Active Directory computer object', 'detail': system['name'] + ' on domain ' + app.config['WINRPC'][adenv]['domain'], 'data': {'hostname': system['name'], 'env': adenv}})

		except Exception as ex:
			flash("Warning - An error occured when communicating with Active Directory: " + str(type(ex)) + " - " + str(ex), "alert-warning")

	# If there are actions to be performed, add on an action to raise a ticket to ESM (but not for Sandbox!)
	if len(actions) > 0 and system['class'] != "play":
		actions.append({'id': 'ticket.ops', 'desc': 'Raises a ticket with operations to perform manual steps, such as removal from monitoring', 'detail': 'Creates a ticket in Service Now and assigns it to ' + workflow.config['TICKET_TEAM'], 'data': {'hostname': system['name']}})

	# Turn the actions list into a signed JSON document via itsdangerous
	signer = JSONWebSignatureSerializer(app.config['SECRET_KEY'])
	json_data = signer.dumps(actions)

	return workflow.render_template("step2.html", actions=actions, system=system, json_data=json_data, title="Decommission Node")

@workflow.action("start",title='Decomission', system_permission="decom", permission="systems.all.decom", menu=False, methods=['POST'])
def decom_step3(id):
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
