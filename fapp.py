#!/usr/bin/python
#

from flask import Flask, request, session
import jinja2 
import os.path
from os import walk
#from ConfigParser import RawConfigParser 
import imp

class CortexFlask(Flask):

	workflows = []

#	def load_workflows(self):
#		"""Attempts to load the workflow config files from the workflows directory
#		which is defined in app.config['WORKFLOWS_DIR']. Each config file is loaded
#		and the display name stored"""
#
#		## list all entries in the directory
#		if not os.path.isdir(self.config['WORKFLOWS_DIR']):
#			self.logger.error("The config option WORKFLOWS_DIR is not a directory!")
#			return
#
#		for (dirpath, dirnames, filenames) in walk(self.config['WORKFLOWS_DIR']):
#			if len(filenames) == 0:
#				self.logger.warn("The WORKFLOWS_DIR directory is empty, no workflows could be loaded!")
#
#			for filename in filenames:
#				fname = os.path.join(self.config['WORKFLOWS_DIR'],filename)
#				try:
#					config = RawConfigParser()
#					config.read(fname)
#					if not config.has_option("main","display"):
#						self.logger.warn("The workflow in " + fname + " does not have a display name, not loading")
#					else:
#						self.logger.info("Loaded workflow '" + config.get("main","display") + "' from " + fname)
#						self.workflows.append({'config': config, 'display': config.get("main","display"), 'name': filename.replace(".ini","") })
#
#				except Exception as ex:
#					self.logger.warn("Could not load workflow from file " + fname + ": " + str(ex))

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
			fqp = os.path.join(self.config['WORKFLOWS_DIR'],entry)

			if os.path.isdir(fqp):
				## this is or rather should be a workflow directory
				found = True
				views_file = os.path.join(fqp,"views.py")
				try:
					view_module = imp.load_source(entry, views_file)
					self.workflows.append({'config': {}, 'display': 'changeme', 'name': entry })
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
		


	def load_user_templates(self):
		if self.config['LOCAL_TEMPLATE_DIR']:
			choice_loader = jinja2.ChoiceLoader(
			[
				jinja2.FileSystemLoader(self.config['LOCAL_TEMPLATE_DIR']),
				self.jinja_loader,
			])
			self.jinja_loader = choice_loader
			self.logger.info('bargate will load templates from local source: ' + str(self.config['LOCAL_TEMPLATE_DIR']))			


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

