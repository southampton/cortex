#!/usr/bin/python
# -*- coding: utf-8 -*-
from flask import Flask, request, session, abort, g, render_template, url_for
import jinja2
import os.path
from os import walk
import imp
import random
import string
import logging
import os.path
import datetime
from logging.handlers import SMTPHandler
from logging.handlers import RotatingFileHandler
from logging import Formatter
import redis
import MySQLdb as mysql
import traceback

class CortexFlask(Flask):
	## A list of dict's, each representing a workflow 'create' function
	wf_functions        = []

	## A list of dict's, each representing a workflow 'system-action' function
	wf_system_functions = []

	workflows = {}

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
		self.jinja_env.globals['utcnow'] = datetime.datetime.utcnow

		# Load the __init__.py config defaults
		self.config.from_object("cortex.defaultcfg")

		# Load system config file
		self.config.from_pyfile('/data/cortex/cortex.conf')

		# Make TEMPLATES_AUTO_RELOAD work (we've touch the Jinja environment). See resolved Flask issue #1907
		if 'TEMPLATES_AUTO_RELOAD' in self.config and self.config['TEMPLATES_AUTO_RELOAD']:
			self.jinja_env.auto_reload = True

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
		self.logger.info('cortex version ' + self.config['VERSION'] + ' initialised')
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
			toolbar = DebugToolbarExtension(self)
			self.logger.info('cortex debug toolbar enabled - DO NOT USE THIS ON LIVE SYSTEMS!')

		# check the database is up and is working
		self.init_database()

		# set up permissions
		self.init_permissions()

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

		## Throw away requests with methods we don't support
		if request.method not in ('GET', 'HEAD', 'POST'):
			abort(405)

		# For methods that require CSRF checking
		if request.method == 'POST':
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
					view_module = imp.load_source(entry, views_file)
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
		choice_loader = jinja2.ChoiceLoader(
		[
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
		  `ipaddr` varchar(43) DEFAULT NULL,
		  PRIMARY KEY (`id`)
		) ENGINE=InnoDB DEFAULT CHARSET=utf8;""")

		try:
			cursor.execute("""CREATE INDEX `related_events_key` ON `events` (`related_id`)""")
		except Exception as ex:
			pass

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
		  `expiry_date` datetime DEFAULT NULL,
		  `build_count` mediumint(11) DEFAULT 0,
		  `decom_date` datetime DEFAULT NULL,
		  `primary_owner_who` varchar(64) DEFAULT NULL,
		  `primary_owner_role` varchar(64) DEFAULT NULL,
		  `secondary_owner_who` varchar(64) DEFAULT NULL,
		  `secondary_owner_role` varchar(64) DEFAULT NULL,
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

		try:
			cursor.execute("""ALTER TABLE `systems` ADD `expiry_date` datetime DEFAULT NULL""")
		except Exception as e:
			pass

		try:
			cursor.execute("""ALTER TABLE `systems` ADD `build_count` mediumint(11) DEFAULT 0""")
		except Exception as e:
			pass

		try:
			cursor.execute("""ALTER TABLE `systems` ADD `decom_date` datetime DEFAULT NULL""")
		except Exception as e:
			pass
		
		# Attempt to alter the systems table and add new columns.
		try:
			cursor.execute("""ALTER TABLE `systems` ADD `primary_owner_who` varchar(64) DEFAULT NULL""")
		except Exception as e:
			pass
		try:
			cursor.execute("""ALTER TABLE `systems` ADD `primary_owner_role` varchar(64) DEFAULT NULL""")
		except Exception as e:
			pass
		try:
			cursor.execute("""ALTER TABLE `systems` ADD `secondary_owner_who` varchar(64) DEFAULT NULL""")
		except Exception as e:
			pass
		try:
			cursor.execute("""ALTER TABLE `systems` ADD `secondary_owner_role` varchar(64) DEFAULT NULL""")
		except Exception as e:
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
		 `puppet_nodes`.`variables` AS `puppet_variables`
                FROM `systems` 
		LEFT JOIN `sncache_cmdb_ci` ON `systems`.`cmdb_id` = `sncache_cmdb_ci`.`sys_id`
		LEFT JOIN `vmware_cache_vm` ON `systems`.`vmware_uuid` = `vmware_cache_vm`.`uuid`
		LEFT JOIN `puppet_nodes` ON `systems`.`id` = `puppet_nodes`.`id` 
		LEFT JOIN `realname_cache` AS  `allocation_who_realname_cache` ON `systems`.`allocation_who` = `allocation_who_realname_cache`.`username`
		LEFT JOIN `realname_cache` AS  `primary_owner_who_realname_cache` ON `systems`.`primary_owner_who` = `primary_owner_who_realname_cache`.`username`
		LEFT JOIN `realname_cache` AS  `secondary_owner_who_realname_cache` ON `systems`.`secondary_owner_who` = `secondary_owner_who_realname_cache`.`username`""")
       	
		cursor.execute("""CREATE TABLE IF NOT EXISTS `roles` (
		  `id` mediumint(11) NOT NULL AUTO_INCREMENT,
		  `name` varchar(64) NOT NULL,
		  `description` text NOT NULL,
		  PRIMARY KEY (`id`),
		  KEY (`name`)
		) ENGINE=InnoDB DEFAULT CHARSET=utf8 AUTO_INCREMENT=2""")

		cursor.execute("""CREATE TABLE IF NOT EXISTS `role_perms` (
		  `id` mediumint(11) NOT NULL AUTO_INCREMENT,
		  `role_id` mediumint(11) NOT NULL,
		  `perm` varchar(64) NOT NULL,
		  PRIMARY KEY (`id`),
		  UNIQUE (`role_id`, `perm`),
		  CONSTRAINT `role_perms_ibfk_1` FOREIGN KEY (`role_id`) REFERENCES `roles` (`id`) ON DELETE CASCADE
		) ENGINE=InnoDB DEFAULT CHARSET=utf8""")

		cursor.execute("""CREATE TABLE IF NOT EXISTS `role_who` (
		  `id` mediumint(11) NOT NULL AUTO_INCREMENT,
		  `role_id` mediumint(11) NOT NULL,
		  `who` varchar(128) NOT NULL,
		  `type` tinyint(1) NOT NULL,
		  PRIMARY KEY (`id`),
		  UNIQUE (`role_id`, `who`, `type`),
		  CONSTRAINT `role_who_ibfk_1` FOREIGN KEY (`role_id`) REFERENCES `roles` (`id`) ON DELETE CASCADE
		) ENGINE=InnoDB DEFAULT CHARSET=utf8""")

		cursor.execute("""CREATE TABLE IF NOT EXISTS `system_perms` (
		  `id` mediumint(11) NOT NULL AUTO_INCREMENT,
		  `system_id` mediumint(11) NOT NULL,
		  `who` varchar(128) NOT NULL,
		  `type` tinyint(1) NOT NULL,
		  `perm` varchar(64) NOT NULL,
		  PRIMARY KEY (`id`),
		  UNIQUE (`system_id`, `who`, `type`, `perm`),
		  CONSTRAINT `system_perms_ibfk_1` FOREIGN KEY (`system_id`) REFERENCES `systems` (`id`) ON DELETE CASCADE
		) ENGINE=InnoDB DEFAULT CHARSET=utf8""")

		cursor.execute("""CREATE TABLE IF NOT EXISTS `system_roles` (
		  `id` mediumint(11) NOT NULL AUTO_INCREMENT,
		  `name` varchar(64) NOT NULL,
		  `description` text NOT NULL,
		  PRIMARY KEY (`id`),
		  KEY (`name`)
		) ENGINE=InnoDB DEFAULT CHARSET=utf8""")

		cursor.execute("""CREATE TABLE IF NOT EXISTS `system_role_perms` (
		  `id` mediumint(11) NOT NULL AUTO_INCREMENT,
		  `system_role_id` mediumint(11) NOT NULL,
		  `perm` varchar(64) NOT NULL,
		  PRIMARY KEY (`id`),
		  UNIQUE (`system_role_id`, `perm`),
		  CONSTRAINT `system_role_perms_ibfk_1` FOREIGN KEY (`system_role_id`) REFERENCES `system_roles` (`id`) ON DELETE CASCADE
		) ENGINE=InnoDB DEFAULT CHARSET=utf8""")

		cursor.execute("""CREATE TABLE IF NOT EXISTS `system_role_who` (
		  `id` mediumint(11) NOT NULL AUTO_INCREMENT,
		  `system_role_id` mediumint(11) NOT NULL,
		  `who` varchar(128) NOT NULL,
		  `type` tinyint(1) NOT NULL,
		  PRIMARY KEY (`id`),
		  UNIQUE (`system_role_id`, `who`, `type`),
		  CONSTRAINT `system_role_who_ibfk_1` FOREIGN KEY (`system_role_id`) REFERENCES `system_roles` (`id`) ON DELETE CASCADE
		) ENGINE=InnoDB DEFAULT CHARSET=utf8""")

		cursor.execute("""CREATE TABLE IF NOT EXISTS `system_role_what` (
		  `system_role_id` mediumint(11) NOT NULL,
		  `system_id` mediumint(11) NOT NULL,
		  PRIMARY KEY (`system_role_id`, `system_id`),
		  CONSTRAINT `system_role_what_ibfk_1` FOREIGN KEY (`system_role_id`) REFERENCES `system_roles` (`id`) ON DELETE CASCADE,
		  CONSTRAINT `system_role_what_ibfk_2` FOREIGN KEY (`system_id`) REFERENCES `systems` (`id`) ON DELETE CASCADE
		) ENGINE=InnoDB DEFAULT CHARSET=utf8""")

		cursor.execute("""CREATE OR REPLACE VIEW `system_role_perms_view` AS
		SELECT DISTINCT 
		  `system_roles`.`id` as `system_role_id`,
		  `system_roles`.`name` as `system_role_name`,
		  `system_role_what`.`system_id`,
		  `system_role_who`.`who`,
		  `system_role_who`.`type`,
		  `system_role_perms`.`perm`
		FROM `system_roles`
		LEFT JOIN `system_role_perms` ON `system_roles`.`id`=`system_role_perms`.`system_role_id`
		LEFT JOIN `system_role_who` ON `system_roles`.`id`=`system_role_who`.`system_role_id`
		LEFT JOIN `system_role_what` ON `system_roles`.`id`=`system_role_what`.`system_role_id`
		WHERE 
		  `system_role_what`.`system_id` IS NOT NULL AND
		  `system_role_who`.`who` IS NOT NULL AND
		  `system_role_who`.`type` IS NOT NULL AND
		  `system_role_perms`.`perm` IS NOT NULL
		""")

		cursor.execute("""CREATE OR REPLACE VIEW `system_perms_view` AS
		SELECT DISTINCT
		  `system_role_perms_view`.`system_id`,
		  `system_role_perms_view`.`who`,
		  `system_role_perms_view`.`type`,
		  `system_role_perms_view`.`perm`
		FROM `system_role_perms_view`
		UNION
		SELECT DISTINCT
		  `system_perms`.`system_id`,
		  `system_perms`.`who`,
		  `system_perms`.`type`,
		  `system_perms`.`perm`
		FROM `system_perms`;
		""")

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

		cursor.execute("""DROP TABLE IF EXISTS `workflow_perms`""")

		# Ensure we have a default administrator role with appropriate permissions
		cursor.execute("""INSERT IGNORE INTO `roles` (`id`, `name`, `description`) VALUES (1, "Administrator", "Has full access to everything")""")
		cursor.execute("""INSERT IGNORE INTO `role_perms` (`role_id`, `perm`) VALUES 
		  (1, "admin.permissions"), 
		  (1, "systems.all.view"), 
		  (1, "systems.all.view.puppet"), 
		  (1, "systems.all.view.puppet.catalog"), 
		  (1, "systems.all.view.rubrik"),
		  (1, "systems.all.edit.expiry"), 
		  (1, "systems.all.edit.review"), 
		  (1, "systems.all.edit.vmware"), 
		  (1, "systems.all.edit.cmdb"), 
		  (1, "systems.all.edit.comment"), 
		  (1, "systems.all.edit.puppet"),
		  (1, "systems.all.edit.rubrik"), 
		  (1, "systems.all.edit.owners"), 
		  (1, "systems.allocate_name"), 
		  (1, "systems.add_existing"),
		  (1, "vmware.view"), 
		  (1, "puppet.dashboard.view"), 
		  (1, "puppet.nodes.view"), 
		  (1, "puppet.default_classes.view"), 
		  (1, "puppet.default_classes.edit"), 
		  (1, "classes.view"), 
		  (1, "classes.edit"), 
		  (1, "tasks.view"),
		  (1, "events.view"),
		  (1, "specs.view"),
		  (1, "specs.edit"),
		  (1, "maintenance.vmware"), 
		  (1, "maintenance.cmdb"), 
		  (1, "maintenance.expire_vm"),
		  (1, "maintenance.sync_puppet_servicenow"),
		  (1, "maintenance.cert_scan"),
		  (1, "maintenance.student_vm"),
		  (1, "api.register"),
		  (1, "workflows.all"),
		  (1, "sysrequests.all.view"),
		  (1, "sysrequests.all.approve"),
		  (1, "sysrequests.all.reject"),
		  (1, "api.get"),
		  (1, "api.post"),
		  (1, "api.put"),
		  (1, "api.delete"),
		  (1, "certificates.view"),
		  (1, "certificates.stats"),
		  (1, "certificates.add")
		""")

		## Close database connection
		temp_db.close()

		self.logger.info("Database initialisation complete")

################################################################################

	def init_permissions(self):
		"""Sets up the list of permissions that can be assigned, must be run
		before workflows are run"""

		## The ORDER MATTERS! It determines the order used on the Roles page
		self.permissions        = [
			{'name': 'systems.all.view',		       'desc': 'View any system'},
			{'name': 'systems.own.view',		       'desc': 'View systems allocated by the user'},
			{'name': 'systems.all.view.puppet',	       'desc': 'View Puppet reports and facts on any system'},
			{'name': 'systems.all.view.puppet.classify',   'desc': 'View Puppet classify on any system'},
			{'name': 'systems.all.view.puppet.catalog',    'desc': 'View Puppet catalog on any system'},
			{'name': 'systems.all.view.rubrik',            'desc': 'View Rubrik backups for any system'},
			{'name': 'systems.all.edit.expiry',	       'desc': 'Modify the expiry date of any system'},
			{'name': 'systems.all.edit.review',	       'desc': 'Modify the review status of any system'},
			{'name': 'systems.all.edit.vmware',	       'desc': 'Modify the VMware link on any system'},
			{'name': 'systems.all.edit.cmdb',	       'desc': 'Modify the CMDB link on any system'},
			{'name': 'systems.all.edit.comment',	       'desc': 'Modify the comment on any system'},
			{'name': 'systems.all.edit.puppet',	       'desc': 'Modify Puppet settings on any system'},
			{'name': 'systems.all.edit.rubrik',            'desc': 'Modify Rubrik settings on any system'},
			{'name': 'systems.all.edit.owners',            'desc': 'Modify the system owners on any system'},
			{'name': 'vmware.view',			       'desc': 'View VMware data and statistics'},
			{'name': 'puppet.dashboard.view',	       'desc': 'View the Puppet dashboard'},
			{'name': 'puppet.nodes.view',		       'desc': 'View the list of Puppet nodes'},
			{'name': 'puppet.default_classes.view',	       'desc': 'View the list of Puppet default classes'},
			{'name': 'puppet.default_classes.edit',	       'desc': 'Modify the list of Puppet default classes'},
			{'name': 'classes.view',		       'desc': 'View the list of system class definitions'},
			{'name': 'classes.edit',		       'desc': 'Edit system class definitions'},
			{'name': 'tasks.view',			       'desc': 'View the details of all tasks (not just your own)'},
			{'name': 'events.view',			       'desc': 'View the details of all events (not just your own)'},
			{'name': 'specs.view',			       'desc': 'View the VM Specification Settings'},
			{'name': 'specs.edit',			       'desc': 'Edit the VM Specification Settings'},
			{'name': 'maintenance.vmware',		       'desc': 'Run VMware maintenance tasks'},
			{'name': 'maintenance.cmdb',		       'desc': 'Run CMDB maintenance tasks'},
			{'name': 'maintenance.expire_vm',	       'desc': 'Run the Expire VM maintenance task'},
			{'name': 'maintenance.sync_puppet_servicenow', 'desc': 'Run the Sync Puppet with Servicenow task'},
			{'name': 'maintenance.cert_scan',              'desc': 'Run the Certificate Scan task'},
			{'name': 'maintenance.student_vm',             'desc': 'Run the Student VM Build Task'},
			{'name': 'api.register',		       'desc': 'Manually register Linux machines (rebuilds / physical machines)'},
			{'name': 'admin.permissions',		       'desc': 'Modify permissions'},
			{'name': 'workflows.all',		       'desc': 'Use any workflow or workflow function'},

			{'name': 'sysrequests.own.view',	       'desc': 'View system requests owned by the user'},
			{'name': 'sysrequests.all.view',	       'desc': 'View any system request'},
			{'name': 'sysrequests.all.approve',	       'desc': 'Approve any system request'},
			{'name': 'sysrequests.all.reject',	       'desc': 'Reject any system request'},
			{'name': 'control.all.vmware.power',	       'desc': 'Contol the power settings of any VM'},

			{'name': 'api.get',			       'desc': 'Send GET requests to the Cortex API.'},
			{'name': 'api.post',			       'desc': 'Send POST requests to the Cortex API.'},
			{'name': 'api.put',			       'desc': 'Send PUT requests to the Cortex API.'},
			{'name': 'api.delete',			       'desc': 'Send DELETE requests to the Cortex API.'},

			{'name': 'certificates.view',                  'desc': 'View the list of discovered certificates and their details'},
			{'name': 'certificates.stats',                 'desc': 'View the statistics about certificates'},
			{'name': 'certificates.add',                   'desc': 'Adds a certificate to the list of tracked certificates'},
		]

		self.workflow_permissions = []

		self.system_permissions = [
			{'name': 'view.overview',               'desc': 'View the system overview'},
			{'name': 'view.detail',                 'desc': 'View the system details'},
			{'name': 'view.puppet',                 'desc': 'View the system\'s Puppet reports and facts'},
			{'name': 'view.puppet.classify',        'desc': 'View the system\'s Puppet classification'},
			{'name': 'view.puppet.catalog',         'desc': 'View the system\'s Puppet catalog'},
			{'name': 'edit.expiry',                 'desc': 'Change the expiry date of the system'},
			{'name': 'edit.review',                 'desc': 'Change the review status of the system'},
			{'name': 'edit.vmware',                 'desc': 'Change the VMware VM link'},
			{'name': 'edit.cmdb',                   'desc': 'Change the CMDB link'},
			{'name': 'edit.comment',                'desc': 'Change the comment'},
			{'name': 'edit.owners',                 'desc': 'Change the system owners'},
			{'name': 'edit.puppet',                 'desc': 'Change Puppet settings'},
			{'name': 'control.vmware.power',        'desc': 'Control the VMware power state'},
		]
