from flask import request, session
from flask_restplus import Resource
import math

from cortex import app
from cortex.api import api_manager, api_login_required
from cortex.api.exceptions import InvalidPermissionException, NoResultsFoundException
from cortex.api.parsers import puppet_post_args, puppet_info_root, puppet_info_module, puppet_info_class, puppet_info_parameter, puppet_info_description, puppet_info_tag
from cortex.api.serializers.puppet import page_puppet_serializer, puppet_serializer

from cortex.lib.user import does_user_have_permission
import cortex.lib.core

puppet_modules_info_namespace = api_manager.namespace('puppet', description='Puppet API')
@puppet_modules_info_namespace.route('/modules_info')
class Puppet(Resource):
	"""
	API Handler for POST requests
	"""
	@api_login_required('post')
	@app.disable_csrf_check
	@api_manager.expect(puppet_info_root)
	def post(self):
		
		root = puppet_info_root.parse_args(request)
		modules = puppet_info_module.parse_args(req=root)
		classes = puppet_info_class.parse_args(req=modules)
		parameters = puppet_info_parameter.parse_args(req=classes)
		
		if not does_user_have_permission("puppet.modules_info.add"):
			raise InvalidPermissionException
		return root
