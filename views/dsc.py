from cortex import app
import cortex.lib.core
import cortex.lib.systems
import cortex.lib.cmdb
import cortex.lib.classes
from cortex.lib.user import does_user_have_permission, does_user_have_system_permission, does_user_have_any_system_permission, is_system_enrolled
from cortex.corpus import Corpus
from flask import Flask, request, session, redirect, url_for, flash, g, abort, make_response, render_template, jsonify, Response
import os
import time
import datetime
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

@app.route('/dsc/classify/<id>', methods=['GET', 'POST'])
@cortex.lib.user.login_required
def dsc_classify_machine(id):

	system = cortex.lib.systems.get_system_by_id(id)
	# return jsonify(system)

	if system == None:
		abort(404)
	
	curd = g.db.cursor(mysql.cursors.DictCursor)

	# retrieve all the systems
	default_roles = ['Default', 'SQLServer', 'Web Server', 't1', 't2']
	curd.execute("SELECT `roles`, `config` FROM `dsc_config` WHERE `system_id` = %s", (id, ))
	existing_data = curd.fetchone()
	exist_role = ""
	exist_config = ""
	# get existing info
	if existing_data is not None:
		exist_role = existing_data['roles'].split(',')
		exist_config = existing_data['config']

	

	if request.method == 'GET':
		
		if does_user_have_permission('dsc.view'):
			return render_template('dsc/classify.html', title="DSC", system=system, active='dsc', roles=default_roles, yaml=exist_config, set_roles=exist_role)
		else:
			abort(403)
	elif request.method == 'POST':
		if not does_user_have_permission('dsc.view'):
			abort(403)
		configuration = request.form['configurations']
		role = request.form.get('selected_values', '')

		error = False

		# validate the configuration YAML
		try:
			data = yaml.safe_load(configuration)
		except Exception as e:
			flash('Invalid YAML syntax for classes: ' + str(e), 'alert-danger')
			error = True
			raise e

		try:
			if not data is None:
				assert isinstance(data, dict)
		except Exception as e:
			flash('Invalid YAML syntax for classes: result was not a list of classes, did you forget a trailing colon? ' + str(e), 'alert-danger')
			error = True

		if error:
			flash('There was an unexpected error somewhere when parsing the YAML. Please check this before continuing')


		curd.execute('REPLACE INTO dsc_config (system_id, roles, config) VALUES (%s, %s, %s)', (id, role, configuration))
		g.db.commit()

		

	curd.execute("SELECT roles, config FROM dsc_config WHERE system_id = %s", (id, ))
	existing_data = curd.fetchone()
	exist_role = ""
	exist_config = ""
	if existing_data is not None:
		exist_role = existing_data['roles'].split(',')
		exist_config = existing_data['config']

	return render_template('dsc/classify.html', title="DSC", system=system, active='dsc', roles=default_roles, yaml=exist_config, set_roles=exist_role)