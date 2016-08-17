from cortex import app
from cortex.lib.errors import logerr, fatalerr
from cortex.lib.user import does_user_have_permission, can_user_access_workflow
from flask import Flask, request, session, g, abort, render_template, url_for
import redis
import time
import traceback
import MySQLdb as mysql

################################################################################

@app.before_request
def before_request():
	"""This function is run before the request is handled by Flask. It is used
	to connect to MySQL and Redis, and to tell old Internet Explorer versions
	to go away.
	"""

	# Check for MSIE version <= 10.0
	if (request.user_agent.browser == "msie" and int(round(float(request.user_agent.version))) <= 10):
		return render_template('foad.html')

	# Connect to redis
	try:
		g.redis = redis.StrictRedis(host=app.config['REDIS_HOST'], port=app.config['REDIS_PORT'], db=0)
		g.redis.get('foo') # it doesnt matter that this key doesnt exist, its just to force a test call to redis.
	except Exception as ex:
		logerr()
		return fatalerr(message='Cortex could not connect to the REDIS server')

	# Connect to database
	try:
		g.db = mysql.connect(host=app.config['MYSQL_HOST'], port=app.config['MYSQL_PORT'], user=app.config['MYSQL_USER'], passwd=app.config['MYSQL_PASS'], db=app.config['MYSQL_NAME'], charset="utf8")
	except Exception as ex:
		logerr()
		return fatalerr(message='Cortex could not connect to the MariaDB server')

	# This would ideally go in app.py, but it can't as it depends on 
	# cortex.lib.user which it can't import due to a cyclic dependency
	app.jinja_env.globals['does_user_have_permission'] = does_user_have_permission
	app.jinja_env.globals['can_user_access_workflow'] = can_user_access_workflow

################################################################################

@app.context_processor
def context_processor():
	"""This function is called on every page load. It injects a 'workflows'
	variable in to every render_template call, which is used to populate the
	Workflows menu on the page. It also injects the list of menu items
	and the items in the menus."""

	# We return a dictionary with each key being a variable to set
	# within the template.
	injectdata = dict()

	# Inject the workflows variable which is a list of loaded workflows. We
	# filter this to just the ones the user is allowed to use. Note that we
	# use 'view_func' rather than 'name' here as we can have many workflows
	# inside a single workflow module, e.g. buildvm which does standard and
	# sandbox VMs.
	injectdata['workflows'] = []
	for workflow in app.workflows:
		if can_user_access_workflow(workflow['view_func']):
			injectdata['workflows'].append(workflow)

	# Inject the menu items 
	# systems, workflows, vmware, puppet, admin

	# Set up the Systems menu, based on a single permission
	systems = []
	if does_user_have_permission("systems.view"):
		systems = [
			{'link': url_for('systems'), 'title': 'Systems list', 'icon': 'fa-list'},
			{'link': url_for('systems_nocmdb'), 'title': 'VMs missing CMBD record', 'icon': 'fa-list'},
			{'link': url_for('systems_expired'), 'title': 'Expired systems list', 'icon': 'fa-list'}
		]

	# Set up the VMware menu, based on a single permission
	vmware = []
	if does_user_have_permission("vmware.view"):
		vmware = [
			{'link': url_for('vmware_os'), 'title': 'Operating systems', 'icon': 'fa-pie-chart'},
			{'link': url_for('vmware_hwtools'), 'title': 'Hardware & tools', 'icon': 'fa-pie-chart'},
			{'link': url_for('vmware_specs'), 'title': 'RAM & CPU', 'icon': 'fa-pie-chart'},
			{'link': url_for('vmware_clusters'), 'title': 'Clusters', 'icon': 'fa-cubes'},
			{'link': url_for('vmware_data'), 'title': 'VM data', 'icon': 'fa-th'},
			{'link': url_for('vmware_data_unlinked'), 'title': 'Unlinked VMs', 'icon': 'fa-frown-o'},
			{'link': url_for('vmware_history'), 'title': 'History', 'icon': 'fa-line-chart'}
		]

	# Set up the Puppet menu, based on permissions
	puppet = []
	if does_user_have_permission("puppet.dashboard.view"):
		puppet.append({'link': url_for('puppet_dashboard'), 'title': 'Dashboard', 'icon': 'fa-dashboard'})
	if does_user_have_permission("puppet.nodes.view"):
		puppet.append({'link': url_for('puppet_nodes'), 'title': 'Nodes', 'icon': 'fa-server'})
	if does_user_have_permission("puppet.groups.view"):
		puppet.append({'link': url_for('puppet_groups'), 'title': 'Groups', 'icon': 'fa-object-group'})
	if does_user_have_permission("puppet.default_classes.view"):
		puppet.append({'link': url_for('puppet_enc_default'), 'title': 'Default classes', 'icon': 'fa-globe'})
	if does_user_have_permission("puppet.dashboard.view"):
		puppet.append({'link': url_for('puppet_radiator'), 'title': 'Radiator view', 'icon': 'fa-desktop'})

	# Set up the Admin menu, based on permissions
	admin = []
	if does_user_have_permission("classes.view"):
		admin.append({'link': url_for('admin_classes'), 'title': 'Classes', 'icon': 'fa-table'})
	if does_user_have_permission("tasks.view"):
		admin.append({'link': url_for('admin_tasks'), 'title': 'Tasks', 'icon': 'fa-tasks'})
	if does_user_have_permission(["maintenance.vmware", "maintenance.cmdb", "maintenance.expire_vm"]):
		admin.append({'link': url_for('admin_maint'), 'title': 'Maintenance', 'icon': 'fa-gears'})
	if does_user_have_permission("systems.allocate_name"):
		admin.append({'link': url_for('systems_new'), 'title': 'Allocate system name', 'icon': 'fa-plus'})
	if does_user_have_permission("systems.add_existing"):
		admin.append({'link': url_for('systems_add_existing'), 'title': 'Add existing system', 'icon': 'fa-plus'})

	injectdata['menu'] = { 'systems': systems, 'vmware': vmware, 'puppet': puppet, 'admin': admin }

	# If the current request is for a page that is a workflow, set the
	# value of the 'active' variable that's passed to the page templates
	# to say it's a workflow (this allows the navigation bar to work)
	for workflow in app.workflows:
		if workflow['view_func'] == request.endpoint:
			injectdata['active'] = 'workflows'
			break

	return injectdata
