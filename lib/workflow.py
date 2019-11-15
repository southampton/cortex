import os, imp, types, json
from cortex import app
from flask import render_template, abort, g
from cortex.lib.user import login_required, does_user_have_workflow_permission, does_user_have_permission, does_user_have_system_permission
from functools import wraps
import MySQLdb as mysql

################################################################################

def get_workflows_locked_details():
	"""Gets the details about workflow locking."""

	# Check if workflows are currently locked 
	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute('SELECT `value` FROM `kv_settings` WHERE `key` = "workflow_lock_status";')
	current_value = curd.fetchone()

	# If we didn't get a row, then we can't be locked
	if current_value is None:
		return {'status': 'Unlocked', 'error': 'No data'}

	# Parse the JSON
	try:
		jsonobj = json.loads(current_value['value'])
	except Exception as e:
		# No JSON, assume False
		return {'status': 'Unlocked', 'error': 'Invalid JSON'}

	return jsonobj

def get_workflows_locked():
	"""Determines if workflows are currently locked."""

	jsonobj = get_workflows_locked_details()

	if jsonobj is not None and 'status' in jsonobj and jsonobj['status'] == 'Locked':
		return True
	else:
		return False

def raise_if_workflows_locked():
	"""Raises an Exception if workflows are currently locked."""

	if get_workflows_locked():
		raise Exception("Workflows are currently locked.\nPlease try again later.")

################################################################################

class CortexWorkflow(object):
	config = {}

	def __init__(self, name, load_config=True, check_config=None):
		self.name = name
		self.config = {}

		if 'DISABLED_WORKFLOWS' in app.config and name in app.config['DISABLED_WORKFLOWS']:
			raise Exception('Workflow is disabled in configuration')

		if load_config:
			# Load settings for this workflow
			cfgfile = os.path.join(app.config['WORKFLOWS_DIR'], self.name, "workflow.conf") 
			if os.path.isfile(cfgfile):
				try:
					self.config = self._load_config(cfgfile)
					app.logger.info("Workflows: Loaded config file for '" + self.name + "'")

					# Validate the config
					if check_config is not None:
						# If a dict is given for check_config, then use our _default_validate_config
						# function to validate the configuration items
						if type(check_config) is dict:
							if not self._default_validate_config(check_config):
								raise Exception("Workflows: Invalid configuration in workflow '" + self.name + "'")
						# If a function is given for check_config, call it:
						elif type(check_config) is types.FunctionType:
							if not check_config(self):
								raise Exception("Workflows: Invalid configuration in workflow '" + self.name + "'")

				except Exception as ex:
					app.logger.error("Workflows: Could not load config file " + cfgfile + ": " + str(ex))

					# Re-raise to stop the workflow from loading
					raise(ex)

			else:
				app.logger.debug("Workflows: No config file found for '" + self.name + "'")

		#register the workflow against the app so it can be accessed from cortex
		app.workflows.update({name: self})

	def _default_validate_config(self, required_config):
		valid_config = True

		for item in required_config:
			# Make sure we have the item
			if item not in self.config:
				app.logger.error("Workflows: Missing required configuration item '" + str(item) + "' for workflow '" + self.name + "'")
				valid_config = False
			else:
				# Check the type of the item matches what we expect
				if required_config[item] is not None:
					if type(self.config[item]) is not required_config[item]:
						app.logger.error("Workflows: Configuration item '" + str(item) + "' in workflow '" + self.name + "' is of incorrect type '" + type(self.config[item]).__name__ + "' - should be '" + required_config[item].__name__ + "'")
						valid_config = False

		return valid_config

	def _load_config(self, filename): 
		"""Extracts the settings from the given config file."""

		# Start a new module, which will be the context for parsing the config
		d = imp.new_module('config')
		d.__file__ = filename

		# Read the contents of the configuration file and execute it as a
		# Python script within the context of a new module
		with open(filename) as config_file:
			exec(compile(config_file.read(), filename, 'exec'), d.__dict__)

		# Extract the config options, which are those variables whose names are
		# entirely in uppercase
		new_config = {}
		for key in dir(d):
			if key.isupper():
				new_config[key] = getattr(d, key)

		return new_config

	def add_permission(self, name, desc):
		if not name.startswith("workflows."):
			name = "workflows." + name

		app.workflow_permissions.append({'name': name, 'desc': desc})
		app.logger.info("Workflows: Added permission '" + name + "'")

	def add_system_permission(self, name, desc):
		app.system_permissions.append({'name': name, 'desc': desc})
		app.logger.info("Workflows: Added per-system permission '" + name + "'")

	def render_template(self, template_name, **kwargs):
		# set the 'active' variable to 'workflows' so the nav bar highlights
		# workflows as the active part of the navigation bar
		kwargs['active'] = 'workflows'
		return render_template(self.name + "::" + template_name,**kwargs)

	def route(self, rule, title="Untitled", order=999, permission="cortex.admin", menu=True, require_login=True, **options):
		if permission is not None and not permission.startswith("workflows."):
			permission = "workflows." + permission

		def decorator(fn):

			## Require permissions
			if permission is not None:
				permfn = self._require_permission(permission)
				fn = permfn(fn)

			## Require login, and the right permissions
			## Note this must come after the decoration by _require_permission
			## as the decorators are essentially processed backwards
			if require_login:
				fn = login_required(fn)

			## Raise an exception if the workflows are locked.
			fn = self._raise_if_workflows_locked(fn)

			## Mark the view function as a workflow view function
			fn = self._mark_as_workflow(fn)

			# Get the endpoint, if any
			endpoint = options.pop('endpoint', None)

			# Add a URL rule
			app.add_url_rule("/workflows/" + self.name + "/" + rule, endpoint, fn, **options)

			# Store the workflow route details in a hash for the
			app.wf_functions.append({
				'title':      title, 
				'name':       fn.__name__,
				'workflow':   self.name, 
				'order':      order,
				'permission': permission, 
				'menu':       menu,
			})

			app.logger.info("Workflows: Registered a new workflow function '" + fn.__name__ + "' in '" + self.name + "'")

			return fn

		return decorator

	def action(self, rule, title="Untitled", desc="N/A", order=999, system_permission=None, permission="cortex.admin", menu=True, require_vm=False, **options):
		def decorator(fn):

			## Require a permission, if set
			if system_permission is not None:
				permfn = self._require_system_permission(system_permission,permission)
				fn = permfn(fn)

			## Require login, and the right permissions
			fn = login_required(fn)

			## Raise an exception if the workflows are locked.
			fn = self._raise_if_workflows_locked(fn)

			## Mark the view function as a workflow view function
			fn = self._mark_as_workflow(fn)

			# Get the endpoint, if any
			endpoint = options.pop('endpoint', None)

			# Add a URL rule
			app.add_url_rule("/sysactions/" + self.name + "/" + rule + "/<int:id>", endpoint, fn, **options)

			# Store the workflow route details in a hash
			app.wf_system_functions.append({
				'title':             title, 
				'name':              fn.__name__,
				'workflow':          self.name, 
				'order':             order,
				'system_permission': system_permission,
				'permission':        permission,
				'desc':              desc,
				'menu':              menu,
				'require_vm':        require_vm,
			})

			app.logger.info("Workflows: Registered a new per-system function '" + fn.__name__ + "' in '" + self.name + "'")

			return fn

		return decorator

	def _require_permission(self,permission):
		def decorator(fn):
			@wraps(fn)
			def decorated_function(*args, **kwargs):
				if not does_user_have_workflow_permission(permission):
					abort(403)
				return fn(*args, **kwargs)
			return decorated_function
		return decorator


	def _require_system_permission(self,system_permission,permission=None):
		def decorator(fn):
			@wraps(fn)
			def decorated_function(*args, **kwargs):
				id = kwargs['id']

				## Grant permission ONLY if
				### they have workflows.all
				### they have the per-system permission set in the workflow action
				### they have the global permission set in the workflow action

				if permission is None:
					if not does_user_have_system_permission(id,system_permission) and not does_user_have_permission("workflows.all"):
						abort(403)

				else:
					if not does_user_have_system_permission(id,system_permission) and not does_user_have_permission("workflows." + permission) and not does_user_have_permission("workflows.all"):
						abort(403)

				return fn(*args, **kwargs)
			return decorated_function
		return decorator

	def _raise_if_workflows_locked(self, f):
		@wraps(f)
		def decorated_function(*args, **kwargs):
			# If the workflows are locked raise an exception.
			raise_if_workflows_locked()
			return f(*args, **kwargs)
		return decorated_function


	def _mark_as_workflow(self,f):
		@wraps(f)
		def decorated_function(*args, **kwargs):
			g.workflow = True
			return f(*args, **kwargs)
		return decorated_function
