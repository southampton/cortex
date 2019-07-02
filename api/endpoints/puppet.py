from flask import request, session, jsonify, g
from flask_restplus import Resource
import math
import json
from cortex import app
from cortex.api import api_manager, api_login_required
from cortex.api.exceptions import InvalidPermissionException, NoResultsFoundException
from cortex.api.serializers.puppet import page_puppet_serializer, puppet_serializer

from cortex.lib.user import does_user_have_permission
import cortex.lib.core
import MySQLdb as mysql




puppet_modules_info_namespace = api_manager.namespace('puppet', description='Puppet API')
@puppet_modules_info_namespace.route('/modules_info')
class Puppet(Resource):
	"""
	API Handler for POST requests
	"""
	
	# User must be logged in and the csrf_check is not applied as there is no csrf token
	# being passed
	# @api_login_required('post')
	@app.disable_csrf_check
	def post(self):
		
		# If the user does not have permission to add data to the table, raise InvalidPermission
		if 'X-Auth-Token' not in request.headers:
			app.logger.warn("auth_token missing from the request")
			raise MissingAuthenticationTokenException
		if request.headers['X-Auth-Token'] != app.config['CORTEX_API_AUTH_TOKEN']:
			app.logger.warn('Incorrect auth_token on request to Systems API')
			raise InvalidPermissionException
		
		
		# Read the request data
		outcome = request.json
		# Get the database cursor
		curd = g.db.cursor(mysql.cursors.DictCursor)
        	# Turn off autocommit cause a lot of insertions are going to be used
		curd.connection.autocommit(False)
		# Delete and rewrite all the table data (simpler and faster than updating) 
		curd.execute("TRUNCATE TABLE `puppet_modules_info`;")
		for module_list in request.json['puppet_classes']:
			for module in module_list:
				if "::" in module['name']:
					module_name = module['name'].split("::")[0]
					class_name = module['name'].split("::")[1]
				else:
					module_name = module['name']
					class_name = "init"
				if 'docstring' in module.keys():
					for tag in module['docstring']['tags']:
						class_parameter = tag['name']
						description = tag['text']
						tag_name = tag['tag_name']
						curd.execute("INSERT INTO `puppet_modules_info` (`module_name`, `class_name`, `class_parameter`, `description`, `tag_name`) VALUES (%s, %s, %s, %s, %s)", (module_name, class_name, class_parameter, description, tag_name))
		# commit the changes		
		curd.connection.commit()

