#!/usr/bin/python

from cortex import app
from cortex.lib.workflow import CortexWorkflow
import cortex.lib.core
import datetime
from flask import Flask, request, session, redirect, url_for, flash, g, abort
import MySQLdb as mysql
import re
from cortex.corpus import Corpus

workflow = CortexWorkflow(__name__)
workflow.add_permission('buildvm.sandbox', 'Create Sandbox VM')
workflow.add_permission('buildvm.standard', 'Create Standard VM')
workflow.add_permission('buildvm.student', 'Create Student VM')

################################################################################
## Sandbox VM Workflow view handler
@workflow.route("sandbox",title='Create Sandbox VM', order=20, permission="buildvm.sandbox", methods=['GET', 'POST'])
def sandbox():
	# Get the list of clusters
	clusters = cortex.lib.core.vmware_list_clusters("srv01197")

	# Get the list of environments
	environments = cortex.lib.core.get_cmdb_environments()

	if request.method == 'GET':
		## Show form
		return workflow.render_template("sandbox.html", clusters=clusters, environments=environments, title="Create Sandbox Virtual Machine", default_env='dev', default_cluster='CHARTREUSE', os_names=workflow.config['SB_OS_DISP_NAMES'], os_order=workflow.config['SB_OS_ORDER'])

	elif request.method == 'POST':
		# Ensure we have all parameters that we require
		if 'sockets' not in request.form or 'cores' not in request.form or 'ram' not in request.form or 'disk' not in request.form or 'template' not in request.form or 'environment' not in request.form:
			flash('You must select options for all questions before creating', 'alert-danger')
			return redirect(url_for('sandbox'))
		
		# Form validation
		try:
			# Extract all the parameters
			purpose  = request.form['purpose']
			comments = request.form['comments']
			sendmail = 'send_mail' in request.form

			# Validate the data (common between standard / sandbox)
			(sockets, cores, ram, disk, template, env, expiry) = validate_data(request, workflow.config['SB_OS_ORDER'], [e['id'] for e in environments])

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
		#options['cluster'] = cluster	## Commenting out whilst we only have one cluster
		options['cluster'] = 'CHARTREUSE'
		options['env'] = env
		options['purpose'] = purpose
		options['comments'] = comments
		options['expiry'] = expiry
		options['sendmail'] = sendmail
		options['wfconfig'] = workflow.config

		# Connect to NeoCortex and start the task
		neocortex = cortex.lib.core.neocortex_connect()
		task_id = neocortex.create_task(__name__, session['username'], options, description="Creates and sets up a virtual machine (sandbox VMware environment)")

		# Redirect to the status page for the task
		return redirect(url_for('task_status', id=task_id))

################################################################################
## Standard VM Workflow view handler

@workflow.route("standard",title='Create Standard VM', order=10, permission="buildvm.standard", methods=['GET', 'POST'])
def standard():
	# Get the list of clusters
	all_clusters = cortex.lib.core.vmware_list_clusters("srv00080")

	# Exclude any clusters that the config asks to:
	clusters = []
	for cluster in all_clusters:
		if cluster['name'] not in workflow.config['HIDE_CLUSTERS']:
			clusters.append(cluster)

	# Get the list of environments
	environments = cortex.lib.core.get_cmdb_environments()

	if request.method == 'GET':
		## Show form
		return workflow.render_template("standard.html", clusters=clusters, environments=environments, os_names=workflow.config['OS_DISP_NAMES'], os_order=workflow.config['OS_ORDER'], title="Create Standard Virtual Machine")

	elif request.method == 'POST':
		# Ensure we have all parameters that we require
		if 'sockets' not in request.form or 'cores' not in request.form or 'ram' not in request.form or 'disk' not in request.form or 'template' not in request.form or 'cluster' not in request.form or 'environment' not in request.form:
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

			# Validate the data (common between standard / sandbox)
			(sockets, cores, ram, disk, template, env, expiry) = validate_data(request, workflow.config['OS_ORDER'], [e['id'] for e in environments])

			# Validate cluster against the list we've got
			if cluster not in [c['name'] for c in clusters]:
				raise ValueError('Invalid cluster selected')

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
		if 'NOTIFY_EMAILS' in app.config:
			options['notify_emails'] = app.config['NOTIFY_EMAILS']
		else:
			options['notify_emails'] = []

		# Connect to NeoCortex and start the task
		neocortex = cortex.lib.core.neocortex_connect()
		task_id = neocortex.create_task(__name__, session['username'], options, description="Creates and sets up a virtual machine (standard VMware environment)")

		# Redirect to the status page for the task
		return redirect(url_for('task_status', id=task_id))

################################################################################
## Student VM Workflow view handler
@workflow.route("student", title='Create Student VM', order=30, permission="buildvm.student", methods=['GET', 'POST'])
def student():
	# Get the list of clusters
	clusters = cortex.lib.core.vmware_list_clusters("srv00080")

	# Get the list of environments
	environments = cortex.lib.core.get_cmdb_environments()

	if request.method == 'GET':
		# Show form
		return workflow.render_template("student.html", title="Create Virtual Machine", os_names=workflow.config['STU_OS_DISP_NAMES'], os_order=workflow.config['STU_OS_ORDER'])

	elif request.method == 'POST':
		# Ensure we have all parameters that we require
		if not {'template', 'network', 'expiry'}.issubset(request.form):
			flash('You must select options for all questions before creating', 'alert-danger')
			return redirect(url_for('student'))
		
		# Form validation
		try:
			# Extract all the parameters
			host_suffix = request.form['fqdn']
			purpose  = request.form['purpose']
			comments = request.form['comments']
			template = request.form['template']
			network  = request.form['network']
			expiry = request.form['expiry']
			sendmail = 'send_mail' in request.form

			# Check name is RFC1123 complient
			if not re.compile(r"^[a-z0-9\-]{1,32}$").match(host_suffix):
				raise ValueError('Invalid hostname suffix')

			if not re.compile(r"^[a-z0-9\-]{1,16}$").match(session['username']):
				raise Exception('Username contains incompatible characters')

			fqdn = 'svm-' + session['username'] + '-' + host_suffix + '.ecs.soton.ac.uk'

			# load corpus
			corpus = Corpus(g.db, app.config)
			# ensure name is not in use
			if corpus.infoblox_get_host_refs(fqdn) is not None:
				raise ValueError('FQDN "' + fqdn + '" appears to have zone records already. Try a different suffix."')

			if template not in workflow.config['STU_OS_ORDER']:
				raise ValueError('Invalid image selected')

			if network not in workflow.config['STU_NETWORK_ORDER']:
				raise ValueError('Invalid network selected')

			expiry = datetime.datetime.strptime(expiry, '%Y-%m-%d')
			if expiry < datetime.datetime.utcnow():
				raise ValueError('Expiry date cannot be in the past')

		except ValueError as e:
			flash(str(e), 'alert-danger')
			return redirect(url_for('student'))

		except Exception as e:
			flash('Submitted data invalid ' + str(e), 'alert-danger')
			return redirect(url_for('student'))
				
		# Build options to pass to the task
		options = {}
		options['workflow'] = 'student'
		options['sockets'] = 1
		options['cores'] = 4
		options['ram'] = 4
		options['disk'] = 0
		options['template'] = template
		options['network'] = network
		#options['cluster'] = cluster	## Commenting out while we only have one cluster
		options['cluster'] = 'CHARTREUSE'
		options['env'] = 'prod'
		options['fqdn'] = fqdn
		options['purpose'] = purpose
		options['comments'] = comments
		options['expiry'] = expiry
		options['sendmail'] = sendmail
		options['wfconfig'] = workflow.config


		# check if task is running
		try:
			curd = g.db.cursor(mysql.cursors.DictCursor)
			stmt = 'SELECT COUNT(*) AS `count` FROM `tasks` WHERE `username`=%s AND `status`=0'
			params = (session['username'],)
			curd.execute(stmt, params)
			tasks_in_progress = curd.fetchone()['count']
			if tasks_in_progress > 0:
				flash('You already have a task in progress', 'alert-warning')
				abort(400)
			
		except mysql.Error as e:
			flash('An internal error occurred and your request could not be processed', 'alert-warning')
			abort(500)

		# Check if manual approval is required
		## They have too many VMs, the VM is to be public facing or is set to expire in over a year or a neocortex task is running
		# need some way to prevent creation spam where vms are requested faster than they are built
		if cortex.lib.systems.get_system_count(only_allocated_by=session['username']) >= 3 or network == 'external' or expiry > datetime.datetime.utcnow() + datetime.timedelta(days=366):
			try:
				curd = g.db.cursor(mysql.cursors.DictCursor)
				sql = 'INSERT INTO `system_request` (`request_date`, `requested_who`, `fqdn`, `workflow`, `sockets`, `cores`, `ram`, `disk`, `template`, `network`, `cluster`, `environment`, `purpose`, `comments`, `expiry_date`, `sendmail`, `status`, `updated_at`, `updated_who`) VALUES (NOW(), %s, %s ,%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s)'
				params = ( session['username'], options['fqdn'], options['workflow'], options['sockets'], options['cores'], options['ram'], options['disk'], options['template'], options['network'], options['cluster'], options['env'], options['purpose'], options['comments'], options['expiry'], options['sendmail'], 0, session['username'])
				curd.execute(sql, params)

				g.db.commit()

				flash('Your request could not be completed automatically and is awaiting human approval', 'alert-warning')
			except mysql.Error as e:
				flash('An internal error occurred and your request could not be processed', 'alert-warning')

			return redirect(url_for('sysrequests'))

		try:
			curd = g.db.cursor(mysql.cursors.DictCursor)
			sql = 'INSERT INTO `system_request` (`request_date`, `requested_who`, `fqdn`, `workflow`, `sockets`, `cores`, `ram`, `disk`, `template`, `network`, `cluster`, `environment`, `purpose`, `comments`, `expiry_date`, `sendmail`, `status`, `updated_at`, `updated_who`) VALUES (NOW(), %s, %s ,%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s)'
			params = ( session['username'], options['fqdn'], options['workflow'], options['sockets'], options['cores'], options['ram'], options['disk'], options['template'], options['network'], options['cluster'], options['env'], options['purpose'], options['comments'], options['expiry'], options['sendmail'], 2, session['username'])
			curd.execute(sql, params)

			g.db.commit()

			flash('Your request has been automatically approved', 'alert-success')
		except mysql.Error as e:
			flash('An internal error occurred and your request could not be processed', 'alert-warning')

		# Connect to NeoCortex and start the task
		neocortex = cortex.lib.core.neocortex_connect()
		task_id = neocortex.create_task(__name__, session['username'], options, description="Creates and configures a virtual machine")
		# Redirect to the status page for the task
		return redirect(url_for('task_status', id=task_id))



################################################################################
## Common data validation / form extraction

def validate_data(r, templates, envs):
	# Pull data out of request
	sockets  = r.form['sockets']
	cores	 = r.form['cores']
	ram	 = r.form['ram']
	disk	 = r.form['disk']
	template = r.form['template']
	env	 = r.form['environment']

	sockets = int(sockets)
	if not 1 <= sockets <= 16:
		raise ValueError('Invalid number of sockets selected')

	cores = int(cores)
	if not 1 <= cores <= 16:
		raise ValueError('Invalid number of cores per socket selected')

	ram = int(ram)
	if not 2 <= ram <= 32:
		raise ValueError('Invalid amount of RAM selected')
	
	disk = int(disk)
	if not 100 <= disk <= 2000:
		raise ValueError('Invalid disk capacity selected')
	
	if template not in templates:
		raise ValueError('Invalid template selected')
	
	if env not in envs:
		raise ValueError('Invalid environment selected')

	if 'expiry' in r.form and r.form['expiry'] is not None and len(r.form['expiry'].strip()) > 0:
		expiry = r.form['expiry']
		try:
			expiry = datetime.datetime.strptime(expiry, '%Y-%m-%d')
		except Exception, e:
			raise ValueError('Expiry date must be specified in YYYY-MM-DD format')
	else:
		expiry = None

	return (sockets, cores, ram, disk, template, env, expiry)
