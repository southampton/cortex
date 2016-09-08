import os
import imp
from cortex import app
from flask import render_template, abort
from cortex.lib.user import login_required, does_user_have_workflow_permission, does_user_have_permission, does_user_have_system_permission
from functools import wraps

################################################################################

class CortexWorkflow:
	config = {}

	def __init__(self, name):
		self.name = name

		# Load settings for this workflow
		cfgfile = os.path.join(app.config['WORKFLOWS_DIR'], self.name, "workflow.conf") 
		if os.path.isfile(cfgfile):
			try:
				self.config = self._load_config(cfgfile)
				app.logger.info("Workflows: Loaded config file for '" + self.name + "'")
			except Exception as ex:
				app.logger.warn("Workflows: Could not load config file " + cfgfile + ": " + str(ex))
		else:
			app.logger.debug("Workflows: No config file found for '" + self.name + "'")

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

	def route(self, rule, title="Untitled", order=999, permission=None, menu=True, **options):
		if not permission.startswith("workflows."):
			permission = "workflows." + permission

		def decorator(fn):
			## Require login, and the right permissions
			fn = login_required(fn)
			if permission is not None:
				permfn = self._require_permission(permission)
				fn = permfn(fn)

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

	def action(self, rule, title="Untitled", desc="N/A", order=999, system_permission=None, permission=None, menu=True, **options):
		def decorator(fn):
			## Require login, and the right permissions
			fn = login_required(fn)
			if system_permission is not None:
				permfn = self._require_system_permission(system_permission,permission)
				fn = permfn(fn)

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
					if not does_user_have_system_permission(id,system_permission) and not does_user_have_permission(permission) and not does_user_have_permission("workflows.all"):
						abort(403)
				return fn(*args, **kwargs)
			return decorated_function
		return decorator
