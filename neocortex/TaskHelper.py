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

	# Task / Event statuses
	STATUS_PROGRESS = 0
	STATUS_SUCCESS  = 1
	STATUS_FAILED   = 2
	STATUS_WARNED   = 3

	# Flash Message Category Map
	CATEGORY_MAP = {
		'message': { 'success': True, 'warning': False },
		'success': { 'success': True, 'warning': False },
		'warning': { 'success': True, 'warning': True },
		'error'  : { 'success': False, 'warning': False },
		'fatal'  : { 'success': False, 'warning': False },
	}
	
	def __init__(self, config, workflow_name, task_id, username):
		"""Initialises the TaskHelper object"""

		self.config         = config
		self.workflow_name  = workflow_name
		self.task_id        = task_id
		self.username       = username
		self.event_id       = -1
		self.event_problems = 0

	def _signal_handler(self, signal, frame):
		"""Marks task and event as failed when interrupted by a signal, and then exits"""

		syslog.syslog('task id ' + str(self.task_id) + ' caught exit signal')

		self.end_event(success=False)
		self.event('neocortex.shutdown','The task was terminated because neocortex was asked to shutdown')
		self._end_task(success=False)

		syslog.syslog('task id ' + str(self.task_id) + ' marked as finished')
		sys.exit(0)

	def run(self, task_module, options):
		"""Runs the task, passing this object to the task to provide access to
		library routines and configuration options. Handles task closures and
		SIGINT/SIGTERM signals ending tasks prematurely."""

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
		"""Returns a connection to the Cortex database"""

		return mysql.connect(self.config['MYSQL_HOST'], self.config['MYSQL_USER'], self.config['MYSQL_PASS'], self.config['MYSQL_NAME'], charset='utf8')

	def _log_exception(self, ex):
		"""Logs an exception into the events for this task"""

		exception_type = str(type(ex).__name__)
		exception_message = str(ex)
		self.curd.execute("INSERT INTO `events` (`source`, `related_id`, `name`, `username`, `desc`, `status`, `start`, `end`) VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())", 
			('neocortex.task',self.task_id, self.workflow_name + "." + 'exception', self.username, "The task failed because an exception was raised: " + exception_type + " - " + exception_message, self.STATUS_FAILED))
		self.db.commit()

	def _log_fatal_error(self, message):
		"""Logs a fatal error into the events for this task"""

		self.curd.execute("INSERT INTO `events` (`source`, `related_id`, `name`, `username`, `desc`, `status`, `start`, `end`) VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())", 
			('neocortex.task',self.task_id, self.workflow_name + "." + 'exception', self.username, message, self.STATUS_FAILED))
		self.db.commit()

	def event(self, name, description, success=True, oneshot=False, warning=False):
		"""Starts a new event within the tasks, closing an existing one if there was one"""

		# Handle closing an existing event if there is still one
		if self.event_id != -1:
			self.end_event(success=success, warning=warning)

		name = self.workflow_name + "." + name
		self.curd.execute("INSERT INTO `events` (`source`, `related_id`, `name`, `username`, `desc`, `start`) VALUES (%s, %s, %s, %s, %s, NOW())", ('neocortex.task', self.task_id, name, self.username, description))
		self.db.commit()
		self.event_id = self.curd.lastrowid

		if oneshot:
			self.end_event(success=success, warning=warning)

		return True

	def update_event(self, description):
		"""Updates the description of the currently running event"""

		if self.event_id == -1:
			return False

		self.curd.execute("UPDATE `events` SET `desc` = %s WHERE `id` = %s", (description, self.event_id))
		self.db.commit()

		return True

	def end_event(self, success=True, description=None, warning=False):
		"""Ends the currently running event, updating it's description and status as necessary"""

		if self.event_id == -1:
			return False

		if not description == None:
			self.update_event(description)

		if success:
			if warning:
				# Keep count of events with warnings/failures
				self.event_problems += 1
				status = self.STATUS_WARNED
			else:
				status = self.STATUS_SUCCESS
		else:
			# Keep count of events with warnings/failures
			self.event_problems += 1
			status = self.STATUS_FAILED

		self.curd.execute("UPDATE `events` SET `status` = %s, `end` = NOW() WHERE `id` = %s", (status, self.event_id))
		self.db.commit()
		self.event_id = -1

		return True

	def _end_task(self, success=True):
		"""End the tasks, updaing it's status as appropriate. If any events within the
		task failed, this will mark the tasks as finishing with warnings even if the
		task succeeds"""

		# Handle closing an existing event if there is still one
		if self.event_id != -1:
			self.end_event(success)

		if success:
			# If we had one or more task event failures, then end the task
			# with warnings rather than a complete success
			if self.event_problems > 0:
				status = self.STATUS_WARNED
			else:
				status = self.STATUS_SUCCESS
		else:
			status = self.STATUS_FAILED

		self.curd.execute("UPDATE `tasks` SET `status` = %s, `end` = NOW() WHERE `id` = %s", (status, self.task_id))
		self.db.commit()
		self.event_problems = 0

	def get_problem_count(self):
		"""Returns the number of events within the task that have failed or finished with warnings."""

		return self.event_problems

	def flash(self, message, category='message'):
		"""Wrapper for oneshot events to create a Flask flashing-like method."""

		name = 'decom.flash.{}'.format(category.lower())
		self.event(
			name,
			message,
			oneshot=True,
			success=self.CATEGORY_MAP.get(category.lower(), self.CATEGORY_MAP['message'])['success'],
			warning=self.CATEGORY_MAP.get(category.lower(), self.CATEGORY_MAP['message'])['warning'],
		)

		# Fatal errors raise runtime errors.
		if category.lower() == 'fatal':
			raise RuntimeError(message)

