#!/usr/bin/python
from flask import Flask, request, session, abort, g, render_template
import jinja2 
import os.path
from os import walk
import imp
import random
import string
import logging
import os.path
from logging.handlers import SMTPHandler
from logging.handlers import RotatingFileHandler
from logging import Formatter
import redis
import MySQLdb as mysql

class CortexFlask(Flask):

	workflows = []

	################################################################################

	def __init__(self,init_object_name):
		super(CortexFlask, self).__init__(init_object_name)

		# CSRF exemption support
		self._exempt_views = set()
		self.before_request(self._csrf_protect)

		# CSRF token function in templates
		self.jinja_env.globals['csrf_token'] = self._generate_csrf_token

		# Load the __init__.py config defaults
		self.config.from_object(init_object_name)

		# Load system config file
		if os.path.isfile('/data/cortex/cortex.conf'):
			self.config.from_pyfile('/data/cortex/cortex.conf')
		elif os.path.isfile('/etc/cortex/cortex.conf'):
			self.config.from_pyfile('/etc/cortex/cortex.conf')
		elif os.path.isfile('/etc/cortex.conf'):
			self.config.from_pyfile('/etc/cortex.conf')

		# Set up logging to file
		if self.config['FILE_LOG'] == True:
			file_handler = RotatingFileHandler(self.config['LOG_DIR'] + '/' + self.config['LOG_FILE'], 'a', self.config['LOG_FILE_MAX_SIZE'], self.config['LOG_FILE_MAX_FILES'])
			file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'))
			self.logger.addHandler(file_handler)

		# Set up the max log level
		if self.debug:
			self.logger.setLevel(logging.DEBUG)
			file_handler.setLevel(logging.DEBUG)
		else:
			self.logger.setLevel(logging.INFO)
			file_handler.setLevel(logging.INFO)

		# Output some startup info
		self.logger.info('cortex version ' + self.config['VERSION_MAJOR'] + " r" + self.config['VERSION_MINOR'] + ' initialised')
		self.logger.info('cortex debug status: ' + str(self.config['DEBUG']))

		# set up e-mail alert logging
		if self.config['EMAIL_ALERTS'] == True:
			# Log to file where e-mail alerts are going to
			self.logger.info('cortex e-mail alerts are enabled and being sent to: ' + str(self.config['ADMINS']))

			# Create the mail handler
			mail_handler = SMTPHandler(self.config['SMTP_SERVER'], self.config['EMAIL_FROM'], self.config['ADMINS'], self.config['EMAIL_SUBJECT'])

			# Set the minimum log level (errors) and set a formatter
			mail_handler.setLevel(logging.ERROR)
			mail_handler.setFormatter(Formatter("""
A fatal error occured in Cortex.

Message type:       %(levelname)s
Location:           %(pathname)s:%(lineno)d
Module:             %(module)s
Function:           %(funcName)s
Time:               %(asctime)s
Logger Name:        %(name)s
Process ID:         %(process)d

Further Details:

%(message)s

"""))

			self.logger.addHandler(mail_handler)

		# Debug Toolbar
		if self.config['DEBUG_TOOLBAR']:
			self.debug = True
			from flask_debugtoolbar import DebugToolbarExtension
			toolbar = DebugToolbarExtension(app)
			self.logger.info('cortex debug toolbar enabled - DO NOT USE THIS ON LIVE SYSTEMS!')

		# Set up before_request function to run on each request
		self.before_request(self.start_request)
	
		# Set up a context processor (inject data into jinja on each request)
		self.context_processor(self.inject_template_data)

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

					# The user should not have accidentally triggered this so just throw a 400
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

	################################################################################

	def load_workflows(self):
		"""Attempts to load the workflow config files from the workflows directory
		which is defined in app.config['WORKFLOWS_DIR']. Each config file is loaded
		and the display name stored"""

		# Where to store workflow settings
		self.wfsettings = {}

		# Ensure that we have a directory
		if not os.path.isdir(self.config['WORKFLOWS_DIR']):
			self.logger.error("The config option WORKFLOWS_DIR is not a directory!")
			return

		# List all entries in the directory and iterate over them
		entries = os.listdir(self.config['WORKFLOWS_DIR'])
		found = False
		for entry in entries:
			# Ignore the . and .. entries, along with any hidden files
			if entry.startswith('.'):
				continue

			# Get the fully qualified path of the file
			fqp = os.path.join(self.config['WORKFLOWS_DIR'], entry)

			# If it's a directory...
			if os.path.isdir(fqp):
				# This is or rather should be a workflow directory
				found = True
				views_file = os.path.join(fqp, "views.py")
				try:
					view_module = imp.load_source(entry, views_file)
					self.logger.info("Loaded workflow '" + entry + "' views module")
				except Exception as ex:
					self.logger.warn("Could not load workflow from file " + views_file + ": " + str(ex))
					continue

				# Load settings for this workflow if they exist ( settings files are optional )
				settings_file = os.path.join(fqp, "workflow.conf")
				if os.path.isfile(settings_file):
					try:
						self.wfsettings[entry] = self._load_workflow_settings(settings_file)
						self.logger.info("Loaded workflow '" + entry + "' config file")
					except Exception as ex:
						self.logger.warn("Could not load workflow config file " + settings_file + ": " + str(ex))
						continue

		# Warn if we didn't find any workflows
		if not found:
			self.logger.warn("The WORKFLOWS_DIR directory is empty, no workflows could be loaded!")

		# Set up template loading. Firstly build a list of FileSystemLoaders
		# that will process templates in each workflows' templates directory
		loader_data = {}
		for workflow in self.workflows:
			template_dir = os.path.join(self.config['WORKFLOWS_DIR'], workflow['name'], 'templates')
			loader_data[workflow['name']] = jinja2.FileSystemLoader(template_dir)

		# Create a ChoiceLoader, which by default will use the default 
		# template loader, and if that fails, uses a PrefixLoader which
		# can check the workflow template directories
		choice_loader = jinja2.ChoiceLoader(
		[
			self.jinja_loader,
			jinja2.PrefixLoader(loader_data, '::')
		])
		self.jinja_loader = choice_loader

	################################################################################
		
	def workflow_handler(self, workflow_name, workflow_title, workflow_order, **options):
		"""This is a decorator function that is used in workflows to add the principal view function
		into the app. It performs the function of Flask's @app.route but also adds the view function
		to a menu on the website to allow the workflow to be activated by the user.

		Usage is as such: @app.workflow_handler(__name__,"Title on menu", methods=['GET','POST'])

		:param workflow_name: the name of the workflow. This should always be __name__.
		:param workflow_title: the title of the workflow, as it appears in the list
		:param workflow_order: an integer hint as to the ordering of the workflow within the list.
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
			# Build the path that the workflow handler will be displayed on
			rule = "/workflows/" + workflow_name

			# Get the endpoint
			endpoint = options.pop('endpoint', None)

			# This is what Flask normally does for a route, which allows the
			# page to be accessible
			self.add_url_rule(rule, endpoint, f, **options)

			# Collect information about the workflow and store it in our workflows list
			self.workflows.append({'display': workflow_title, 'name': workflow_name, 'order': workflow_order, 'view_func': f.__name__ })
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

################################################################################

	def start_request(self):
		"""This function is run before the request is handled by Flask. It is used
		to connect to MySQL and Redis, and to tell old Internet Explorer versions
		to go away.
		"""

		# Check for MSIE version <= 10.0
		if (request.user_agent.browser == "msie" and int(round(float(request.user_agent.version))) <= 10):
			return render_template('foad.html')

		# Connect to redis
		try:
			g.redis = redis.StrictRedis(host=self.config['REDIS_HOST'], port=self.config['REDIS_PORT'], db=0)
			g.redis.get('foo') # it doesnt matter that this key doesnt exist, its just to force a test call to redis.
		except Exception as ex:
			self.fatal_error('Unable to connect to redis', str(ex))
	
		# Connect to database
		try:
			g.db = mysql.connect(host=self.config['MYSQL_HOST'], port=self.config['MYSQL_PORT'], user=self.config['MYSQL_USER'], passwd=self.config['MYSQL_PASS'], db=self.config['MYSQL_NAME'])
		except Exception as ex:
			self.fatal_error('Unable to connect to MySQL', str(ex))

################################################################################

	def inject_template_data(self):
		"""This function is called on every page load. It injects a 'workflows'
		variable in to every render_template call, which is used to populate the
		Workflows menu on the page."""

		# Inject in our list of workflows, so each page will see a 'workflows'
		# variable
		injectdata = dict(workflows=self.workflows)

		# If the current request is for a page that is a workflow, set the
		# value of the 'active' variable that's passed to the page templates
		# to say it's a workflow (this allows the navigation bar to work)
		for workflow in self.workflows:
			if workflow['view_func'] == request.endpoint:
				injectdata['active'] = 'workflows'
				break

		return injectdata

################################################################################

	def fatal_error(self, title, message):
		"""Aborts with an HTTP 500 (Internal Server Error) and produces
		an appropriate fatal error page"""

		g.fault_title = title
		g.fault_message = message
		abort(500)
