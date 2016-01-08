#!/usr/bin/python
from flask import Flask, request, session, abort
import jinja2 
import os.path
from os import walk
import imp
import random                 ## used in pwgen            
import string                 ## used in pwgen

class CortexFlask(Flask):

	workflows = []

	################################################################################

	def __init__(self,name):
		super(CortexFlask, self).__init__(name)
		self._exempt_views = set()
		self.before_request(self._csrf_protect)
		self.jinja_env.globals['csrf_token'] = self._generate_csrf_token

	################################################################################

	def pwgen(self, length=16):
		"""This is very crude password generator. It is currently only used to generate
		a CSRF token.
		"""

		urandom = random.SystemRandom()
		alphabet = string.ascii_letters + string.digits
		return str().join(urandom.choice(alphabet) for _ in range(length))

################################################################################

	def _generate_csrf_token(self):
		"""This function is used to generate a CSRF token for use in templates."""

		if '_csrf_token' not in session:
			session['_csrf_token'] = self.pwgen(32)

		return session['_csrf_token']

	################################################################################

	def _csrf_protect(self):
		"""Performs the checking of CSRF tokens. This check is skipped for the 
		GET, HEAD, OPTIONS and TRACE methods within HTTP, and is also skipped
		for any function that has been added to _exempt_views by use of the
		disable_csrf_check decorator."""

		# For methods that require CSRF checking
		if request.method not in ('GET', 'HEAD', 'OPTIONS', 'TRACE'):
			# Get the function that is rendering the current view
			view = self.view_functions.get(request.endpoint)
			view_location = view.__module__ + '.' + view.__name__

			# If the view is not exempt
			if not view_location in self._exempt_views:
				token = session.get('_csrf_token')
				if not token or token != request.form.get('_csrf_token'):
					if 'username' in session:
						self.logger.warning('CSRF protection alert: %s failed to present a valid POST token', session['username'])
					else:
			 			self.logger.warning('CSRF protection alert: a non-logged in user failed to present a valid POST token')

					### the user should not have accidentally triggered this
					### so just throw a 400
					abort(400)
			else:
				self.logger.debug('View ' + view_location + ' is exempt from CSRF checks')

	################################################################################

	def disable_csrf_check(self, view):
		"""A decorator that can be used to exclude a view from CSRF validation.
		Example usage of disable_csrf_check might look something like this:
			@app.disable_csrf_check
			@app.route('/some_view')
			def some_view():
				return render_template('some_view.html')
		:param view: The view to be wrapped by the decorator.
		"""

		view_location = view.__module__ + '.' + view.__name__
		self._exempt_views.add(view_location)
		self.logger.debug('Added CSRF check exemption for ' + view_location)
		return view

	################################################################################

	def _load_workflow_settings(self, filename): 
		d = imp.new_module('config')
		d.__file__ = filename

		with open(filename) as config_file:
			exec(compile(config_file.read(), filename, 'exec'), d.__dict__)

		new_config = {}
		for key in dir(d):
			if key.isupper():
				new_config[key] = getattr(d, key)

		return new_config

	################################################################################

	def load_workflows(self):
		"""Attempts to load the workflow config files from the workflows directory
		which is defined in app.config['WORKFLOWS_DIR']. Each config file is loaded
		and the display name stored"""

		## where to store workflow settings
		self.wfsettings = {}

		## list all entries in the directory
		if not os.path.isdir(self.config['WORKFLOWS_DIR']):
			self.logger.error("The config option WORKFLOWS_DIR is not a directory!")
			return

		entries = os.listdir(self.config['WORKFLOWS_DIR'])
		found = False
		for entry in entries:
			if entry.startswith('.'):
				continue

			fqp = os.path.join(self.config['WORKFLOWS_DIR'],entry)

			if os.path.isdir(fqp):
				## this is or rather should be a workflow directory
				found = True
				views_file = os.path.join(fqp,"views.py")
				try:
					view_module = imp.load_source(entry, views_file)
					self.logger.info("Loaded workflow '" + entry + "' views module")
				except Exception as ex:
					self.logger.warn("Could not load workflow from file " + views_file + ": " + str(ex))
					continue

				## Load settings for this workflow if they exist ( settings files are optional )
				settings_file = os.path.join(fqp,"workflow.conf")
				if os.path.isfile(settings_file):
					try:
						self.wfsettings[entry] = self._load_workflow_settings(settings_file)
						self.logger.info("Loaded workflow '" + entry + "' config file")
					except Exception as ex:
						self.logger.warn("Could not load workflow config file " + settings_file + ": " + str(ex))
						continue

		if not found:
			self.logger.warn("The WORKFLOWS_DIR directory is empty, no workflows could be loaded!")

		## set up template loading
		loader_data = {}
		for workflow in self.workflows:
			template_dir = os.path.join(self.config['WORKFLOWS_DIR'],workflow['name'],'templates')
			loader_data[workflow['name']] = jinja2.FileSystemLoader(template_dir)

		choice_loader = jinja2.ChoiceLoader(
		[
			self.jinja_loader,
			jinja2.PrefixLoader(loader_data,'::')
		])
		self.jinja_loader = choice_loader

	################################################################################
		
	def workflow_handler(self, workflow_name, workflow_title, **options):
		"""This is a decorator function that is used in workflows to add the principal view function
		into the app. It performs the function of Flask's @app.route but also adds the view function
		to a menu on the website to allow the workflow to be activated by the user.

		Usage is as such: @app.workflow_handler(__name__,"Title on menu", methods=['GET','POST'])

		:param workflow_name: the name of the workflow. This should always be __name__.
		:param workflow_title: the name of the workflow. This should always be __name__.
		:param options: the options to be forwarded to the underlying
			     :class:`~werkzeug.routing.Rule` object.  A change
			     to Werkzeug is handling of method options.  methods
			     is a list of methods this rule should be limited
			     to (``GET``, ``POST`` etc.).  By default a rule
			     just listens for ``GET`` (and implicitly ``HEAD``).
			     Starting with Flask 0.6, ``OPTIONS`` is implicitly
			     added and handled by the standard request handling.
		"""

		def decorator(f):
			rule = "/workflows/" + workflow_name
			endpoint = options.pop('endpoint', None)
			self.add_url_rule(rule, endpoint, f, **options)
			self.workflows.append({'display': workflow_title, 'name': workflow_name, 'view_func': f.__name__ })
			return f
		return decorator

	################################################################################

	def log_exception(self, exc_info):
		"""Logs an exception.  This is called by :meth:`handle_exception`
		if debugging is disabled and right before the handler is called.
		This implementation logs the exception as an error on the
		:attr:`logger` but sends extra information such as the remote IP
		address, the username, etc. This extends the default implementation
		in Flask.

		"""

		if 'username' in session:
			usr = session['username']
		else:
			usr = 'Not logged in'

		self.logger.error("""Path:                 %s 
HTTP Method:          %s
Client IP Address:    %s
User Agent:           %s
User Platform:        %s
User Browser:         %s
User Browser Version: %s
Username:             %s
""" % (
			request.path,
			request.method,
			request.remote_addr,
			request.user_agent.string,
			request.user_agent.platform,
			request.user_agent.browser,
			request.user_agent.version,
			usr,
			
		), exc_info=exc_info)

