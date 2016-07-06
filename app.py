#!/usr/bin/python
from flask import Flask, request, session, abort, g, render_template, url_for
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

	def __init__(self, init_object_name):
		"""Constructor for the CortexFlask application. Reads the config, sets
		up logging, configures Jinja and Flask."""

		# Call the superclass (Flask) constructor
		super(CortexFlask, self).__init__(init_object_name)

		# CSRF exemption support
		self._exempt_views = set()
		self.before_request(self._csrf_protect)

		# CSRF token function in templates
		self.jinja_env.globals['csrf_token'] = self._generate_csrf_token

		# Load the __init__.py config defaults
		self.config.from_object("cortex.defaultcfg")

		# Load system config file
		self.config.from_pyfile('/data/cortex/cortex.conf')

		# Set up logging to file
		if self.config['FILE_LOG'] == True:
			file_handler = RotatingFileHandler(self.config['LOG_DIR'] + '/' + self.config['LOG_FILE'], 'a', self.config['LOG_FILE_MAX_SIZE'], self.config['LOG_FILE_MAX_FILES'])
			file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s'))
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

		# check the database is up and is working
		self.init_database()

	################################################################################

	def pwgen(self, length=16):
		"""This is very crude password generator. It is currently only used to generate
		a CSRF token."""

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
			g.db = mysql.connect(host=self.config['MYSQL_HOST'], port=self.config['MYSQL_PORT'], user=self.config['MYSQL_USER'], passwd=self.config['MYSQL_PASS'], db=self.config['MYSQL_NAME'], charset="utf8")
		except Exception as ex:
			self.fatal_error('Unable to connect to MySQL', str(ex))

################################################################################

	def inject_template_data(self):
		"""This function is called on every page load. It injects a 'workflows'
		variable in to every render_template call, which is used to populate the
		Workflows menu on the page. It also injects the list of menu items
		and the items in the menus."""

		# We return a dictionary with each key being a variable to set
		# within the template.
		injectdata = dict()

		# Inject the workflows variable which is a list of loaded workflows
		injectdata['workflows'] =self.workflows

		# Inject the menu items 
		# systems, workflows, vmware, puppet, admin
		# Define the 'systems' menu
		systems = [
			{'link': url_for('systems'), 'title': 'Systems list', 'icon': 'fa-list'},
			{'link': url_for('systems_new'), 'title': 'Allocate system name', 'icon': 'fa-plus'}
		]
		vmware = [
			{'link': url_for('vmware_os'), 'title': 'Operating systems', 'icon': 'fa-pie-chart'},
			{'link': url_for('vmware_hw'), 'title': 'Hardware version', 'icon': 'fa-pie-chart'},
			{'link': url_for('vmware_power'), 'title': 'Power state', 'icon': 'fa-pie-chart'},
			{'link': url_for('vmware_specs'), 'title': 'RAM & CPU', 'icon': 'fa-pie-chart'},
			{'link': url_for('vmware_tools'), 'title': 'VM tools', 'icon': 'fa-pie-chart'},
			{'link': url_for('vmware_clusters'), 'title': 'Clusters', 'icon': 'fa-cubes'},
			{'link': url_for('vmware_data'), 'title': 'VM data', 'icon': 'fa-th'},
			{'link': url_for('vmware_data_unlinked'), 'title': 'Unlinked VMs', 'icon': 'fa-frown-o'},
			{'link': url_for('vmware_history'), 'title': 'History', 'icon': 'fa-line-chart'}
		]
		puppet = [
			{'link': url_for('puppet_dashboard'), 'title': 'Dashboard', 'icon': 'fa-dashboard'},
			{'link': url_for('puppet_nodes'), 'title': 'Nodes', 'icon': 'fa-server'},
			{'link': url_for('puppet_groups'), 'title': 'Groups', 'icon': 'fa-object-group'},
			{'link': url_for('puppet_enc_default'), 'title': 'Default classes', 'icon': 'fa-globe'},
			{'link': url_for('puppet_radiator'), 'title': 'Radiator view', 'icon': 'fa-desktop'},
		]
		admin = [
			{'link': url_for('admin_classes'), 'title': 'Classes', 'icon': 'fa-table'},	
			{'link': url_for('admin_tasks'), 'title': 'Tasks', 'icon': 'fa-tasks'},
			{'link': url_for('admin_maint'), 'title': 'Maintenance', 'icon': 'fa-gears'}
		]

		injectdata['menu'] = { 'systems': systems, 'vmware': vmware, 'puppet': puppet, 'admin': admin }

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

################################################################################

	def init_database(self):
		"""Ensures cortex can talk to the database (rather than waiting for a HTTP
		connection to trigger before_request) and the tables are there. Only runs
		at cortex startup."""

		# Connect to database
		try:
			temp_db = mysql.connect(host=self.config['MYSQL_HOST'], port=self.config['MYSQL_PORT'], user=self.config['MYSQL_USER'], passwd=self.config['MYSQL_PASS'], db=self.config['MYSQL_NAME'])
		except Exception as ex:
			raise Exception("Could not connect to MySQL server: " + str(type(ex)) + " - " + str(ex))

		self.logger.info("Successfully connected to the MySQL database server")

		## Now create tables if they don't exist
		cursor = temp_db.cursor()

		## Turn on autocommit so each table is created in sequence
		cursor.connection.autocommit(True)

		## Turn off warnings (MySQLdb generates warnings even though we use IF NOT EXISTS- wtf?!)
		cursor._defer_warnings = True

		self.logger.info("Checking for and creating tables as necessary")

		cursor.execute("""CREATE TABLE IF NOT EXISTS `classes` (`name` varchar(16) NOT NULL,
		  `digits` tinyint(4) NOT NULL,
		  `disabled` tinyint(1) NOT NULL DEFAULT '0',
		  `lastid` int(11) DEFAULT '0',
		  `comment` text,
		  `link_vmware` tinyint(1) NOT NULL DEFAULT '0',
		  `cmdb_type` varchar(64) DEFAULT NULL,
		  PRIMARY KEY (`name`)
		) ENGINE=InnoDB DEFAULT CHARSET=utf8;""")

		cursor.execute("""CREATE TABLE IF NOT EXISTS `events` (
		  `id` mediumint(11) NOT NULL AUTO_INCREMENT,
		  `source` varchar(255) NOT NULL,
		  `related_id` mediumint(11) DEFAULT NULL,
		  `name` varchar(255) NOT NULL,
		  `username` varchar(64) NOT NULL,
		  `desc` text,
		  `status` tinyint(4) NOT NULL DEFAULT '0',
		  `start` datetime NOT NULL,
		  `end` datetime DEFAULT NULL,
		  PRIMARY KEY (`id`)
		) ENGINE=InnoDB DEFAULT CHARSET=utf8;""")

		cursor.execute("""CREATE TABLE IF NOT EXISTS `kv_settings` (
		  `key` varchar(64) NOT NULL,
		  `value` text,
		  PRIMARY KEY (`key`)
		) ENGINE=InnoDB DEFAULT CHARSET=utf8;""")

		cursor.execute("""CREATE TABLE IF NOT EXISTS `systems` (
		  `id` mediumint(11) NOT NULL AUTO_INCREMENT,
		  `type` tinyint(4) NOT NULL,
		  `class` varchar(16) DEFAULT NULL,
		  `number` mediumint(11) DEFAULT NULL,
		  `name` varchar(256) NOT NULL,
		  `allocation_date` datetime DEFAULT NULL,
		  `allocation_who` varchar(64) DEFAULT NULL,
		  `allocation_comment` text NOT NULL,
		  `cmdb_id` varchar(128) DEFAULT NULL,
		  `vmware_uuid` varchar(36) DEFAULT NULL,
		  `review_status` tinyint(4) NOT NULL DEFAULT 0,
		  `review_task` varchar(16) DEFAULT NULL,
		  PRIMARY KEY (`id`),
		  KEY `class` (`class`),
		  KEY `name` (`name`(255)),
		  KEY `allocation_who` (`allocation_who`),
		  CONSTRAINT `systems_ibfk_1` FOREIGN KEY (`class`) REFERENCES `classes` (`name`)
		) ENGINE=InnoDB DEFAULT CHARSET=utf8;""")

		cursor.execute("""CREATE TABLE IF NOT EXISTS `tasks` (
		  `id` mediumint(11) NOT NULL AUTO_INCREMENT,
		  `module` varchar(64) NOT NULL,
		  `username` varchar(64) NOT NULL,
		  `start` datetime NOT NULL,
		  `end` datetime DEFAULT NULL,
		  `status` tinyint(4) NOT NULL DEFAULT '0',
		  `description` text,
		  PRIMARY KEY (`id`)
		) ENGINE=InnoDB DEFAULT CHARSET=utf8;""")

		cursor.execute("""CREATE TABLE IF NOT EXISTS  `puppet_groups` (
		  `name` varchar(255) NOT NULL,
		  `classes` text NOT NULL,
		  PRIMARY KEY (`name`)
		) ENGINE=InnoDB DEFAULT CHARSET=utf8;""")

		cursor.execute("""CREATE TABLE IF NOT EXISTS `puppet_nodes` (
		  `id` mediumint(11) NOT NULL,
		  `certname` varchar(255) NOT NULL,
		  `env` varchar(255) NOT NULL DEFAULT 'production',
		  `include_default` tinyint(1) NOT NULL DEFAULT '1',
		  `classes` text NOT NULL,
		  `variables` text NOT NULL,
		  PRIMARY KEY (`id`),
		  CONSTRAINT `puppet_nodes_ibfk_1` FOREIGN KEY (`id`) REFERENCES `systems` (`id`) ON DELETE CASCADE
		) ENGINE=InnoDB DEFAULT CHARSET=utf8;""")

		cursor.execute("""CREATE TABLE IF NOT EXISTS `sncache_cmdb_ci` (
		  `sys_id` varchar(32) NOT NULL,
		  `sys_class_name` varchar(128) NOT NULL,
		  `name` varchar(255) NOT NULL,
		  `operational_status` varchar(255) NOT NULL,
		  `u_number` varchar(255) NOT NULL,
		  `short_description` text NOT NULL,
		  `u_environment` varchar(255) DEFAULT NULL,
		  `virtual` tinyint(1) NOT NULL,
		  `comments` text,
		  `os` varchar(128) DEFAULT NULL,
		  PRIMARY KEY (`sys_id`),
		  KEY `u_number` (`u_number`)
		) ENGINE=InnoDB DEFAULT CHARSET=utf8;""")

		cursor.execute("""CREATE TABLE IF NOT EXISTS `vmware_cache_clusters` (
		  `id` varchar(255) NOT NULL,
		  `name` varchar(255) NOT NULL,
		  `vcenter` varchar(255) NOT NULL,
		  `did` varchar(255) DEFAULT NULL,
		  `ram` bigint DEFAULT 0,
		  `cores` int DEFAULT 0,
		  `cpuhz` bigint DEFAULT 0,
		  `ram_usage` bigint DEFAULT 0,
		  `cpu_usage` bigint DEFAULT 0,
		  `hosts` bigint(20) DEFAULT '0',
		  PRIMARY KEY (`id`,`vcenter`)
		) ENGINE=InnoDB DEFAULT CHARSET=utf8;""")

		cursor.execute("""CREATE TABLE IF NOT EXISTS `vmware_cache_datacenters` (
		  `id` varchar(255) NOT NULL,
		  `name` varchar(255) NOT NULL,
		  `vcenter` varchar(255) NOT NULL,
		  PRIMARY KEY (`id`,`vcenter`)
		) ENGINE=InnoDB DEFAULT CHARSET=utf8;""")

		cursor.execute("""CREATE TABLE IF NOT EXISTS `vmware_cache_vm` (
		  `id` varchar(255) NOT NULL,
		  `vcenter` varchar(255) NOT NULL,
		  `name` varchar(255) NOT NULL,
		  `uuid` varchar(36) NOT NULL,
		  `numCPU` int(11) NOT NULL,
		  `memoryMB` int(11) NOT NULL,
		  `powerState` varchar(255) NOT NULL,
		  `guestFullName` varchar(255) NOT NULL,
		  `guestId` varchar(255) NOT NULL,
		  `hwVersion` varchar(255) NOT NULL,
		  `hostname` varchar(255) NOT NULL,
		  `ipaddr` varchar(255) NOT NULL,
		  `annotation` text,
		  `cluster` varchar(255) NOT NULL,
		  `toolsRunningStatus` varchar(255) NOT NULL,
		  `toolsVersionStatus` varchar(255) NOT NULL,
		  `template` tinyint(1) NOT NULL DEFAULT '0',
		  PRIMARY KEY (`id`,`vcenter`),
		  KEY `uuid` (`uuid`),
		  KEY `name` (`name`)
		) ENGINE=InnoDB DEFAULT CHARSET=utf8;""")

		cursor.execute("""CREATE TABLE IF NOT EXISTS `vmware_cache_folders` (
		  `id` varchar(255) NOT NULL,
		  `name` varchar(255) NOT NULL,
		  `vcenter` varchar(255) NOT NULL,
		  `did` varchar(255) NOT NULL,
		  `parent` varchar(255) NOT NULL,
		  PRIMARY KEY (`id`,`vcenter`,`did`)
		) ENGINE=InnoDB DEFAULT CHARSET=utf8""")

		cursor.execute("""CREATE TABLE IF NOT EXISTS `stats_vm_count` (
		  `timestamp` DATETIME NOT NULL,
		  `value` mediumint(11) NOT NULL,
		  PRIMARY KEY (`timestamp`)
		) ENGINE=InnoDB DEFAULT CHARSET=utf8""")

		cursor.execute("""CREATE TABLE IF NOT EXISTS `stats_linux_vm_count` (
		  `timestamp` DATETIME NOT NULL,
		  `value` mediumint(11) NOT NULL,
		  PRIMARY KEY (`timestamp`)
		) ENGINE=InnoDB DEFAULT CHARSET=utf8""")

		cursor.execute("""CREATE TABLE IF NOT EXISTS `stats_windows_vm_count` (
		  `timestamp` DATETIME NOT NULL,
		  `value` mediumint(11) NOT NULL,
		  PRIMARY KEY (`timestamp`)
		) ENGINE=InnoDB DEFAULT CHARSET=utf8""")

		cursor.execute("""CREATE TABLE IF NOT EXISTS `stats_desktop_vm_count` (
		  `timestamp` DATETIME NOT NULL,
		  `value` mediumint(11) NOT NULL,
		  PRIMARY KEY (`timestamp`)
		) ENGINE=InnoDB DEFAULT CHARSET=utf8""")

		cursor.execute("""CREATE TABLE IF NOT EXISTS `stats_other_vm_count` (
		  `timestamp` DATETIME NOT NULL,
		  `value` mediumint(11) NOT NULL,
		  PRIMARY KEY (`timestamp`)
		) ENGINE=InnoDB DEFAULT CHARSET=utf8""")

		## Close database connection
		temp_db.close()

		self.logger.info("Database initialisation complete")
