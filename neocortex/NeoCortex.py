#!/usr/bin/python

import Pyro4
import syslog
import signal
import os
import imp
import multiprocessing
from multiprocessing import Process, Value
import MySQLdb as mysql
import sys
import requests
import json
import time

from NeoCortexLib import NeoCortexLib
from TaskHelper import TaskHelper

CONFIG_FILE = '/data/cortex/cortex.conf'
Pyro4.config.SERVERTYPE = "multiplex"
Pyro4.config.SOCK_REUSE = True

class NeoCortex(object):

	debug = False
	db    = None
	pyro  = None

	## PRIVATE METHODS #########################################################

	def __init__(self, pyro):
		syslog.openlog("neocortex", syslog.LOG_PID)

		## Load the config and drop privs
		self._load_config(CONFIG_FILE)
		self._drop_privs()

		## Store the copy of the pyro daemon object
		self.pyro = pyro

		## Set up signal handlers
		signal.signal(signal.SIGTERM, self._signal_handler_term)
		signal.signal(signal.SIGINT, self._signal_handler_int)

		## preload a connection to mysql
		self._get_db()

	def _signal_handler_term(self, signal, frame):
		self._signal_handler('SIGTERM')
	
	def _signal_handler_int(self, signal, frame):
		self._signal_handler('SIGINT')
	
	def _signal_handler(self, signal):
		#global pyro_daemon
		syslog.syslog('neocortex caught signal ' + str(signal))

		## Mark each task as terminated
		curd = self._get_cursor()

		## get child processes		
		active_processes = multiprocessing.active_children()

		for proc in active_processes:
			syslog.syslog('marking task ' + proc.name + " as finished")
			task_id = int(proc.name)
			## mark the task as finished (error)
			curd.execute("UPDATE `tasks` SET `status` = 2, `end` = NOW() WHERE `id` = %s", (task_id))
			## close any events with an error
			curd.execute("UPDATE `events` SET `status` = 2, `end` = NOW() WHERE `source` = 'neocortex.task' AND `related_id` = %s AND `status` = 0", (task_id))
			## insert an event to say that it was terminated due to neocortex stopping
			curd.execute("INSERT INTO `events` (`source`, `related_id`, `name`, `username`, `desc`, `status`, `start`, `end`) VALUES (%s, %s, %s, %s, %s, 2, NOW(), NOW())", 
			('neocortex.task', task_id, "neocortex.shutdown", "system", "The task was terminated because neocortex was asked to shutdown"))
			self.db.commit()

		Pyro4.core.Daemon.shutdown(self.pyro)
		syslog.syslog('neocortex exited')
		sys.exit(0)

	def _get_cursor(self):
		self._get_db()
		return self.db.cursor(mysql.cursors.DictCursor)

	def _get_db(self):
		if self.db:
			if self.db.open:
				try:
					curd = self.db.cursor(mysql.cursors.DictCursor)
					curd.execute('SELECT 1')
					result = curd.fetchone();

					if result:
						return self.db

				except (AttributeError, mysql.OperationalError):
					syslog.syslog("MySQL connection is closed, will attempt reconnect")

		## If we didn't return up above then we need to connect first
		return self._db_connect()
		
	def _db_connect(self):
		syslog.syslog("Attempting connection to MySQL")
		self.db = mysql.connect(self.config['MYSQL_HOST'], self.config['MYSQL_USER'], self.config['MYSQL_PASS'], self.config['MYSQL_NAME'], charset='utf8')
		curd = self.db.cursor(mysql.cursors.DictCursor)
		curd.execute("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED")
		syslog.syslog("Connection to MySQL established")
		return self.db

	def _load_config(self, filename): 
		d = imp.new_module('config')
		d.__file__ = filename
		try:
			with open(filename) as config_file:
				exec(compile(config_file.read(), filename, 'exec'), d.__dict__)
		except IOError as e:
			syslog.syslog('Unable to load configuration file (%s)' % e.strerror)
			sys.exit(1)
		self.config = {}
		for key in dir(d):
			if key.isupper():
				self.config[key] = getattr(d, key)

		## ensure we have required config options
		for wkey in ['NEOCORTEX_SET_GID', 'NEOCORTEX_SET_UID', 'NEOCORTEX_KEY', 'WORKFLOWS_DIR']:
			if not wkey in self.config.keys():
				print "Missing configuation option: " + wkey
				sys.exit(1)

		if 'DEBUG' in self.config.keys():
			if self.config['DEBUG'] == True:
				self.debug = True
				
		return True

	def _drop_privs(self):
		## Drop privileges, looking up the UID/GID if not given numerically
		if str(self.config['NEOCORTEX_SET_GID']).isdigit():
			os.setgid(self.config['NEOCORTEX_SET_GID'])
		else:
			import grp
			os.setgid(grp.getgrnam(self.config['NEOCORTEX_SET_GID']).gr_gid)

		if str(self.config['NEOCORTEX_SET_UID']).isdigit():
			os.setuid(self.config['NEOCORTEX_SET_UID'])
		else:
			import pwd
			os.setuid(pwd.getpwnam(self.config['NEOCORTEX_SET_UID']).pw_uid)

	def _record_task(self, module_name, username, description=None):
		curd = self._get_cursor()
		curd.execute("INSERT INTO `tasks` (`module`, `username`, `start`, `description`) VALUES (%s, %s, NOW(), %s)", (module_name, username, description))
		self.db.commit()
		return curd.lastrowid

	## RPC METHODS #############################################################

	def ping(self):
		return True

	#### this function is used to submit jobs/tasks.
	## workflow_name - the name of the workflow to start
	## username - who submitted this task
	## options - a dictionary of arguments for the method.
	## description - an optional description of the task
	def create_task(self, workflow_name, username, options, description=None):

		if not os.path.isdir(self.config['WORKFLOWS_DIR']):
			raise IOError("The config option WORKFLOWS_DIR is not a directory")

		fqp = os.path.join(self.config['WORKFLOWS_DIR'], workflow_name)

		if not os.path.exists(fqp):
			raise IOError("The workflow directory was not found")

		if not os.path.isdir(fqp):
			raise IOError("The workflow name was not a directory")

		task_file = os.path.join(fqp,"task.py")
		try:
			task_module = imp.load_source(workflow_name, task_file)
		except Exception as ex:
			raise ImportError("Could not load workflow from file " + task_file + ": " + str(ex))

		task_id      = self._record_task(workflow_name, username, description)
		task_helper  = TaskHelper(self.config, workflow_name, task_id, username)
		task         = Process(target=task_helper.run, args=(task_module, options), name=str(task_id))
		task.start()

		syslog.syslog('started task workflow/' + workflow_name + ' with task id ' + str(task_id) + ' and worker pid ' + str(task.pid))

		return task_id

	## This function allows arbitrary taks to be called
	def start_internal_task(self, username, task_file, task_name, options=None, description=None):
		try:
			task_module = imp.load_source(task_name, task_file)
		except Exception as ex:
			raise ImportError("Could not load internal task from file " + task_file + ": " + str(ex))

		task_id      = self._record_task(task_name, username, description)
		task_helper  = TaskHelper(self.config, task_name, task_id, username)
		task         = Process(target=task_helper.run, args=(task_module, options), name=str(task_id))
		task.start()

		syslog.syslog('started task internal/' + task_name + ' with task id ' + str(task_id) + ' and worker pid ' + str(task.pid))

		return task_id

	## This function allows the Flask web app to allocate names (as well as tasks)
	def allocate_name(self, class_name, system_comment, username, num):
		lib = NeoCortexLib(self._get_db(), self.config)
		return lib.allocate_name(class_name, system_comment, username, num)

	## List active tasks - returns a list of task ids
	def active_tasks(self):
		active_processes = multiprocessing.active_children()
		active_tasks = []
		for proc in active_processes:
			active_tasks.append(int(proc.name))

		return active_tasks
		
