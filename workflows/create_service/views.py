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

	# Get the list of environments
	environments = cortex.lib.core.get_cmdb_environments()

	if request.method == 'GET':
		autocomplete_users = get_user_list_from_cache()
		return workflow.render_template("create_service.html", clusters=clusters, environments=environments, title="Create Service", default_cluster=workflow.config['SB_DEFAULT_CLUSTER'], default_env=workflow.config['SB_DEFAULT_ENV'], os_names=workflow.config['SB_OS_DISP_NAMES'], os_order=workflow.config['SB_OS_ORDER'], autocomplete_users=autocomplete_users)#, existing_recipes_names)
	else: # if it is POST, then it does need validation
		return workflow.render_template("create_service.html")# return redirect(url_for('task_status', id=task_id))
"""
@workflow.action("get_recipe", title="Create New Service", desc="Get the recipe for the existing service", permission="service.get_recipe")
def get_recipe(name):
	# Will need to add a a new table that will contain recipes maybe?
	# You must find a way of referencing another VM by using the service name (which might be found in the task table?)
	
	
	
	# return recipe """
