#!/usr/bin/env python

from cortex import app
from cortex.lib.workflow import CortexWorkflow #, raise_if_workflows_locked
from cortex.lib.user import get_user_list_from_cache
from cortex.lib.systems import get_service_recipes_list, get_vm_recipes_list
import cortex.lib.core
import datetime
from flask import Flask, request, session, redirect, url_for, flash, g, abort, jsonify
import MySQLdb as mysql
import re
from cortex.corpus import Corpus
import json
import types

workflow = CortexWorkflow(__name__)
workflow.add_permission('service.create', 'Create New Service')

@workflow.route("create",title='Create New Service', order=20, permission="newserver", methods=['GET', 'POST'])
def createservice():
	# Get the list of clusters
	all_clusters = cortex.lib.core.vmware_list_clusters(workflow.config['VCENTER_TAG'])

	# Exclude any clusters that the config asks to:
	clusters = []
	for cluster in all_clusters:
		if cluster['name'] not in workflow.config['HIDE_CLUSTERS']:
			clusters.append(cluster)

	folders = []
	for folder in cortex.lib.core.vmware_list_folders(workflow.config['VCENTER_TAG']):
		if folder['name'] not in workflow.config.get('HIDE_FOLDERS', []):
			folders.append(folder)
	folders.sort(key=lambda x: x['fully_qualified_path'])

	
	curd = g.db.cursor(mysql.cursors.DictCursor)

	# Get the list of environments
	environments = cortex.lib.core.get_cmdb_environments()
	if request.method == 'GET':

		autocomplete_users = get_user_list_from_cache()
		autocomplete_service_recipes_names = get_service_recipes_list()
		autocomplete_vm_recipes_names = get_vm_recipes_list()
		
		return workflow.render_template("create_service.html", clusters=clusters, environments=environments, title="Create Service", os_names=workflow.config['OS_DISP_NAMES'], os_order=workflow.config['OS_ORDER'], autocomplete_users=autocomplete_users, autocomplete_service_recipes_names=autocomplete_service_recipes_names, autocomplete_vm_recipes_names=autocomplete_vm_recipes_names, folders=folders, network_names=workflow.config['NETWORK_NAMES'], networks_order=workflow.config['NETWORK_ORDER'])
	elif request.method == 'POST' and 'action' in request.form and request.form['action']=="create_recipe": # if it is POST, then it does need validation
				
		# Get the form in a dict
		form = parse_request_form(request.form)
		
		# Extract the data from the form
		service_name = form['service_name']
		vms_list = ""
		# Check if the request form contains only one vm recipe
		if (not isinstance(form['vm_recipe_name[]'], basestring)) and len(form['vm_recipe_name[]']) > 1:
			for vm in form['vm_recipe_name[]']:
				vms_list += vm + ", "
			vms_list = vms_list[:-2] # remove the last comma and space from the list
		else: # if the length is 1 do not split the list
			vms_list = form['vm_recipe_name[]']
		environment = form['env']
		email_notification = form.get('sendmail', "off")
		expiry = form['expiry']
		workflow_type = form['workflow_type']
		service_description = form.get('service_description', None)
		
		# Insert data into the database
		if not recipe_exists(service_name, "service", curd):
			curd.execute("INSERT INTO `service_recipes`(`name`, `env`, `workflow_type`, `vms_list`, `email_notification`, `expiry_date`, `description`) VALUES(%s, %s, %s, %s, %s, %s, %s)", (service_name, environment, workflow_type, vms_list, email_notification, expiry, service_description))
		
		if 'service_vms' in form.keys():
			for vm_name in form['service_vms'].keys():
				puppet_classes = form['service_vms'][vm_name]['puppet_classes']
				purpose = form['service_vms'][vm_name]['purpose']
				comments = form['service_vms'][vm_name]['comments']
				primary_owner_who = form['service_vms'][vm_name]['primary_owner_who']
				primary_owner_role = form['service_vms'][vm_name]['primary_owner_role']
				secondary_owner_who = form['service_vms'][vm_name]['secondary_owner_who']
				secondary_owner_role = form['service_vms'][vm_name]['secondary_owner_role']
				sockets = form['service_vms'][vm_name]['sockets']
				cores = form['service_vms'][vm_name]['cores']
				ram = form['service_vms'][vm_name]['ram']
				disk = form['service_vms'][vm_name]['disk']
				template = form['service_vms'][vm_name]['template']
				cluster = form['service_vms'][vm_name]['cluster']
				network = form['service_vms'][vm_name]['network']
				vm_folder_moid = form['service_vms'][vm_name]['vm_folder_moid']
				description = form['service_vms'][vm_name]['vm_description']
				if not recipe_exists(vm_name, "vm", curd):
					curd.execute("""INSERT INTO `vm_recipes`(
							`name`,
							`purpose`,
							`comments`,
							`primary_owner_who`,
							`primary_owner_role`,
							`secondary_owner_who`,
							`secondary_owner_role`,
							`sockets`,
							`cores`,
							`ram`,
							`disk`,
							`os`,
							`location_cluster`,
							`puppet_code`,
							`description`,
							`network`,
							`vm_folder_moid`) VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""", (vm_name, purpose, comments, primary_owner_who, primary_owner_role, secondary_owner_who, secondary_owner_role, sockets, cores, ram, disk, template, cluster, puppet_classes, description, network, vm_folder_moid,))
		
		# Commit the changes
		g.db.commit()

		return json.dumps(request.form.to_dict())
	elif request.method=='POST' and 'action' in request.form and request.form['action']=="use_recipe":
		# Get the list of clusters
		all_clusters = cortex.lib.core.vmware_list_clusters(workflow.config['VCENTER_TAG'])

		# Exclude any clusters that the config asks to:
		clusters = []
		for cluster in all_clusters:
			if cluster['name'] not in workflow.config['HIDE_CLUSTERS']:
				clusters.append(cluster)

		folders = []
		for folder in cortex.lib.core.vmware_list_folders(workflow.config['VCENTER_TAG']):
			if folder['name'] not in workflow.config.get('HIDE_FOLDERS', []):
				folders.append(folder)
		folders.sort(key=lambda x: x['fully_qualified_path'])

		# Get the list of environments
		environments = cortex.lib.core.get_cmdb_environments()


		# This needs to be integrated in the form verification for the whole service
		"""
		if 'sockets' not in request.form or 'cores' not in request.form or 'ram' not in request.form or 'disk' not in request.form or 'template' not in request.form or 'cluster' not in request.form or 'environment' not in request.form or 'network' not in request.form:
			flash('You must select options for all questions before creating', 'alert-danger')
			return redirect(url_for('create'))
		"""

		# parse the request form
		form = parse_request_form(request.form)

		# Ensure that the service wide configuration details are present
		service_required_keys = ['vm_recipes', 'env', 'workflow_type', 'task', 'service_name']
		validate_form(service_required_keys, form)

		# Get NeoCortex connection
		neocortex = cortex.lib.core.neocortex_connect()
		
		# Initialise the options dict
		options = {}
		
		# Initialise the the base options		
		options['vm_recipes'] = {}
		options['wfconfig'] = workflow.config
 
		# Load each VM recipe
		for vm_recipe in form['service_vms'].keys():
			
			#Validate the form for the VM recipe
			vm_required_keys = ['sockets', 'cores', 'ram', 'disk', 'template', 'cluster', 'environment', 'network']
			validate_form(vm_required_keys, form['service_vms'][vm_recipe])
		
			# Collect the form data into the options dict for the task
			options['vm_recipes'][vm_recipe] = {}
			options['vm_recipes'][vm_recipe]['wfconfig'] = workflow.config
			options['vm_recipes'][vm_recipe]['workflow'] = form['workflow_type']
			options['vm_recipes'][vm_recipe]['sockets'] = form['service_vms'][vm_recipe]['sockets']
			options['vm_recipes'][vm_recipe]['cores'] = form['service_vms'][vm_recipe]['cores']
			options['vm_recipes'][vm_recipe]['ram'] = form['service_vms'][vm_recipe]['ram']
			options['vm_recipes'][vm_recipe]['disk'] = form['service_vms'][vm_recipe]['disk']
			options['vm_recipes'][vm_recipe]['template'] = form['service_vms'][vm_recipe]['template']
			options['vm_recipes'][vm_recipe]['cluster'] = form['service_vms'][vm_recipe]['cluster']
			options['vm_recipes'][vm_recipe]['env'] = form['env']
			options['vm_recipes'][vm_recipe]['purpose'] = form['service_vms'][vm_recipe]['purpose']
			options['vm_recipes'][vm_recipe]['comments'] = form['service_vms'][vm_recipe]['comments']
			options['vm_recipes'][vm_recipe]['sendmail'] = form.get('sendmail', 'off')
			options['vm_recipes'][vm_recipe]['expiry'] = form.get('expiry', None)
			options['vm_recipes'][vm_recipe]['network'] = form['service_vms'][vm_recipe]['network']
			options['vm_recipes'][vm_recipe]['primary_owner_who'] = form['service_vms'][vm_recipe].get('primary_owner_who', None)
			options['vm_recipes'][vm_recipe]['primary_owner_role'] = form['service_vms'][vm_recipe].get('primary_owner_role', None)
			options['vm_recipes'][vm_recipe]['secondary_owner_who'] = form['service_vms'][vm_recipe].get('secondary_owner_who', None)
			options['vm_recipes'][vm_recipe]['secondary_owner_role'] = form['service_vms'][vm_recipe].get('secondary_owner_role', None)
			options['vm_recipes'][vm_recipe]['dns_aliases'] = form['service_vms'][vm_recipe].get('dns_aliases', None)
			options['vm_recipes'][vm_recipe]['vm_folder_moid'] = form['service_vms'][vm_recipe].get('vm_folder_moid', None)
			options['vm_recipes'][vm_recipe]['puppet_code'] = form['service_vms'][vm_recipe].get('puppet_classes', None)
			options['vm_recipes'][vm_recipe]['task'] = form['task']
			options['vm_recipes'][vm_recipe]['service_recipe_name'] = form['service_name']
			if 'NOTIFY_EMAILS' in app.config:
				options['vm_recipes'][vm_recipe]['notify_emails'] = app.config['NOTIFY_EMAILS']
			else:
				options['vm_recipes'][vm_recipe]['notify_emails'] = []

		# Create new Neocortex task
		task_id = neocortex.create_task(__name__, session['username'], options, description="Creates and sets up a service containing multiple VMs.")
		
		# Redirect to the task status page
		return redirect(url_for('task_status', id=task_id))

	elif request.method=='POST' and 'action' in request.form and request.form['action']=="delete_recipe":
		print("recipe should be deleted")

	elif request.method=='POST' and 'action' in request.form and request.form['action']=="update_recipe":
		print("recipe should be updated")

	else: 
		return "Look at me, I just did nothing"

@workflow.route("get_service_recipe",title='Get a recipe', methods=['POST'], menu=False)
@app.disable_csrf_check
def get_service_recipe():

	# Get the db cursor
	curd = g.db.cursor(mysql.cursors.DictCursor)

	# Get the service recipe name from the request form	
	service_recipe_name = ""
	if 'service_recipe_name' in request.get_json():
		service_recipe_name = request.get_json()['service_recipe_name']

	# Query the database to get the service recipe
	curd.execute("SELECT * FROM `service_recipes` WHERE `name`=%s", (service_recipe_name,))

	# Fetch the unprocessed service recipe from the result
	service_recipe_raw = curd.fetchone()
	
	# Initialise dict which holds the processed service recipe
	service_recipe = {}

	if service_recipe_raw is not None:
		
		# Store the details about the recipe in a dict
		service_recipe['name'] = service_recipe_raw['name']
		service_recipe['env'] = service_recipe_raw['env']
		service_recipe['email_notification'] = service_recipe_raw['email_notification']
		service_recipe['expiry_date'] = service_recipe_raw['expiry_date']
		service_recipe['description'] = service_recipe_raw['description']
		service_recipe['vms_recipes'] = {}

		# For each vm in the list
		for vm_recipe_name in service_recipe_raw['vms_list'].split(", "):
			
			# Query the database
			curd.execute("SELECT * FROM `vm_recipes` WHERE `name`=%s", (vm_recipe_name,))
			
			# Fetch the VM recipe
			vm_recipe= curd.fetchone()
			
			# Add the data to the processed service recipe dict
			if vm_recipe is not None:
				service_recipe['vms_recipes'][vm_recipe['name']] = {"purpose" : vm_recipe['purpose'],
								     "comments": vm_recipe['comments'],
								     "primary_owner_who": vm_recipe['primary_owner_who'],
								     "primary_owner_role": vm_recipe['primary_owner_role'],
								     "secondary_owner_who": vm_recipe['secondary_owner_who'],
								     "secondary_owner_role": vm_recipe['secondary_owner_role'],
								     "sockets": vm_recipe['sockets'],
								     "cores": vm_recipe['cores'],
								     "ram": vm_recipe['ram'],
								     "disk": vm_recipe['disk'],
								     "os": vm_recipe['os'],
								     "location_cluster": vm_recipe['location_cluster'],
								     "puppet_code": vm_recipe['puppet_code'],
								     "description": vm_recipe['description'],
								     "network": vm_recipe['network'],
								     "vm_folder_moid": vm_recipe['vm_folder_moid'],
								}
	# Return as JSON
	return jsonify(service_recipe)

@workflow.route("update_vm_recipe",title='Update a VM recipe', methods=['POST'], menu=False)
@app.disable_csrf_check
def update_vm_recipe():

        # Get the db cursor
        curd = g.db.cursor(mysql.cursors.DictCursor)
	
	form = parse_request_form(request.form)['service_vms']
	
	# The form should only contain one VM, so extract its name
	vm_name = next(iter(form))
	
	# Extract form data
	purpose = form[vm_name]['purpose']
	comments = form[vm_name]['comments']
	primary_owner_who = form[vm_name]['primary_owner_who']
	primary_owner_role = form[vm_name]['primary_owner_role']
	secondary_owner_who = form[vm_name]['secondary_owner_who']
	secondary_owner_role = form[vm_name]['secondary_owner_role']
	sockets = form[vm_name]['sockets']
	cores = form[vm_name]['cores']
	ram = form[vm_name]['ram']
	disk = form[vm_name]['disk']
	os = form[vm_name]['template']
	location_cluster = form[vm_name]['cluster']
	puppet_code = form[vm_name]['puppet_classes']
	description = form[vm_name]['vm_description']
	network = form[vm_name]['network']
	vm_folder_moid = form[vm_name]['vm_folder_moid']
	
	# Update the table
	curd.execute("""UPDATE `vm_recipes` 
			SET `purpose` = %s,
			`comments` = %s,
			`primary_owner_who` = %s,
			`primary_owner_role` = %s,
			`secondary_owner_who` = %s,
			`secondary_owner_role` = %s,
			`sockets` = %s,
			`cores` = %s,
			`ram` = %s,
			`disk` = %s,
			`os` = %s,
			`location_cluster` = %s,
			`puppet_code` = %s,
			`description` = %s,
			`network` = %s,
			`vm_folder_moid` = %s
			WHERE `name` = %s;""", (purpose, comments, primary_owner_who, primary_owner_role, secondary_owner_who, secondary_owner_role, sockets, cores, ram, disk, os, location_cluster, puppet_code, description, network, vm_folder_moid, vm_name,))
	
	# Commit the changes
	g.db.commit()

	# Maybe return a 200 OK later
	return json.dumps(form)


@workflow.route("get_vm_recipe",title='Get a VM recipe', methods=['POST'], menu=False)
@app.disable_csrf_check
def get_vm_recipe():

        # Get the db cursor
        curd = g.db.cursor(mysql.cursors.DictCursor)

        # Get the VM recipe name from the request form     
        vm_recipe_name = ""
        if 'vm_recipe_name' in request.get_json():
                vm_recipe_name = request.get_json()['vm_recipe_name']

        # Query the database to get the VM recipe
        curd.execute("SELECT * FROM `vm_recipes` WHERE `name`=%s", (vm_recipe_name,))

	# Fetch the VM recipe
	vm_recipe= curd.fetchone()

        # Return as JSON
        return jsonify(vm_recipe)


# Helper that parses the request data
def parse_request_form(form):
	
	# Constant: the key under which all the VM recipes are kept inside the form sent by the template
	BASE_STRING = "service_vms"
	
	result_dict = {}

	# The dict generated by this loop will look pretty much like:
	#
	# form = {"service_name": "banner",
	#	  "expiry_date": "31-08-2019",
	#	  "another_service_wide_property": "some_value",
	#	  "vm_recipes":{
	#		  "banner_db": {"ram":"2GB", "disk":"100GB", etc.},
	#		  "some_other_vm": {"ram":"8GB", "disk":"400GB", etc.},
	#		  "recip_name": {"attribute_1": "value_1", "attribute_2": "value_2", etc.},
	#		  ... and so on
	#		  }
	#	  }
	#
	for index in form.keys():
		if BASE_STRING in index:
			regex_search = re.search("\[(.*)\]\[(.*)\]", index)
			recipe_name = regex_search.group(1)
			attribute = regex_search.group(2)
			value = form[index]
			if BASE_STRING not in result_dict.keys():
				result_dict[BASE_STRING] = {recipe_name:{attribute:value}}
			elif recipe_name not in result_dict[BASE_STRING].keys():
				result_dict[BASE_STRING][recipe_name] = {attribute:value}
			elif attribute not in result_dict[BASE_STRING][recipe_name].keys():
				result_dict[BASE_STRING][recipe_name][attribute] = value
		else:
			result_dict[index] = form.getlist(index) if len(form.getlist(index)) > 1 else form[index]
		
	return result_dict

# Helper function that determines if a recipe for the enitity with the given name already exists
def recipe_exists(recipe_name, entity, cursor):
	
	# Check if service recipe exists
	if entity is "service":

		cursor.execute("SELECT COUNT(`name`) AS count FROM `service_recipes` WHERE `name`=%s", (recipe_name,))

		result = cursor.fetchone()
		
		if result['count'] == 1:
			return True
		return False

	# Check if VM recipe exists
	elif entity is "vm":
		
		cursor.execute("SELECT COUNT(`name`) AS count FROM `vm_recipes` WHERE `name`=%s", (recipe_name,))
		
		result = cursor.fetchone()
		
		if result['count'] == 1:
			return True
		return False
	
	# If the entity is something else, abort
	else:
		app.logger.warn('There is no entity of this type')
		return abort(400)

# Helper which ensures that all the required keys
# from a given list are present in a request form
# so you don't have to write extremely long if statements
def validate_form(required_keys, request_dict):
	
	for key in required_keys:
		if key not in request_dict.keys():
			return redirect(url_for('createservice'))
