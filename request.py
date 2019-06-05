from cortex import app
from cortex.lib.errors import logerr, fatalerr
from cortex.lib.user import does_user_have_permission, does_user_have_workflow_permission, does_user_have_system_permission
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
	app.jinja_env.globals['does_user_have_system_permission'] = does_user_have_system_permission

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
	# filter this to just the ones the user is allowed to use.
	injectdata['workflows'] = []
	for fn in app.wf_functions:
		if fn['menu']:
			if does_user_have_workflow_permission(fn['permission']):
				injectdata['workflows'].append(fn)

	# Inject the menu items 

	# Favourites menu
	favourites = []
	if does_user_have_permission("systems.own.view") or does_user_have_permission("systems.all.view"):
		favourites = [{'link': url_for('favourites'), 'title': 'All Favourites', 'icon': 'fa-star'},
		{'link': url_for('favourites_by_type', system_type='srv'), 'title': 'Favourited srv systems', 'icon': 'fa-star'},
		{'link': url_for('favourites_by_type', system_type='play'), 'title': 'Favourited play systems', 'icon': 'fa-star'},
	]

	# Set up the Systems menu, based on a single permission
	systems = []
	if does_user_have_permission("systems.own.view") or does_user_have_permission("systems.all.view"):
		systems.append({'link': url_for('systems'), 'title': 'All systems', 'icon': 'fa-list'})

	if does_user_have_permission("systems.all.view"):
		systems.append({'link': url_for('systems_nocmdb'), 'title': 'Systems without a CMBD record', 'icon': 'fa-list'})
		systems.append({'link': url_for('systems_expired'), 'title': 'Expired systems', 'icon': 'fa-list'})
	if does_user_have_permission("sysrequests.own.view") or does_user_have_permission("sysrequests.all.view"):
		systems.append({'link': url_for('sysrequests'), 'title': 'System requests', 'icon': 'fa-list'})

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
	if does_user_have_permission("puppet.default_classes.view"):
		puppet.append({'link': url_for('puppet_enc_default'), 'title': 'Default classes', 'icon': 'fa-globe'})
	if does_user_have_permission("puppet.dashboard.view"):
		puppet.append({'link': url_for('puppet_radiator'), 'title': 'Radiator view', 'icon': 'fa-desktop'})
	if does_user_have_permission("puppet.nodes.view"):
		puppet.append({'link': '*puppet_search', 'title': 'Configuration search', 'icon': 'fa-search'})

	# Set up the certificates menu, based on permissions
	certificates = []
	if does_user_have_permission("certificates.view"):
		certificates.append({'link': url_for('certificates'), 'title': 'Certificates', 'icon': 'fa-certificate'})
	if does_user_have_permission("certificates.stats"):
		certificates.append({'link': url_for('certificate_statistics'), 'title': 'Statistics', 'icon': 'fa-pie-chart'})

	# Set up the Admin menu, based on permissions
	admin = []
	if does_user_have_permission("classes.view"):
		admin.append({'link': url_for('admin_classes'), 'title': 'Classes', 'icon': 'fa-table'})
	if does_user_have_permission("tasks.view"):
		admin.append({'link': url_for('admin_tasks'), 'title': 'Tasks', 'icon': 'fa-tasks'})
	if does_user_have_permission("events.view"):
		admin.append({'link': url_for('admin_events'), 'title': 'Events', 'icon': 'fa-list-alt'})
	if does_user_have_permission("specs.view"):
		admin.append({'link': url_for('admin_specs'), 'title': 'VM Specs', 'icon': 'fa-sliders'})
	if does_user_have_permission(["maintenance.vmware", "maintenance.cmdb", "maintenance.expire_vm", "maintenance.sync_puppet_servicenow", "maintenance.cert_scan"]):
		admin.append({'link': url_for('admin_maint'), 'title': 'Maintenance', 'icon': 'fa-gears'})
	if does_user_have_permission("systems.allocate_name"):
		admin.append({'link': url_for('systems_new'), 'title': 'Allocate system name', 'icon': 'fa-plus'})
	if does_user_have_permission("systems.add_existing"):
		admin.append({'link': url_for('systems_add_existing'), 'title': 'Add existing system', 'icon': 'fa-plus'})

	# Sets up the permissions menu
	perms = []
	if does_user_have_permission("admin.permissions"):
		perms.append({'link': url_for('perms_roles'), 'title': 'Permission Roles', 'icon': 'fa-user-secret'})
		perms.append({'link': url_for('system_perms_roles'), 'title': 'System Permission Roles', 'icon': 'fa-user-secret'})
		perms.append({'link': url_for('systems_withperms'), 'title': 'Systems with permissions', 'icon': 'fa-list'})

	# Set injectdata default options.
	injectdata['menu'] = { 'systems': systems, 'favourites': favourites, 'vmware': vmware, 'puppet': puppet, 'certificates': certificates, 'admin': admin, 'perms': perms }
	injectdata['classic_layout'] = False
	injectdata['sidebar_expand'] = False

	if 'username' in session:

		# Determine the layout mode for the user
		try:
			if g.redis.get('user:' + session['username'] + ":preferences:interface:layout") == "classic":
				injectdata['classic_layout'] = True
		except Exception as ex:
			pass

		# Determine theme for the user
		try:
			if g.redis.get('user:' + session['username'] + ":preferences:interface:theme") == "dark":
				injectdata['theme'] = "dark"
		except Exception as ex:
			pass

		# Determine whether to expand sidebar.
		try:
			if g.redis.get('user:' + session['username'] + ':preferences:interface:sidebar') == 'expand':
				injectdata['sidebar_expand'] = True
		except Exception as ex:
			pass

	# Add the banner message.
	try:
		injectdata['banner_message'] = app.config['BANNER_MESSAGE']
	except KeyError:
		pass

	return injectdata
