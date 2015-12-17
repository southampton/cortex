#!/usr/bin/python
#

from cortex import app
import cortex.core
from flask import Flask, request, session, redirect, url_for, flash, g, abort, make_response, render_template, jsonify
import os 
import time
import json
import re
import werkzeug
import MySQLdb as mysql
import yaml

################################################################################

@app.route('/puppet/enc/<int:id>', methods=['GET', 'POST'])
@cortex.core.login_required
def puppet_enc_edit(id):
	# Get the system out of the database
	system = cortex.core.get_system_by_id(id)
	environments = cortex.core.get_puppet_environments()
	env_dict = cortex.core.get_environments_as_dict()

	# If we've got a new node, then don't show "None"
	if system['puppet_classes'] is None:
		system['puppet_classes'] = "# Global variables to include can be entered here"
	if system['puppet_variables'] is None:
		system['puppet_variables'] = "# Classes to include can be entered here"
	if system['puppet_certname'] is None:
		system['puppet_certname'] = ""

	# On any GET request, just display the information
	if request.method == 'GET':
		return render_template('systems-puppet-enc.html', system=system, active='systems', environments=environments)

	# On any POST request, validate the input and then save
	elif request.method == 'POST':
		# Extract data from form
		certname = request.form.get('certname', '')
		environment = request.form.get('environment', '')
		classes = request.form.get('classes', '')
		variables = request.form.get('variables', '')
		if 'include_default' in request.form:
			include_default = True
		else:
			include_default = False
		error = False

		# Validate certificate name
		if len(certname.strip()) == 0:
			flash('Invalid certificate name', 'alert-danger')
			error = True

		# Validate environement:
		if environment not in [e['id'] for e in environments]:
			flash('Invalid environment', 'alert-danger')
			error = True

		# Validate classes YAML
		try:
			yaml.load(classes)
		except Exception, e:
			flash('Invalid YAML syntax for classes: ' + str(e), 'alert-danger')
			error = True

		# Validate variables YAML
		try:
			yaml.load(variables)
		except Exception, e:
			flash('Invalid YAML syntax for variables: ' + str(e), 'alert-danger')
			error = True

		# On error, overwrite what is in the system object with our form variables
		# and return the page back to the user for fixing
		if error:
			system['puppet_certname'] = certname
			system['puppet_env'] = environment
			system['puppet_classes'] = classes
			system['puppet_variables'] = variables
			system['puppet_include_default'] = include_default
			return render_template('systems-puppet-enc.html', system=system, active='systems', environments=environments)

		# Get a cursor to the database
		cur = g.db.cursor(mysql.cursors.DictCursor)

		# Update the system
		cur.execute('UPDATE `puppet_nodes` SET `certname` = %s, `env` = %s, `classes` = %s, `variables` = %s, `include_default` = %s WHERE `id` = %s', (certname, env_dict[environment]['puppet'], classes, variables, include_default, id))
		g.db.commit();

		# Redirect back to the systems page
		flash('Puppet ENC for host ' + system['name'] + ' updated', 'alert-success')

		return redirect(url_for('systems'))

@app.route('/puppet/nodes')
@cortex.core.login_required
def puppet_nodes():
	# Get a cursor to the databaseo
	cur = g.db.cursor(mysql.cursors.DictCursor)

	# Get OS statistics
	cur.execute('SELECT `puppet_nodes`.`certname` AS `certname`, `systems`.`id` AS `id`, `systems`.`name` AS `name`  FROM `puppet_nodes` LEFT JOIN `systems` ON `puppet_nodes`.`id` = `systems`.`id` ORDER BY `puppet_nodes`.`certname` ')
	results = cur.fetchall()

	return render_template('puppet-nodes.html', active='puppet', data=results)

