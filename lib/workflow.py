import imp
import json
import os
import types
from functools import wraps

import MySQLdb as mysql
from flask import abort, g, render_template

from cortex import app
from cortex.lib.user import (
	does_user_have_permission, does_user_have_system_permission, does_user_have_workflow_permission, login_required)

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
	except Exception:
		# No JSON, assume False
		return {'status': 'Unlocked', 'error': 'Invalid JSON'}

	return jsonobj

def get_workflows_locked():
	"""Determines if workflows are currently locked."""

	jsonobj = get_workflows_locked_details()
	return bool(jsonobj is not None and 'status' in jsonobj and jsonobj['status'] == 'Locked')

def raise_if_workflows_locked():
	"""Raises an Exception if workflows are currently locked."""

	if get_workflows_locked():
		raise Exception("Workflows are currently locked.\nPlease try again later.")

################################################################################

# pylint: disable=no-self-use
class CortexWorkflow:
	config = {}

	def __init__(self, name, load_config=True, check_config=None):
		self.name = name
		self.config = {}

		if 'DISABLED_WORKFLOWS' in app.config and name in app.config['DISABLED_WORKFLOWS']:
			raise Exception('Workflow is disabled in configuration')

		# Load workflow config
		if load_config:
			self._load_workflow_config(app.config['WORKFLOWS_DIR'], check_config=check_config)

		#register the workflow against the app so it can be accessed from cortex
		app.workflows.update({name: self})

	def _load_workflow_config(self, base_dir, check_config):
		"""Load Cortex Workflow config"""

		# Load config from file workflow.conf
		config_file = os.path.join(base_dir, self.name, "workflow.conf")
		if os.path.isfile(config_file):
			self.config.update(self._load_config(config_file))
			app.logger.info("Workflows: Loaded config file workflow.conf for {name}".format(name=self.name))
		else:
			app.logger.debug("Workflows: No config file found for {name}".format(name=self.name))

		# Load config from directory workflow.conf.d
		config_directory = os.path.join(base_dir, self.name, "workflow.conf.d")
		if os.path.isdir(config_directory):
			for config_file in sorted(os.listdir(config_directory)):
				if config_file.endswith(".conf"):
					self.config.update(self._load_config(os.path.join(config_directory, config_file)))
					app.logger.info("Workflows: Loaded config file workflow.conf.d/{f} for {name}".format(f=config_file, name=self.name))

		# Validate the config
		if check_config:
			try:
				# If a dict is given for check_config, then use our _default_validate_config
				# function to validate the configuration items
				if isinstance(check_config, dict):
					if not self._default_validate_config(check_config):
						raise Exception("Workflows: Invalid configuration in workflow {name}".format(name=self.name))
				# If a function is given for check_config, call it:
				elif isinstance(check_config, types.FunctionType):
					if not check_config(self):
						raise Exception("Workflows: Invalid configuration in workflow {name}".format(name=self.name))

			except Exception as ex:
				app.logger.error("Workflows: Invalid workflow configuration in {name}: {ex}".format(name=self.name, ex=ex))

				# Re-raise to stop the workflow from loading
				raise ex

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
					if not isinstance(self.config[item], required_config[item]):
						app.logger.error("Workflows: Configuration item '" + str(item) + "' in workflow '" + self.name + "' is of incorrect type '" + type(self.config[item]).__name__ + "' - should be '" + required_config[item].__name__ + "'")
						valid_config = False

		return valid_config

	def _load_config(self, filename):
		"""Extracts the settings from the given config file."""

		# Start a new module, which will be the context for parsing the config
		# pylint: disable=invalid-name
		d = imp.new_module('config')
		d.__file__ = filename

		# Read the contents of the configuration file and execute it as a
		# Python script within the context of a new module
		with open(filename) as config_file:
			# pylint: disable=exec-used
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

		app.permissions.add_workflow_permission(name, desc)
		app.logger.info("Workflows: Added permission '" + name + "'")

	def add_system_permission(self, name, desc):
		app.permissions.add_system_permission(name, desc)
		app.logger.info("Workflows: Added per-system permission '" + name + "'")

	def render_template(self, template_name, **kwargs):
		# set the 'active' variable to 'workflows' so the nav bar highlights
		# workflows as the active part of the navigation bar
		kwargs['active'] = 'workflows'
		return render_template(self.name + "::" + template_name, **kwargs)

	def route(self, rule, title="Untitled", order=999, permission="cortex.admin", menu=True, require_login=True, **options):

		if isinstance(permission, str) and not permission.startswith("workflows."):
			permission = "workflows." + permission

		def decorator(func):

			## Require permissions
			if permission and callable(permission):
				permfn = self._require_permission_callable(permission)
				func = permfn(func)
			elif permission:
				permfn = self._require_permission(permission)
				func = permfn(func)

			## Require login, and the right permissions
			## Note this must come after the decoration by _require_permission
			## as the decorators are essentially processed backwards
			if require_login:
				func = login_required(func)

			## Raise an exception if the workflows are locked.
			func = self._raise_if_workflows_locked(func)

			## Mark the view function as a workflow view function
			func = self._mark_as_workflow(func)

			# Get the endpoint, if any
			endpoint = options.pop('endpoint', None)

			# Add a URL rule
			app.add_url_rule("/workflows/" + self.name + "/" + rule, endpoint, func, **options)

			# Store the workflow route details in a hash for the
			app.wf_functions.append({
				'title':      title,
				'name':       func.__name__,
				'workflow':   self.name,
				'order':      order,
				'permission': permission,
				'menu':       menu,
			})

			app.logger.info("Workflows: Registered a new workflow function '" + func.__name__ + "' in '" + self.name + "'")

			return func

		return decorator

	def action(self, rule, title="Untitled", desc="N/A", order=999, system_permission=None, permission="cortex.admin", menu=True, require_vm=False, **options):
		def decorator(func):

			## Require a permission, if set
			if system_permission is not None:
				permfn = self._require_system_permission(system_permission, permission)
				func = permfn(func)

			## Require login, and the right permissions
			func = login_required(func)

			## Raise an exception if the workflows are locked.
			func = self._raise_if_workflows_locked(func)

			## Mark the view function as a workflow view function
			func = self._mark_as_workflow(func)

			# Get the endpoint, if any
			endpoint = options.pop('endpoint', None)

			# Add a URL rule
			app.add_url_rule("/sysactions/" + self.name + "/" + rule + "/<int:target_id>", endpoint, func, **options)

			# Store the workflow route details in a hash
			app.wf_system_functions.append({
				'title':             title,
				'name':              func.__name__,
				'workflow':          self.name,
				'order':             order,
				'system_permission': system_permission,
				'permission':        permission,
				'desc':              desc,
				'menu':              menu,
				'require_vm':        require_vm,
			})

			app.logger.info("Workflows: Registered a new per-system function '" + func.__name__ + "' in '" + self.name + "'")

			return func

		return decorator

	def _require_permission(self, permission):
		def decorator(func):
			@wraps(func)
			def decorated_function(*args, **kwargs):
				if not does_user_have_workflow_permission(permission):
					abort(403)
				return func(*args, **kwargs)
			return decorated_function
		return decorator

	def _require_permission_callable(self, permission_callable):
		def decorator(func):
			@wraps(func)
			def decorated_function(*args, **kwargs):
				if not callable(permission_callable):
					abort(403)
				result = permission_callable()
				if not isinstance(result, bool) or not result:
					abort(403)

				return func(*args, **kwargs)
			return decorated_function
		return decorator

	def _require_system_permission(self, system_permission, permission=None):
		def decorator(func):
			@wraps(func)
			def decorated_function(*args, **kwargs):
				system_id = kwargs['target_id']

				## Grant permission ONLY if
				### they have workflows.all
				### they have the per-system permission set in the workflow action
				### they have the global permission set in the workflow action

				if permission is None:
					if not does_user_have_system_permission(system_id, system_permission) and not does_user_have_permission("workflows.all"):
						abort(403)

				else:
					if not does_user_have_system_permission(system_id, system_permission) and not does_user_have_permission("workflows." + permission) and not does_user_have_permission("workflows.all"):
						abort(403)

				return func(*args, **kwargs)
			return decorated_function
		return decorator

	def _raise_if_workflows_locked(self, func):
		@wraps(func)
		def decorated_function(*args, **kwargs):
			# If the workflows are locked raise an exception.
			raise_if_workflows_locked()
			return func(*args, **kwargs)
		return decorated_function


	def _mark_as_workflow(self, func):
		@wraps(func)
		def decorated_function(*args, **kwargs):
			g.workflow = True
			return func(*args, **kwargs)
		return decorated_function
