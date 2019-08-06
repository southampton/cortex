from cortex import app
import cortex.lib.core
import cortex.lib.systems
import cortex.lib.cmdb
import cortex.lib.classes
import cortex.lib.dsc
from cortex.lib.user import does_user_have_permission, does_user_have_system_permission, does_user_have_any_system_permission, is_system_enrolled
from cortex.corpus import Corpus
from flask import Flask, request, session, redirect, url_for, flash, g, abort, make_response, render_template, jsonify, Response
import json
import re
import werkzeug
import MySQLdb as mysql
import yaml
import csv
import io
import requests
import cortex.lib.rubrik
from flask.views import MethodView
from pyVmomi import vim

def generate_new_yaml(proxy, oldRole, oldConfig, newRole, newConfig):
	#configs should be passed in as string
	if newRole == "":
		return json.dumps("")
	else:
		oldConfig = json.loads(oldConfig)
		newConfig = json.loads(newConfig)

		roles_info = cortex.lib.dsc.get_roles(proxy)

		removed_values = list(set(oldRole) - set(newRole))
		added_values = list(set(newRole) - set(oldRole))

		modified_config = newConfig

		for added in added_values:
			if added == "":
				continue
			modified_config[added] = roles_info[added]
	
		for removed in removed_values:
			if removed == "":
				continue
			del modified_config[removed]

		return json.dumps(modified_config)



############################################################################

def generate_reset_yaml(proxy, roles):
	roles_info = cortex.lib.dsc.get_roles(proxy)
	config = {}
	for role in roles:
		if role == '':
			continue
		config[role] = roles_info[role]
	return json.dumps(config)

############################################################################

@app.route('/dsc/classify/<id>', methods=['GET', 'POST'])
@cortex.lib.user.login_required
def dsc_classify_machine(id):

	system = cortex.lib.systems.get_system_by_id(id)

	if system == None:
		abort(404)
	
	curd = g.db.cursor(mysql.cursors.DictCursor)

	default_roles = []
	dsc_proxy = cortex.lib.dsc.dsc_connect()
	roles_info = cortex.lib.dsc.get_roles(dsc_proxy)
	for role in roles_info:
		default_roles.append(role)

	# return jsonify(roles_info['UOSWebCustomSite_Install'][0]['Name'])

	# retrieve all the systems
	# default_roles = ['Default', 'SQLServer', 'Web Server', 't1', 't2']
	curd.execute("SELECT `roles`, `config` FROM `dsc_config` WHERE `system_id` = %s", (id, ))
	existing_data = curd.fetchone()
	exist_role = ""
	exist_config = ""
	# get existing info
	if existing_data is not None:
		exist_role = existing_data['roles'].split(',')
		exist_config = yaml.dump(json.loads(existing_data['config']))
	

	if request.method == 'GET':
		
		if does_user_have_permission('dsc.view'):
			return render_template('dsc/classify.html', title="DSC", system=system, active='dsc', roles=default_roles, yaml=exist_config, set_roles=exist_role, role_info=roles_info)
		else:
			abort(403)
	elif request.method == 'POST':


		checked_boxes = json.loads(request.form['checked_values'])
		for group in checked_boxes:
			del checked_boxes[group]['prevObject']
		if request.form['button'] == 'save_changes':
			#check for permissions
			if not does_user_have_permission('dsc.edit'):
				abort(403)
			
			# get the new role and configuration entered
			role = request.form.get('selected_values', '')
			configuration = request.form['configurations']
			
			try:
				data = yaml.safe_load(configuration)
			except Exception as e:
				flash('Invalid YAML syntax for classes: ' + str(e), 'alert-danger')
				error = True
				raise e

			if data != None:
				roles = json.dumps((data))
				if roles != ",".join(exist_role):
					new_yaml = generate_new_yaml(dsc_proxy, exist_role, json.dumps(yaml.load(exist_config)), role.split(","), json.dumps(yaml.load(configuration)))
					# return new_yaml

				# return jsonify(((new_yaml)))
				# cortex.lib.dsc.dsc_generate_files(dsc_proxy, system['name'], new_yaml)

				curd.execute('REPLACE INTO dsc_config (system_id, roles, config) VALUES (%s, %s, %s)', (id, role, new_yaml))
				# curd.execute('REPLACE INTO dsc_config (system_id, roles) VALUES (%s, %s)', (id, role))
				g.db.commit()



		elif request.form['button'] == 'reset':
			role = request.form.get('selected_values', '')
			new_config = generate_reset_yaml(dsc_proxy, role.split(","))
			curd.execute('REPLACE INTO dsc_config (system_id, roles, config) VALUES (%s, %s, %s)', (id, role, new_config))
			g.db.commit()
		

	curd.execute("SELECT roles, config FROM dsc_config WHERE system_id = %s", (id, ))
	existing_data = curd.fetchone()
	exist_role = ""
	exist_config = ""
	if existing_data is not None:
		exist_role = existing_data['roles'].split(',')
		exist_config = yaml.dump(json.loads(existing_data['config']))

	return render_template('dsc/classify.html', title="DSC", system=system, active='dsc', roles=default_roles, yaml=exist_config, set_roles=exist_role, role_info=roles_info)
