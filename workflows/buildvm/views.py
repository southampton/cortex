#!/usr/bin/env python

from cortex import app
from cortex.lib.workflow import CortexWorkflow
from cortex.lib.user import get_user_list_from_cache
import cortex.lib.core
import cortex.lib.admin
import datetime
from flask import Flask, request, session, redirect, url_for, flash, g, abort
import MySQLdb as mysql
import re
import json
from cortex.corpus import Corpus

workflow = CortexWorkflow(__name__)
workflow.add_permission('buildvm.sandbox', 'Create Sandbox VM')
workflow.add_permission('buildvm.standard', 'Create Standard VM')

################################################################################
## Sandbox VM Workflow view handler

@workflow.route("sandbox",title='Create Sandbox VM', order=20, permission="buildvm.sandbox", methods=['GET', 'POST'])
def sandbox():

	# Get the list of clusters
	all_clusters = cortex.lib.core.vmware_list_clusters(workflow.config['SB_VCENTER_TAG'])

	# Limit to the configured clusters
	clusters = []
	for cluster in all_clusters:
		if cluster['name'] in workflow.config['SB_CLUSTERS']:
			clusters.append(cluster)

	# Get the list of environments
	environments = cortex.lib.core.get_cmdb_environments()

	if request.method == 'GET':
		autocomplete_users = get_user_list_from_cache()
		## Show form
		return workflow.render_template("sandbox.html", clusters=clusters, environments=environments, title="Create Sandbox Virtual Machine", default_cluster=workflow.config['SB_DEFAULT_CLUSTER'], default_env=workflow.config['SB_DEFAULT_ENV'], os_names=workflow.config['SB_OS_DISP_NAMES'], os_order=workflow.config['SB_OS_ORDER'], os_types=workflow.config['SB_OS_TYPES'], autocomplete_users=autocomplete_users)

	elif request.method == 'POST':
		# Ensure we have all parameters that we require
		if 'sockets' not in request.form or 'cores' not in request.form or 'ram' not in request.form or 'disk' not in request.form or 'template' not in request.form or 'environment' not in request.form:
			flash('You must select options for all questions before creating', 'alert-danger')
			return redirect(url_for('sandbox'))

		# Form validation
		try:
			# Extract all the parameters
			cluster  = request.form['cluster']
			purpose  = request.form['purpose']
			comments = request.form['comments']
			sendmail = 'send_mail' in request.form
			primary_owner_who = request.form.get('primary_owner_who', None)
			primary_owner_role = request.form.get('primary_owner_role', None)
			secondary_owner_who = request.form.get('secondary_owner_who', None)
			secondary_owner_role = request.form.get('secondary_owner_role', None)

			# Validate the data (common between standard / sandbox)
			(sockets, cores, ram, disk, template, env, expiry) = validate_data(request, workflow.config['SB_OS_ORDER'], [e['id'] for e in environments])

			# Validate cluster against the list we've got
			if cluster not in [c['name'] for c in clusters]:
				raise ValueError('Invalid cluster selected (' + str(cluster) + ")")

		except ValueError as e:
			flash(str(e), 'alert-danger')
			return redirect(url_for('sandbox'))

		except Exception as e:
			flash('Submitted data invalid ' + str(e), 'alert-danger')
			return redirect(url_for('sandbox'))

		# Build options to pass to the task
		options = {}
		options['workflow'] = 'sandbox'
		options['sockets'] = sockets
		options['cores'] = cores
		options['ram'] = ram
		options['disk'] = disk
		options['template'] = template
		options['cluster'] = cluster
		options['env'] = env
		options['purpose'] = purpose
		options['comments'] = comments
		options['expiry'] = expiry
		options['sendmail'] = sendmail
		options['wfconfig'] = workflow.config
		options['primary_owner_who'] = primary_owner_who
		options['primary_owner_role'] = primary_owner_role
		options['secondary_owner_who'] = secondary_owner_who
		options['secondary_owner_role'] = secondary_owner_role

		# Connect to NeoCortex and start the task
		neocortex = cortex.lib.core.neocortex_connect()
		task_id = neocortex.create_task(__name__, session['username'], options, description="Creates and sets up a virtual machine (sandbox VMware environment)")

		# Log the Task ID
		cortex.lib.core.log(__name__, "workflow.buildvm.sandbox", "Build sandbox VM task {} started by {}.".format(task_id, session["username"]))

		# Redirect to the status page for the task
		return redirect(url_for('task_status', id=task_id))

################################################################################
## Standard VM Workflow view handler

@workflow.route("standard",title='Create Standard VM', order=10, permission="buildvm.standard", methods=['GET', 'POST'])
def standard():

	# Get the list of clusters
	all_clusters = cortex.lib.core.vmware_list_clusters(workflow.config['VCENTER_TAG'])

	# Limit to the configured clusters
	clusters = []
	for cluster in all_clusters:
		if cluster['name'] in workflow.config['CLUSTERS']:
			clusters.append(cluster)

	folders = []
	for folder in cortex.lib.core.vmware_list_folders(workflow.config['VCENTER_TAG']):
		if folder['name'] not in workflow.config.get('HIDE_FOLDERS', []):
			folders.append(folder)
	folders.sort(key=lambda x: x['fully_qualified_path'])

	# Get the list of environments
	environments = cortex.lib.core.get_cmdb_environments()

	if request.method == 'GET':
		autocomplete_users = get_user_list_from_cache()

		# Get the VM Specs from the DB
		try:
			vm_spec_json = cortex.lib.admin.get_kv_setting('vm.specs', load_as_json=True)
		except ValueError:
			flash("Could not parse JSON from the database.", "alert-danger")
			vm_spec_json = {}
			
		# Get the VM Specs Config from the DB.
		try:
			vm_spec_config_json = cortex.lib.admin.get_kv_setting('vm.specs.config', load_as_json=True)
		except ValueError:
			flash("Could not parse JSON from the database.", "alert-danger")
			vm_spec_config_json = {}

		## Show form
		return workflow.render_template("standard.html", clusters=clusters, environments=environments, folders=folders, os_names=workflow.config['OS_DISP_NAMES'], os_order=workflow.config['OS_ORDER'], network_names=workflow.config['NETWORK_NAMES'], networks_order=workflow.config['NETWORK_ORDER'], autocomplete_users=autocomplete_users, vm_spec_json=vm_spec_json, vm_spec_config_json=vm_spec_config_json, title="Create Standard Virtual Machine")

	elif request.method == 'POST':
		# Ensure we have all parameters that we require
		if 'sockets' not in request.form or 'cores' not in request.form or 'ram' not in request.form or 'disk' not in request.form or 'template' not in request.form or 'cluster' not in request.form or 'environment' not in request.form or 'network' not in request.form:
			flash('You must select options for all questions before creating', 'alert-danger')
			return redirect(url_for('standard'))

		# Form validation
		try:
			# Extract the parameters (some are extracted by validate_data)
			cluster  = request.form['cluster']
			task     = request.form['task']
			purpose  = request.form['purpose']
			comments = request.form['comments']
			sendmail = 'send_mail' in request.form
			network  = request.form['network']
			primary_owner_who = request.form.get('primary_owner_who', None)
			primary_owner_role = request.form.get('primary_owner_role', None)
			secondary_owner_who = request.form.get('secondary_owner_who', None)
			secondary_owner_role = request.form.get('secondary_owner_role', None)
			dns_aliases = request.form.get('dns_aliases', None)
			vm_folder_moid = request.form.get('vm_folder_moid', None)

			if dns_aliases is not None and len(dns_aliases) > 0:
				dns_aliases = dns_aliases.split(',')
			else:
				dns_aliases = []

			if vm_folder_moid is not None and len(vm_folder_moid) <= 0:
				vm_folder_moid = None

			# Validate the data (common between standard / sandbox)
			(sockets, cores, ram, disk, template, env, expiry) = validate_data(request, workflow.config['OS_ORDER'], [e['id'] for e in environments])

			# Validate cluster against the list we've got
			if cluster not in [c['name'] for c in clusters]:
				raise ValueError('Invalid cluster selected')

			# Validate network against the list we've got
			if network not in workflow.config['NETWORK_NAMES']:
				raise ValueError('Invalid network selected')

		except ValueError as e:
			flash(str(e), 'alert-danger')
			return redirect(url_for('standard'))

		except Exception as e:
			flash('Submitted data invalid', 'alert-danger')
			return redirect(url_for('standard'))

		# Build options to pass to the task
		options = {}
		options['workflow'] = 'standard'
		options['sockets'] = sockets
		options['cores'] = cores
		options['ram'] = ram
		options['disk'] = disk
		options['template'] = template
		options['cluster'] = cluster
		options['env'] = env
		options['task'] = task
		options['purpose'] = purpose
		options['comments'] = comments
		options['sendmail'] = sendmail
		options['wfconfig'] = workflow.config
		options['expiry'] = expiry
		options['network'] = network
		options['primary_owner_who'] = primary_owner_who
		options['primary_owner_role'] = primary_owner_role
		options['secondary_owner_who'] = secondary_owner_who
		options['secondary_owner_role'] = secondary_owner_role
		options['dns_aliases'] = dns_aliases
		options['vm_folder_moid'] = vm_folder_moid

		if 'NOTIFY_EMAILS' in app.config:
			options['notify_emails'] = app.config['NOTIFY_EMAILS']
		else:
			options['notify_emails'] = []

		# Connect to NeoCortex and start the task
		neocortex = cortex.lib.core.neocortex_connect()
		task_id = neocortex.create_task(__name__, session['username'], options, description="Creates and sets up a virtual machine (standard VMware environment)")

		# Log the Task ID
		cortex.lib.core.log(__name__, "workflow.buildvm.standard", "Build standard VM task {} started by {} with ServiceNow task {}".format(task_id, session["username"], values["task"]))

		# Redirect to the status page for the task
		return redirect(url_for('task_status', id=task_id))

################################################################################
## Common data validation / form extraction

def validate_data(r, templates, envs):

	# Get the VM Specs Config from the DB.
	try:
		vm_spec_config_json = cortex.lib.admin.get_kv_setting('vm.specs.config', load_as_json=True)
	except ValueError:
		flash("Could not parse JSON from the database.", "alert-danger")
		vm_spec_config_json = {}


	# Pull data out of request
	sockets  = r.form['sockets']
	cores	 = r.form['cores']
	ram	 = r.form['ram']
	disk	 = r.form['disk']
	template = r.form['template']
	env	 = r.form['environment']

	sockets = int(sockets)
	if vm_spec_config_json is not None and 'slider-sockets' in vm_spec_config_json and vm_spec_config_json['slider-sockets'].get('min', None) is not None and vm_spec_config_json['slider-sockets'].get('max', None) is not None:
		if not int(vm_spec_config_json['slider-sockets']['min']) <= sockets <= int(vm_spec_config_json['slider-sockets']['max']):
			raise ValueError('Invalid number of sockets selected')
	elif not 1 <= sockets <= 16:
		raise ValueError('Invalid number of sockets selected')

	cores = int(cores)
	if vm_spec_config_json is not None and 'slider-cores' in vm_spec_config_json and vm_spec_config_json['slider-cores'].get('min', None) is not None and vm_spec_config_json['slider-cores'].get('max', None) is not None:
		if not int(vm_spec_config_json['slider-cores']['min']) <= cores <= int(vm_spec_config_json['slider-cores']['max']):
			raise ValueError('Invalid number of cores per socket selected')
	elif not 1 <= cores <= 16:
		raise ValueError('Invalid number of cores per socket selected')

	ram = int(ram)
	if vm_spec_config_json is not None and 'slider-ram' in vm_spec_config_json and vm_spec_config_json['slider-ram'].get('min', None) is not None and vm_spec_config_json['slider-ram'].get('max', None) is not None:
		if not int(vm_spec_config_json['slider-ram']['min']) <= ram <= int(vm_spec_config_json['slider-ram']['max']):
			raise ValueError('Invalid amount of RAM selected')		
	elif not 2 <= ram <= 32:
		raise ValueError('Invalid amount of RAM selected')

	disk = int(disk)
	if vm_spec_config_json is not None and 'slider-disk' in vm_spec_config_json and vm_spec_config_json['slider-disk'].get('min', None) is not None and vm_spec_config_json['slider-disk'].get('max', None) is not None:
		if not int(vm_spec_config_json['slider-disk']['min']) <= disk <= int(vm_spec_config_json['slider-disk']['max']):
			raise ValueError('Invalid disk capacity selected')
	elif not 100 <= disk <= 2000:
		raise ValueError('Invalid disk capacity selected')

	if template not in templates:
		raise ValueError('Invalid template selected')

	if env not in envs:
		raise ValueError('Invalid environment selected')

	if 'expiry' in r.form and r.form['expiry'] is not None and len(r.form['expiry'].strip()) > 0:
		expiry = r.form['expiry']
		try:
			expiry = datetime.datetime.strptime(expiry, '%Y-%m-%d')
		except Exception as e:
			raise ValueError('Expiry date must be specified in YYYY-MM-DD format')
	else:
		expiry = None

	return (sockets, cores, ram, disk, template, env, expiry)
