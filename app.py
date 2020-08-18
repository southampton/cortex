# -*- coding: utf-8 -*-
import datetime
import imp
import logging
import os
import random
import re
import socket
import string
import traceback
from logging import Formatter
from logging.handlers import RotatingFileHandler, SMTPHandler

import jinja2
import markupsafe
import MySQLdb as mysql
from flask import Flask, abort, request, session, url_for

from cortex.lib.perms import CortexPermissions

# pylint: disable=too-many-lines,no-member

# Regular expressions for Jinja links filter
SYSTEM_LINK_RE = re.compile(r"""\{\{ *system_link +id *= *(?P<quote>["']?) *(?P<link_id>[0-9]+) *(?P=quote) *\}\}(?P<link_text>[^{]*)\{\{ */system_link *\}\}""", re.IGNORECASE)
TASK_LINK_RE = re.compile(r"""\{\{ *task_link +id *= *(?P<quote>["']?) *(?P<link_id>[0-9]+) *(?P=quote) *\}\}(?P<link_text>[^{]*)\{\{ */task_link *\}\}""", re.IGNORECASE)

class CortexFlask(Flask):

	## A list of Cortex workflows
	workflows = {}

	## A list of dict's, each representing a workflow 'create' function
	wf_functions = []

	## A list of dict's, each representing a workflow 'system-action' function
	wf_system_functions = []

	################################################################################

	def __init__(self, init_object_name):
		"""Constructor for the CortexFlask application. Reads the config, sets
		up logging, configures Jinja and Flask."""

		# Call the superclass (Flask) constructor
		super(CortexFlask, self).__init__(init_object_name)

		# CSRF exemption support
		self._exempt_views = set()
		self.before_request(self._csrf_protect)

		# Jinja Template Functions and Filters
		self.jinja_env.globals['csrf_token'] = self._generate_csrf_token
		self.jinja_env.globals['utcnow'] = datetime.datetime.utcnow
		self.jinja_env.filters['parse_cortex_links'] = self.parse_cortex_links
		self.jinja_env.filters['all'] = all
		self.jinja_env.filters['any'] = any

		# Load Cortex configuration
		self._load_config("/data/cortex")

		# Make TEMPLATES_AUTO_RELOAD work (we've touch the Jinja environment). See resolved Flask issue #1907
		if 'TEMPLATES_AUTO_RELOAD' in self.config and self.config['TEMPLATES_AUTO_RELOAD']:
			self.jinja_env.auto_reload = True

		# Set up logging to file
		if self.config['FILE_LOG']:
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
		self.logger.info('cortex version ' + self.config['VERSION'] + ' initialised')
		self.logger.info('cortex debug status: ' + str(self.config['DEBUG']))

		# set up e-mail alert logging
		if self.config['EMAIL_ALERTS']:
			# Log to file where e-mail alerts are going to
			self.logger.info('cortex e-mail alerts are enabled and being sent to: ' + str(self.config['ADMINS']))

			# Create the mail handler
			mail_handler = SMTPHandler(self.config['SMTP_SERVER'], self.config['EMAIL_FROM'], self.config['ADMINS'], self.config['EMAIL_SUBJECT'])

			# Get Hostname / FQDN
			try:
				log_extra = {'hostname': socket.gethostname(), 'fqdn': socket.getfqdn()}
			except Exception:
				log_extra = {'hostname': 'unknown', 'fqdn': 'unknown'}

			# Set Formatter message text (email body)
			formatter_text = """
A fatal error occured in Cortex.

Hostname:           {hostname}
FQDN:               {fqdn}

Message type:       %(levelname)s
Location:           %(pathname)s:%(lineno)d
Module:             %(module)s
Function:           %(funcName)s
Time:               %(asctime)s
Logger Name:        %(name)s
Process ID:         %(process)d

Further Details:

%(message)s
"""
			# Add log_extra data into the formatter text
			formatter_text = formatter_text.format(**log_extra)

			# Set the minimum log level (errors) and set a formatter
			mail_handler.setLevel(logging.ERROR)
			mail_handler.setFormatter(Formatter(formatter_text))

			self.logger.addHandler(mail_handler)

		# check the database is up and is working
		self.init_database()

		# initialise the permissions
		self.permissions = CortexPermissions(self.config)

	################################################################################

	def _load_config(self, base_dir):
		"""
		Loads Cortex application config in the following order:
		1. From the default config object
		2. From the primary config file cortex.conf
		3. From config files in the cortex.conf.d directory
		"""
		# Load the __init__.py config defaults
		self.config.from_object("cortex.defaultcfg")

		# Load primary system config file
		self.config.from_pyfile(os.path.join(base_dir, "cortex.conf"))

		# Load config files from cortex.conf.d
		config_directory = os.path.join(base_dir, "cortex.conf.d")
		if os.path.isdir(config_directory):
			for config_file in sorted(os.listdir(config_directory)):
				if config_file.endswith(".conf"):
					self.config.from_pyfile(os.path.join(config_directory, config_file))

	################################################################################

	# pylint: disable=no-self-use
	def pwgen(self, alphabet=string.ascii_letters + string.digits, length=32):
		"""This is very crude password generator. Used to generate a CSRF token, and
		simple random tokens."""

		return ''.join(random.choices(alphabet, k=length))

	################################################################################

	def _generate_csrf_token(self):
		"""This function is used to generate a CSRF token for use in templates."""

		if '_csrf_token' not in session:
			session['_csrf_token'] = self.pwgen(length=32)

		return session['_csrf_token']

	################################################################################

	def _csrf_protect(self):
		"""Performs the checking of CSRF tokens. This check is skipped for the
		GET, HEAD, OPTIONS and TRACE methods within HTTP, and is also skipped
		for any function that has been added to _exempt_views by use of the
		disable_csrf_check decorator."""

		## Throw away requests with methods we don't support
		if request.method not in ('GET', 'HEAD', 'POST', 'DELETE'):
			abort(405)

		# Get the function that is rendering the current view
		view = self.view_functions.get(request.endpoint)

		# For methods that require CSRF checking
		if request.method == 'POST' and view is not None:
			# If the view is not part of the API and it's not exempt
			view_location = view.__module__ + '.' + view.__name__
			if re.search(r"[\w]*cortex\.api\.endpoints[\w]*", view.__module__) is None and not view_location in self._exempt_views:
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

	def load_workflows(self):
		"""Attempts to load the workflow config files from the workflows directory
		which is defined in app.config['WORKFLOWS_DIR']. Each config file is loaded
		and the display name stored"""

		# Ensure that we have a directory
		if not os.path.isdir(self.config['WORKFLOWS_DIR']):
			self.logger.error("Workflows: The config option WORKFLOWS_DIR is not a directory!")
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
				self.logger.info("Workflows: Loading workflow '" + entry + "'")

				views_file = os.path.join(fqp, "views.py")
				self.logger.info("Loading " + entry + " from " + views_file)
				try:
					imp.load_source(entry, views_file)
					self.logger.info("Workflows: Finished loading workflow '" + entry + "'")
				except Exception as ex:
					self.logger.warn("Workflows: Could not load from file " + views_file + ": " + str(type(ex)) + " - " + str(ex))
					self.logger.warn(traceback.format_exc())
					continue

		# Warn if we didn't find any workflows
		if not found:
			self.logger.warn("Workflows: The WORKFLOWS_DIR directory is empty (no workflows exist)")

		# Set up template loading. Firstly build a list of FileSystemLoaders
		# that will process templates in each workflows' templates directory
		loader_data = {}
		wflist = self.wf_functions + self.wf_system_functions
		for workflow in wflist:
			template_dir = os.path.join(self.config['WORKFLOWS_DIR'], workflow['workflow'], 'templates')
			loader_data[workflow['workflow']] = jinja2.FileSystemLoader(template_dir)

		# Create a ChoiceLoader, which by default will use the default
		# template loader, and if that fails, uses a PrefixLoader which
		# can check the workflow template directories
		choice_loader = jinja2.ChoiceLoader([
			self.jinja_loader,
			jinja2.PrefixLoader(loader_data, '::')
		])
		self.jinja_loader = choice_loader

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

	# pylint: disable=invalid-name,no-self-use
	def parse_cortex_links(self, s, make_safe=True):
		"""Primarily aimed at being a Jinja filter, this allows for the following
		to be put in to text that will resolve it to a hyperlink in HTML:
		{{system_link id="123"}}link text{{/system_link}}
		{{task_link id="456"}}link text{{/task_link}}
		"""

		# These is the list of regexs
		regexs = [SYSTEM_LINK_RE, TASK_LINK_RE]

		# Start with our result equalling our input, and start searching at the beginning)
		result = s
		search_index = 0

		# Whilst there's more string to search...
		while search_index < len(result):
			# Setup search for the first matching regex
			lowest_index = len(result)
			lowest_re_result = None
			lowest_regex = None

			# Iterate over all our regexs and find the one that matches earliest in our string
			for regex in regexs:
				# Note we start our search at start_index so we don't re-evaluate stuff we've already parsed
				re_result = regex.search(result[search_index:])

				# If we got a hit on this regex and it's earlier in the string than the previous...
				if re_result is not None and re_result.span()[0] < lowest_index:
					# Make a note!
					lowest_re_result = re_result
					lowest_regex = regex
					lowest_index = lowest_re_result.span()[0]

			# If we found no matching regexs, then there are no more changes to make, so stop searching
			if lowest_regex is None:
				break

			# Replace the text appropriately depending on what we found
			if lowest_regex is SYSTEM_LINK_RE:
				if make_safe:
					link_text = str(markupsafe.escape(lowest_re_result.group('link_text')))
				else:
					link_text = lowest_re_result.group('link_text')
				url = url_for('system_view', system_id=int(lowest_re_result.group('link_id')))
				inserted_text = "<a href='" + url + "'>" + link_text + "</a>"
			elif lowest_regex is TASK_LINK_RE:
				if make_safe:
					link_text = str(markupsafe.escape(lowest_re_result.group('link_text')))
				else:
					link_text = lowest_re_result.group('link_text')
				url = url_for('task_status', task_id=int(lowest_re_result.group('link_id')))
				inserted_text = "<a href='" + url + "'>" + link_text + "</a>"

			# Update our string and variables
			before_text = result[0:search_index + lowest_re_result.span()[0]]
			if make_safe:
				old_length = len(before_text)
				# Make safe the text that we haven't already made safe before
				before_text = result[0:search_index] + str(markupsafe.escape(result[search_index:search_index + lowest_re_result.span()[0]]))
				additional_length = len(before_text) - old_length
			else:
				additional_length = 0
			result = before_text + inserted_text + result[search_index + lowest_re_result.span()[1]:]
			search_index = additional_length + search_index + lowest_re_result.span()[0] + len(inserted_text)

		if make_safe:
			# Make the trailing part of the string safe
			result = result[0:search_index] + str(markupsafe.escape(result[search_index:]))

		return result

	################################################################################

	# pylint: disable=invalid-name
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
		# pylint: disable=protected-access
		cursor._defer_warnings = True
		# pylint: enable=protected-access

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
		  `id` int(11) NOT NULL AUTO_INCREMENT,
		  `source` varchar(255) NOT NULL,
		  `related_id` mediumint(11) DEFAULT NULL,
		  `name` varchar(255) NOT NULL,
		  `username` varchar(64) NOT NULL,
		  `desc` text,
		  `status` tinyint(4) NOT NULL DEFAULT '0',
		  `start` datetime NOT NULL,
		  `end` datetime DEFAULT NULL,
		  `ipaddr` varchar(43) DEFAULT NULL,
		  PRIMARY KEY (`id`)
		) ENGINE=InnoDB DEFAULT CHARSET=utf8;""")

		try:
			cursor.execute("""CREATE INDEX `related_events_key` ON `events` (`related_id`)""")
		except Exception:
			pass

		try:
			cursor.execute("""CREATE INDEX `events_name_index` ON `events` (`name`)""")
		except Exception:
			pass

		cursor.execute("""CREATE TABLE IF NOT EXISTS `kv_settings` (
		  `key` varchar(64) NOT NULL,
		  `value` text,
		  PRIMARY KEY (`key`)
		) ENGINE=InnoDB DEFAULT CHARSET=utf8;""")

		cursor.execute("""CREATE TABLE IF NOT EXISTS `puppet_environments` (
		  `id` mediumint(11) NOT NULL AUTO_INCREMENT,
		  `short_name` varchar(255) NOT NULL,
		  `environment_name` varchar(255) NOT NULL,
		  `type` tinyint(4) NOT NULL,
		  `owner` varchar(64) DEFAULT NULL,
		  PRIMARY KEY (`id`),
		  UNIQUE(`environment_name`)
		) ENGINE=InnoDB DEFAULT CHARSET=utf8;""")

		cursor.execute("""CREATE TABLE IF NOT EXISTS `puppet_modules` (
		  `id` mediumint(11) NOT NULL AUTO_INCREMENT,
		  `environment_id` mediumint(11) NOT NULL,
		  `module_name` varchar(255) NOT NULL,
		  `last_updated` datetime NOT NULL,
		  PRIMARY KEY (`id`),
		  UNIQUE(`environment_id`, `module_name`),
		  CONSTRAINT `puppet_modules_ibfk_1` FOREIGN KEY (`environment_id`) REFERENCES `puppet_environments` (`id`) ON DELETE CASCADE
		) ENGINE=InnoDB DEFAULT CHARSET=utf8;""")

		cursor.execute("""CREATE TABLE IF NOT EXISTS `puppet_classes` (
		  `id` mediumint(11) NOT NULL AUTO_INCREMENT,
		  `module_id` mediumint(11) NOT NULL,
		  `class_name` varchar(255) NOT NULL,
		  `desc` text,
		  PRIMARY KEY (`id`),
		  UNIQUE(`module_id`, `class_name`),
		  CONSTRAINT `puppet_classes_ibfk_1` FOREIGN KEY (`module_id`) REFERENCES `puppet_modules` (`id`) ON DELETE CASCADE
		) ENGINE=InnoDB DEFAULT CHARSET=utf8;""")

		cursor.execute("""CREATE TABLE IF NOT EXISTS `puppet_documentation` (
		  `class_id` mediumint(11) NOT NULL,
		  `tag` varchar(16) NOT NULL,
		  `name` varchar(255) NOT NULL,
		  `text` text,
		  `types` text,
		  PRIMARY KEY (`class_id`, `tag`, `name`),
		  CONSTRAINT `puppet_documentation_ibfk_1` FOREIGN KEY (`class_id`) REFERENCES `puppet_classes` (`id`) ON DELETE CASCADE
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
		  `expiry_date` datetime DEFAULT NULL,
		  `build_count` mediumint(11) DEFAULT 0,
		  `decom_date` datetime DEFAULT NULL,
		  `primary_owner_who` varchar(64) DEFAULT NULL,
		  `primary_owner_role` varchar(64) DEFAULT NULL,
		  `secondary_owner_who` varchar(64) DEFAULT NULL,
		  `secondary_owner_role` varchar(64) DEFAULT NULL,
		  `enable_backup` tinyint(1) DEFAULT 2,
		  `enable_backup_scripts` tinyint(1) DEFAULT 2,
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
		  `status` tinyint(4) NOT NULL DEFAULT '0' COMMENT '0: in progress, 1: success, 2: failure, 3: warning',
		  `description` text,
		  PRIMARY KEY (`id`)
		) ENGINE=InnoDB DEFAULT CHARSET=utf8;""")

		cursor.execute("""CREATE TABLE IF NOT EXISTS `puppet_nodes` (
		  `id` mediumint(11) NOT NULL,
		  `certname` varchar(255) NOT NULL,
		  `env` varchar(255) NOT NULL DEFAULT 'production',
		  `include_default` tinyint(1) NOT NULL DEFAULT '1',
		  `classes` text NOT NULL,
		  `variables` text NOT NULL,
		  `last_failed` datetime DEFAULT NULL,
		  `last_changed` datetime DEFAULT NULL,
		  `noop_since` datetime DEFAULT NULL,
		  PRIMARY KEY (`id`),
		  CONSTRAINT `puppet_nodes_ibfk_1` FOREIGN KEY (`id`) REFERENCES `systems` (`id`) ON DELETE CASCADE
		) ENGINE=InnoDB DEFAULT CHARSET=utf8;""")

		# Attempt to alter the puppet_nodes table and add new columns.
		try:
			cursor.execute("""ALTER TABLE `puppet_nodes` ADD `last_failed` datetime DEFAULT NULL""")
			cursor.execute("""ALTER TABLE `puppet_nodes` ADD `last_changed` datetime DEFAULT NULL""")
			cursor.execute("""ALTER TABLE `puppet_nodes` ADD `noop_since` datetime DEFAULT NULL""")
		except Exception:
			pass

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

		cursor.execute("""CREATE TABLE IF NOT EXISTS `realname_cache` (
		 `username` varchar(64) NOT NULL,
		 `realname` varchar(255),
		 PRIMARY KEY (`username`)
		) ENGINE=InnoDB DEFAULT CHARSET=utf8""")

		cursor.execute("""DROP TABLE IF EXISTS `ldap_group_cache`""")

		cursor.execute("""CREATE TABLE IF NOT EXISTS `ldap_group_cache` (
		 `username` varchar(64) NOT NULL,
		 `group_dn` varchar(255) NOT NULL,
		 `group` varchar(255) NOT NULL,
		  PRIMARY KEY (`username`, `group_dn`)
		) ENGINE=InnoDB DEFAULT CHARSET=utf8""")

		cursor.execute("""CREATE TABLE IF NOT EXISTS `ldap_group_cache_expire` (
		 `username` varchar(64) NOT NULL,
		 `expiry_date` datetime DEFAULT NULL,
		  PRIMARY KEY (`username`)
		) ENGINE=InnoDB DEFAULT CHARSET=utf8""")

		cursor.execute("""TRUNCATE `ldap_group_cache_expire`""")

		cursor.execute("""CREATE TABLE IF NOT EXISTS `system_request` (
		 `id` mediumint(11) NOT NULL AUTO_INCREMENT,
		 `request_date` datetime NOT NULL,
		 `requested_who` varchar(64) NOT NULL,
		 `hostname` varchar(255) NOT NULL,
		 `workflow` varchar(64) NOT NULL,
		 `sockets` int(11) NOT NULL,
		 `cores` int(11) NOT NULL,
		 `ram` int(11) NOT NULL,
		 `disk` int(11) NOT NULL,
		 `template` varchar(255) NOT NULL,
		 `network` varchar(255) DEFAULT NULL,
		 `cluster` varchar(255) NOT NULL,
		 `environment` varchar(255) NOT NULL,
		 `purpose` text NOT NULL,
		 `comments` text NOT NULL,
		 `expiry_date` datetime DEFAULT NULL,
		 `sendmail` tinyint(1) NOT NULL,
		 `status` int(2) NOT NULL COMMENT '0: pending, 1: rejected, 2: approved',
		 `updated_who` varchar(64) NOT NULL,
		 `updated_at` datetime NOT NULL,
		 `status_text` text DEFAULT NULL,
		  PRIMARY KEY (`id`)
		) ENGINE=InnoDB DEFAULT CHARSET=utf8""")

		# Attempt to alter the systems table and add new columns.
		try:
			cursor.execute("""ALTER TABLE `systems` ADD `expiry_date` datetime DEFAULT NULL""")
		except Exception:
			pass
		try:
			cursor.execute("""ALTER TABLE `systems` ADD `build_count` mediumint(11) DEFAULT 0""")
		except Exception:
			pass
		try:
			cursor.execute("""ALTER TABLE `systems` ADD `decom_date` datetime DEFAULT NULL""")
		except Exception:
			pass
		try:
			cursor.execute("""ALTER TABLE `systems` ADD `primary_owner_who` varchar(64) DEFAULT NULL""")
		except Exception:
			pass
		try:
			cursor.execute("""ALTER TABLE `systems` ADD `primary_owner_role` varchar(64) DEFAULT NULL""")
		except Exception:
			pass
		try:
			cursor.execute("""ALTER TABLE `systems` ADD `secondary_owner_who` varchar(64) DEFAULT NULL""")
		except Exception:
			pass
		try:
			cursor.execute("""ALTER TABLE `systems` ADD `secondary_owner_role` varchar(64) DEFAULT NULL""")
		except Exception:
			pass
		try:
			cursor.execute("""ALTER TABLE `systems` ADD `enable_backup` tinyint(1) DEFAULT 2""")
		except Exception:
			pass

		try:
			cursor.execute("""ALTER TABLE `systems` ADD `enable_backup_scripts` tinyint(1) DEFAULT 2""")
		except Exception:
			pass

		cursor.execute("""CREATE OR REPLACE VIEW `systems_info_view` AS SELECT
		  `systems`.`id` AS `id`,
		  `systems`.`type` AS `type`,
		  `systems`.`class` AS `class`,
		  `systems`.`number` AS `number`,
		  `systems`.`name` AS `name`,
		  `systems`.`allocation_date` AS `allocation_date`,
		  `systems`.`expiry_date` AS `expiry_date`,
		  `systems`.`decom_date` AS `decom_date`,
		  `systems`.`allocation_who` AS `allocation_who`,
		  `allocation_who_realname_cache`.`realname` AS `allocation_who_realname`,
		  `systems`.`allocation_comment` AS `allocation_comment`,
		  `systems`.`review_status` AS `review_status`,
		  `systems`.`review_task` AS `review_task`,
		  `systems`.`cmdb_id` AS `cmdb_id`,
		  `systems`.`build_count` AS `build_count`,
		  `systems`.`primary_owner_who` AS `primary_owner_who`,
		  `systems`.`primary_owner_role` AS `primary_owner_role`,
		  `primary_owner_who_realname_cache`.`realname` AS `primary_owner_who_realname`,
		  `systems`.`secondary_owner_who` AS `secondary_owner_who`,
		  `systems`.`secondary_owner_role` AS `secondary_owner_role`,
		  `secondary_owner_who_realname_cache`.`realname` AS `secondary_owner_who_realname`,
		  `sncache_cmdb_ci`.`sys_class_name` AS `cmdb_sys_class_name`,
		  `sncache_cmdb_ci`.`name` AS `cmdb_name`,
		  `sncache_cmdb_ci`.`operational_status` AS `cmdb_operational_status`,
		  `sncache_cmdb_ci`.`u_number` AS `cmdb_u_number`,
		  `sncache_cmdb_ci`.`u_environment` AS `cmdb_environment`,
		  `sncache_cmdb_ci`.`short_description` AS `cmdb_description`,
		  `sncache_cmdb_ci`.`comments` AS `cmdb_comments`,
		  `sncache_cmdb_ci`.`os` AS `cmdb_os`,
		  `sncache_cmdb_ci`.`short_description` AS `cmdb_short_description`,
		  `sncache_cmdb_ci`.`virtual` AS `cmdb_is_virtual`,
		  `vmware_cache_vm`.`id` AS `vmware_moid`,
		  `vmware_cache_vm`.`name` AS `vmware_name`,
		  `vmware_cache_vm`.`vcenter` AS `vmware_vcenter`,
		  `vmware_cache_vm`.`uuid` AS `vmware_uuid`,
		  `vmware_cache_vm`.`numCPU` AS `vmware_cpus`,
		  `vmware_cache_vm`.`memoryMB` AS `vmware_ram`,
		  `vmware_cache_vm`.`powerState` AS `vmware_guest_state`,
		  `vmware_cache_vm`.`guestFullName` AS `vmware_os`,
		  `vmware_cache_vm`.`hwVersion` AS `vmware_hwversion`,
		  `vmware_cache_vm`.`ipaddr` AS `vmware_ipaddr`,
		  `vmware_cache_vm`.`toolsVersionStatus` AS `vmware_tools_version_status`,
		  `vmware_cache_vm`.`hostname` AS `vmware_hostname`,
		  `puppet_nodes`.`certname` AS `puppet_certname`,
		  `puppet_nodes`.`env` AS `puppet_env`,
		  `puppet_nodes`.`include_default` AS `puppet_include_default`,
		  `puppet_nodes`.`classes` AS `puppet_classes`,
		  `puppet_nodes`.`variables` AS `puppet_variables`,
		  `puppet_nodes`.`last_failed` AS `puppet_last_failed`,
		  `puppet_nodes`.`last_changed` AS `puppet_last_changed`,
		  `puppet_nodes`.`noop_since` AS `puppet_noop_since`,
		  `systems`.`enable_backup` AS `enable_backup`,
		  `systems`.`enable_backup_scripts` AS `enable_backup_scripts`
		FROM `systems`
		LEFT JOIN `sncache_cmdb_ci` ON `systems`.`cmdb_id` = `sncache_cmdb_ci`.`sys_id`
		LEFT JOIN `vmware_cache_vm` ON `systems`.`vmware_uuid` = `vmware_cache_vm`.`uuid`
		LEFT JOIN `puppet_nodes` ON `systems`.`id` = `puppet_nodes`.`id`
		LEFT JOIN `realname_cache` AS `allocation_who_realname_cache` ON `systems`.`allocation_who` = `allocation_who_realname_cache`.`username`
		LEFT JOIN `realname_cache` AS `primary_owner_who_realname_cache` ON `systems`.`primary_owner_who` = `primary_owner_who_realname_cache`.`username`
		LEFT JOIN `realname_cache` AS `secondary_owner_who_realname_cache` ON `systems`.`secondary_owner_who` = `secondary_owner_who_realname_cache`.`username`""")

		cursor.execute("""CREATE TABLE IF NOT EXISTS `system_user_favourites` (
		  `username` varchar(255),
		  `system_id` mediumint(11) NOT NULL,
		  PRIMARY KEY (`username`, `system_id`),
		  UNIQUE (`username`, `system_id`),
		  CONSTRAINT `system_user_favourites_ibfk_1` FOREIGN KEY (`system_id`) REFERENCES `systems` (`id`) ON DELETE CASCADE
		) ENGINE=InnoDB DEFAULT CHARSET=utf8""")

		cursor.execute("""CREATE TABLE IF NOT EXISTS `certificate` (
		  `digest` varchar(40) NOT NULL,
		  `subjectHash` varchar(64),
		  `subjectCN` text,
		  `subjectDN` text,
		  `notBefore` DATETIME,
		  `notAfter` DATETIME,
		  `issuerCN` text,
		  `issuerDN` text,
		  `notify` tinyint(1) NOT NULL DEFAULT TRUE,
		  `notes` TEXT NOT NULL,
		  `keySize` integer DEFAULT NULL,
		  PRIMARY KEY (`digest`),
		  INDEX `idx_subjectCN` (`subjectCN`(128))
		) ENGINE=InnoDB DEFAULT CHARSET utf8;""")

		cursor.execute("""CREATE TABLE IF NOT EXISTS `certificate_sans` (
		  `cert_digest` varchar(40) NOT NULL,
		  `san` varchar(255) NOT NULL,
		  PRIMARY KEY (cert_digest, san),
		  FOREIGN KEY `ibfk_cert_digest` (`cert_digest`) REFERENCES `certificate` (`digest`) ON DELETE CASCADE
		) ENGINE=InnoDB DEFAULT CHARSET utf8;""")

		cursor.execute("""CREATE TABLE IF NOT EXISTS `scan_result` (
		  `id` mediumint(11) NOT NULL AUTO_INCREMENT,
		  `host` varchar(128) NOT NULL,
		  `port` integer(4) NOT NULL,
		  `cert_digest` varchar(40) NOT NULL,
		  `when` DATETIME NOT NULL,
		  `chain_state` tinyint(2) NOT NULL DEFAULT 0,
		  PRIMARY KEY (`id`),
		  FOREIGN KEY `ibfk_cert_digest` (`cert_digest`) REFERENCES `certificate` (`digest`) ON DELETE CASCADE,
		  INDEX `idx_host` (`host`)
		) ENGINE=InnoDB DEFAULT CHARSET utf8;""")

		cursor.execute("""CREATE TABLE IF NOT EXISTS `p_roles` (
		  `id` mediumint(11) NOT NULL AUTO_INCREMENT,
		  `name` varchar(64) NOT NULL,
		  `description` text NOT NULL,
		  PRIMARY KEY (`id`),
		  KEY (`name`)
		) ENGINE=InnoDB DEFAULT CHARSET=utf8 AUTO_INCREMENT=2""")

		cursor.execute("""CREATE TABLE IF NOT EXISTS `p_role_who` (
		  `id` mediumint(11) NOT NULL AUTO_INCREMENT,
		  `role_id` mediumint(11) NOT NULL,
		  `who` varchar(128) NOT NULL,
		  `type` tinyint(1) NOT NULL,
		  PRIMARY KEY (`id`),
		  UNIQUE (`role_id`, `who`, `type`),
		  CONSTRAINT `p_role_who_ibfk_1` FOREIGN KEY (`role_id`) REFERENCES `p_roles` (`id`) ON DELETE CASCADE
		) ENGINE=InnoDB DEFAULT CHARSET=utf8""")

		cursor.execute("""CREATE TABLE IF NOT EXISTS `p_perms` (
		  `id` mediumint(11) NOT NULL AUTO_INCREMENT,
		  `perm` varchar(64) NOT NULL,
		  `description` text NOT NULL,
		  `active` tinyint(1) NOT NULL DEFAULT 0,
		  PRIMARY KEY (`id`),
		  UNIQUE (`perm`)
		) ENGINE=InnoDB DEFAULT CHARSET=utf8;""")

		cursor.execute("""CREATE TABLE IF NOT EXISTS `p_role_perms` (
		  `role_id` mediumint(11) NOT NULL,
		  `perm_id` mediumint(11) NOT NULL,
		  PRIMARY KEY (`role_id`, `perm_id`),
		  CONSTRAINT `p_role_perms_ibfk_1` FOREIGN KEY (`role_id`) REFERENCES `p_roles` (`id`) ON DELETE CASCADE,
		  CONSTRAINT `p_role_perms_ibfk_2` FOREIGN KEY (`perm_id`) REFERENCES `p_perms` (`id`) ON DELETE CASCADE
		) ENGINE=InnoDB DEFAULT CHARSET=utf8;""")

		cursor.execute("""CREATE OR REPLACE VIEW `p_perms_view` AS
		SELECT DISTINCT
		  `p_role_who`.`who` AS `who`,
		  `p_role_who`.`type` AS `who_type`,
		  LOWER(`p_perms`.`perm`) AS `perm`
		FROM `p_role_who`
		JOIN `p_role_perms` ON `p_role_who`.`role_id`=`p_role_perms`.`role_id`
		JOIN `p_perms` ON `p_role_perms`.`perm_id`=`p_perms`.`id`
		WHERE `p_perms`.`active`=1""")

		cursor.execute("""CREATE TABLE IF NOT EXISTS `p_system_perms` (
		  `id` mediumint(11) NOT NULL AUTO_INCREMENT,
		  `perm` varchar(64) NOT NULL,
		  `description` text NOT NULL,
		  `active` tinyint(1) NOT NULL DEFAULT 0,
		  PRIMARY KEY (`id`),
		  UNIQUE (`perm`)
		) ENGINE=InnoDB DEFAULT CHARSET=utf8;""")

		cursor.execute("""CREATE TABLE IF NOT EXISTS `p_role_system_perms` (
		  `role_id` mediumint(11) NOT NULL,
		  `perm_id` mediumint(11) NOT NULL,
		  `system_id` mediumint(11) NOT NULL,
		  PRIMARY KEY (`role_id`, `perm_id`, `system_id`),
		  CONSTRAINT `p_role_system_perms_ibfk_1` FOREIGN KEY (`role_id`) REFERENCES `p_roles` (`id`) ON DELETE CASCADE,
		  CONSTRAINT `p_role_system_perms_ibfk_2` FOREIGN KEY (`perm_id`) REFERENCES `p_system_perms` (`id`) ON DELETE CASCADE,
		  CONSTRAINT `p_role_system_perms_ibfk_3` FOREIGN KEY (`system_id`) REFERENCES `systems` (`id`) ON DELETE CASCADE
		) ENGINE=InnoDB DEFAULT CHARSET=utf8;""")

		cursor.execute("""CREATE TABLE IF NOT EXISTS `p_system_perms_who` (
		  `id` mediumint(11) NOT NULL,
		  `perm_id` mediumint(11) NOT NULL,
		  `who` varchar(128) NOT NULL,
		  `type` tinyint(1) NOT NULL,
		  `system_id` mediumint(11) NOT NULL,
		  CONSTRAINT `p_system_perms_who_ibfk_1` FOREIGN KEY (`perm_id`) REFERENCES `p_system_perms` (`id`) ON DELETE CASCADE,
		  CONSTRAINT `p_system_perms_who_ibfk_2` FOREIGN KEY (`system_id`) REFERENCES `systems` (`id`) ON DELETE CASCADE
		) ENGINE=InnoDB DEFAULT CHARSET=utf8;""")

		cursor.execute("""CREATE OR REPLACE VIEW `p_system_perms_view` AS
		SELECT DISTINCT
		  `p_role_who`.`who` AS `who`,
		  `p_role_who`.`type` AS `who_type`,
		  `p_role_system_perms`.`system_id` AS `system_id`,
		  LOWER(`p_system_perms`.`perm`) AS `perm`
		FROM `p_role_who`
		JOIN `p_role_system_perms` ON `p_role_who`.`role_id`=`p_role_system_perms`.`role_id`
		JOIN `p_system_perms` ON `p_role_system_perms`.`perm_id`=`p_system_perms`.`id`
		WHERE `p_system_perms`.`active`=1
		UNION
		SELECT DISTINCT
		  `p_system_perms_who`.`who` AS `who`,
		  `p_system_perms_who`.`type` AS `who_type`,
		  `p_system_perms_who`.`system_id` AS `system_id`,
		  LOWER(`p_system_perms`.`perm`) AS `perm`
		FROM `p_system_perms_who`
		JOIN `p_system_perms` ON `p_system_perms_who`.`perm_id`=`p_system_perms`.`id`
		WHERE `p_system_perms`.`active`=1""")

		cursor.execute("""CREATE TABLE IF NOT EXISTS `p_puppet_perms` (
		  `id` mediumint(11) NOT NULL AUTO_INCREMENT,
		  `perm` varchar(64) NOT NULL,
		  `description` text NOT NULL,
		  `active` tinyint(1) NOT NULL DEFAULT 0,
		  PRIMARY KEY (`id`),
		  UNIQUE (`perm`)
		) ENGINE=InnoDB DEFAULT CHARSET=utf8;""")

		cursor.execute("""CREATE TABLE IF NOT EXISTS `p_role_puppet_perms` (
		  `role_id` mediumint(11) NOT NULL,
		  `perm_id` mediumint(11) NOT NULL,
		  `environment_id` mediumint(11) NOT NULL,
		  PRIMARY KEY (`role_id`, `perm_id`, `environment_id`),
		  CONSTRAINT `p_role_puppet_perms_ibfk_1` FOREIGN KEY (`role_id`) REFERENCES `p_roles` (`id`) ON DELETE CASCADE,
		  CONSTRAINT `p_role_puppet_perms_ibfk_2` FOREIGN KEY (`perm_id`) REFERENCES `p_puppet_perms` (`id`) ON DELETE CASCADE,
		  CONSTRAINT `p_role_puppet_perms_ibfk_3` FOREIGN KEY (`environment_id`) REFERENCES `puppet_environments` (`id`) ON DELETE CASCADE
		) ENGINE=InnoDB DEFAULT CHARSET=utf8;""")

		cursor.execute("""CREATE OR REPLACE VIEW `p_puppet_perms_view` AS
		SELECT DISTINCT
			`p_role_who`.`who` AS `who`,
			`p_role_who`.`type` AS `who_type`,
			`p_role_puppet_perms`.`environment_id` AS `environment_id`,
			LOWER(`p_puppet_perms`.`perm`) AS `perm`
		FROM `p_role_who`
		JOIN `p_role_puppet_perms` ON `p_role_who`.`role_id`=`p_role_puppet_perms`.`role_id`
		JOIN `p_puppet_perms` ON `p_role_puppet_perms`.`perm_id`=`p_puppet_perms`.`id`
		WHERE `p_puppet_perms`.`active`=1
		UNION
		SELECT DISTINCT
			`puppet_environments`.`owner` AS `who`,
			0 AS `who_type`,
			`puppet_environments`.`id` AS `environment_id`,
			LOWER(`p_puppet_perms`.`perm`) AS `perm`
		FROM `puppet_environments`
		CROSS JOIN `p_puppet_perms`
		WHERE `p_puppet_perms`.`active`=1 AND `owner` IS NOT NULL""")

		## Clean up old tables
		cursor.execute("""DROP TABLE IF EXISTS `workflow_perms`""")
		cursor.execute("""DROP TABLE IF EXISTS `puppet_groups`""")
		cursor.execute("""DROP TABLE IF EXISTS `puppet_modules_info`""")

		## Close database connection
		temp_db.close()

		self.logger.info("Database initialisation complete")

################################################################################
