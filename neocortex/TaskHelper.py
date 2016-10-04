#!/usr/bin/python

import Pyro4
import syslog
import signal
import os
import imp
import MySQLdb as mysql
import sys
import requests
import json
import time
from setproctitle import setproctitle #pip install setproctitle
from corpus import Corpus

class TaskHelper(object):

	def __init__(self, config, workflow_name, task_id, username):
		self.config        = config
		self.workflow_name = workflow_name
		self.task_id       = task_id
		self.username      = username
		self.event_id      = -1

	def _signal_handler(self, signal, frame):
		syslog.syslog('task id ' + str(self.task_id) + ' caught exit signal')

		self.end_event(success=False)
		self.event('neocortex.shutdown','The task was terminated because neocortex was asked to shutdown')
		self._end_task(success=False)

		syslog.syslog('task id ' + str(self.task_id) + ' marked as finished')
		sys.exit(0)

	def run(self, task_module, options):

		## Set up signal handlers to mark the task as error'ed
		signal.signal(signal.SIGTERM, self._signal_handler)
		signal.signal(signal.SIGINT, self._signal_handler)

		self.db   = self.db_connect()
		self.curd = self.db.cursor(mysql.cursors.DictCursor)
		self.lib  = Corpus(self.db, self.config)

		## Set the process name
		setproctitle("neocortex task ID " + str(self.task_id) + " " + self.workflow_name)

		try:
			task_module.run(self, options)
			self._end_task()
		except self.lib.TaskFatalError as ex:
			self._log_fatal_error("The task failed: " + str(ex))
			self._end_task(success=False)
		except self.lib.VMwareTaskError as ex:
			self._log_fatal_error("The task failed because VMware returned an error: " + str(ex))
			self._end_task(success=False)
		except Exception as ex:
			self._log_exception(ex)
			self._end_task(success=False)

	def db_connect(self):
		return mysql.connect(self.config['MYSQL_HOST'], self.config['MYSQL_USER'], self.config['MYSQL_PASS'], self.config['MYSQL_NAME'], charset='utf8')

	def _log_exception(self, ex):
		exception_type = str(type(ex).__name__)
		exception_message = str(ex)
		self.curd.execute("INSERT INTO `events` (`source`, `related_id`, `name`, `username`, `desc`, `status`, `start`, `end`) VALUES (%s, %s, %s, %s, %s, 2, NOW(), NOW())", 
			('neocortex.task',self.task_id, self.workflow_name + "." + 'exception', self.username, "The task failed because an exception was raised: " + exception_type + " - " + exception_message))
		self.db.commit()

	def _log_fatal_error(self, message):
		self.curd.execute("INSERT INTO `events` (`source`, `related_id`, `name`, `username`, `desc`, `status`, `start`, `end`) VALUES (%s, %s, %s, %s, %s, 2, NOW(), NOW())", 
			('neocortex.task',self.task_id, self.workflow_name + "." + 'exception', self.username, message))
		self.db.commit()

	def event(self, name, description, success=True, oneshot=False):
		# Handle closing an existing event if there is still one
		if self.event_id != -1:
			self.end_event(success)

		name = self.workflow_name + "." + name
		self.curd.execute("INSERT INTO `events` (`source`, `related_id`, `name`, `username`, `desc`, `start`) VALUES (%s, %s, %s, %s, %s, NOW())", ('neocortex.task', self.task_id, name, self.username, description))
		self.db.commit()
		self.event_id = self.curd.lastrowid

		if oneshot:
			self.end_event(success=success)

		return True

	def update_event(self, description):
		if self.event_id == -1:
			return False

		self.curd.execute("UPDATE `events` SET `desc` = %s WHERE `id` = %s", (description, self.event_id))
		self.db.commit()

		return True

	def end_event(self, success=True, description=None):
		if self.event_id == -1:
			return False

		if not description == None:
			self.update_event(description)

		if success:
			status = 1
		else:
			status = 2 

		self.curd.execute("UPDATE `events` SET `status` = %s, `end` = NOW() WHERE `id` = %s", (status, self.event_id))
		self.db.commit()
		self.event_id = -1

		return True

	def _end_task(self, success=True):
		# Handle closing an existing event if there is still one
		if self.event_id != -1:
			self.end_event(success)

		if success:
			status = 1
		else:
			status = 2 

		self.curd.execute("UPDATE `tasks` SET `status` = %s, `end` = NOW() WHERE `id` = %s", (status, self.task_id))
		self.db.commit()
