
from flask import abort, flash, redirect, request, session, url_for

import cortex.lib.classes
import cortex.lib.core
import cortex.views
from cortex.lib.workflow import CortexWorkflow

workflow = CortexWorkflow(__name__)
workflow.add_permission('newserver', 'Create System Record')

@workflow.route("create", title='Create System Record', order=30, permission="newserver", methods=['GET', 'POST'])
def allocateserver():

	# Get the list of enabled classes
	classes = cortex.lib.classes.get_list(hide_disabled=True)

	# Extract the classes the have servers in (so hide storage and switches, for example)
	server_classes = [c for c in classes if c['cmdb_type'] == "cmdb_ci_server"]

	# Get the list of environments
	environments = cortex.lib.core.get_cmdb_environments()

	# Get the list of networks
	networks = workflow.config['NETWORKS']

	# Get the list of operating systems
	oses = workflow.config['OPERATING_SYSTEMS']

	# Get the list of domains
	domains = workflow.config['DOMAINS']

	if request.method == 'POST':
		if not all(field in request.form for field in ['purpose', 'comments', 'class', 'os', 'environment', 'network', 'domain']):
			flash('You must select options for all questions before allocating', 'alert-danger')
			return redirect(url_for('allocateserver'))

		# Extract all the parameters
		classname = request.form['class']
		os = request.form['os']
		env = request.form['environment']
		network = request.form['network']
		purpose = request.form['purpose']
		comments = request.form['comments']
		domain = request.form['domain']
		alloc_ip = 'alloc_ip' in request.form
		is_virtual = 'is_virtual' in request.form
		set_backup = 1 if 'set_backup' in request.form else 0
		task = None

		# Extract task if we've got it
		if 'task' in request.form and len(request.form['task'].strip()) > 0:
			task = request.form['task'].strip()

		# Validate class name against the list of classes
		if classname not in [c['name'] for c in classes]:
			abort(400)

		# Validate operating system
		if os not in [o['id'] for o in oses]:
			abort(400)

		# Validate environment
		if env not in [e['id'] for e in environments]:
			abort(400)

		# Validate networking (if we're allocating an IP)
		if alloc_ip:
			if network not in [n['id'] for n in networks]:
				abort(400)
			if domain not in domains:
				abort(400)

		# Populate options
		options = {}
		options['classname'] = classname
		options['purpose'] = purpose
		options['env'] = env
		options['comments'] = comments
		options['alloc_ip'] = alloc_ip
		options['is_virtual'] = is_virtual
		options['set_backup'] = set_backup
		options['task'] = task
		options['wfconfig'] = workflow.config

		# Populate networking options
		if alloc_ip:
			# Domain
			options['domain'] = domain

			# Get subnet from network ID
			for net in networks:
				if net['id'] == network:
					options['network'] = net['subnet']

		# Populate OS type id
		for iter_os in oses:
			if iter_os['id'] == os:
				options['os_type'] = iter_os['type_id']

		## Connect to NeoCortex and start the task
		neocortex = cortex.lib.core.neocortex_connect()
		task_id = neocortex.create_task(__name__, session['username'], options, description="Allocate a hostname, IP address and create a CI entry")

		## Redirect to the status page for the task
		return redirect(url_for('task_status', id=task_id))

	## Show form
	return workflow.render_template("create.html", title="Create System Record", classes=server_classes, default_class=workflow.config['DEFAULT_CLASS'], environments=environments, networks=networks, default_network=workflow.config['DEFAULT_NETWORK_ID'], oses=oses, domains=domains, default_domain=workflow.config['DEFAULT_DOMAIN'])
