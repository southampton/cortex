#!/usr/bin/env python

from cortex import app
from cortex.lib.workflow import CortexWorkflow
from cortex.lib.user import get_user_list_from_cache
import cortex.lib.core
import datetime
from flask import Flask, request, session, redirect, url_for, flash, g, abort
import MySQLdb as mysql
import re
from cortex.corpus import Corpus
import json

workflow = CortexWorkflow(__name__)
workflow.add_permission('service.create', 'Create New Service')

@workflow.route("create",title='Create New Service', order=20, permission="newserver", methods=['GET', 'POST'])
def createservice():
	# Get the list of clusters
	all_clusters = cortex.lib.core.vmware_list_clusters(workflow.config['SB_VCENTER_TAG'])

	# Exclude any clusters that the config asks to:
	clusters = []
	for cluster in all_clusters:
		if cluster['name'] in workflow.config['SB_CLUSTERS']:
			clusters.append(cluster)


	curd = g.db.cursor(mysql.cursors.DictCursor)

	# Get the list of environments
	environments = cortex.lib.core.get_cmdb_environments()
	if request.method == 'GET':
		autocomplete_users = get_user_list_from_cache()	
		return workflow.render_template("create_service.html", clusters=clusters, environments=environments, title="Create Service", default_cluster=workflow.config['SB_DEFAULT_CLUSTER'], default_env=workflow.config['SB_DEFAULT_ENV'], os_names=workflow.config['SB_OS_DISP_NAMES'], os_order=workflow.config['SB_OS_ORDER'], autocomplete_users=autocomplete_users)#, existing_recipes_names)
	else: # if it is POST, then it does need validation
				
		# Get the form in a dict
		form = parse_request_form(request.form)
		
		# Extract the data from the form
		service_name = form['service_name']
		vms_list = ""
		if len(form['vm_recipe_name[]']) > 1:
			for vm in form['vm_recipe_name[]']:
				vms_list += vm + ", "
			vms_list = vms_list[:-2] # remove the last comma and space from the list
		else: # if the length is 1 do not split the list
			vms_list = form['vm_recipe_name[]']
		environment = "dev" # this is a default value for now cause the form itself is not finished
		email_notification = "off" # again, default value because the form is still not in its final stage
		
		curd.execute("INSERT INTO `service_recipe`(`name`, `environment`, `vms_list`, `email_notification`) VALUES(%s, %s, %s, %s)", (service_name, environment, vms_list, email_notification,))
		
		g.db.commit()

		return json.dumps(request.form.to_dict())  # return redirect(url_for('task_status', id=task_id))



@workflow.route("get_service_recipe",title='Create New Service', order=20, permission="newserver", methods=['POST'])
@app.disable_csrf_check
def get_service_recipe():
	# Get the db cursor
	curd = g.db.cursor(mysql.cursors.DictCursor)
	
	# Get the service recipe name from the request form	
	service_recipe_name = ""
	if 'service_recipe_name' in request.form:
		service_recipe_name = request.form['service_recipe_name']

	# Query the database to get the service recipe
	curd.execute("SELECT * FROM `service_recipe` WHERE `name`=%s", (service_recipe_name,))
	service_recipe_raw = curd.fetchone()

	# Store the details about the recipe in a dict
	service_recipe['name'] = service_recipe_raw['name']
	service_recipe['environment'] = service_recipe_raw['environment']
	service_recipe['email_notification'] = service_recipe_raw['email_notification']

	# For each vm in the list, query the databse
	for vm_recipe_name in service_recipe_raw['vms_list']:
		curd.execute("SELECT FROM `vm_recipe` WHERE `name`=%s", (vm_recipe_name,))
		vm_recipe= curd.fetchone()
		
		# Add the data to the dict
		service_recipe[vm_recipe['name']] = {"purpose" : vm_recipe['purpose'],
						     "comments": vm_recipe['comments'],
						     "primary_owner_who": vm_recipe['primary_owner_who'],
						     "priamry_owner_role": vm_recipe['primary_owner_role'],
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
		}

# Helper that parses the request data
def parse_request_form(form):
	BASE_STRING = "service_vms"
	STATIC_FIELDS = ["_csrf_token", "service_name", "vm_recipe_name[]"]
	result_dict = {}
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
