from flask import request, session
from flask_restx import Resource

import cortex.lib.systems
from cortex.api import api_login_required, api_manager
from cortex.api.exceptions import (
	InvalidPermissionException, NoResultsFoundException)
from cortex.api.parsers import (
	pagination_arguments, process_pagination_arguments, pagination_response)
from cortex.api.serializers.systems_info_view import (
	page_systems_info_view_serializer, systems_info_view_serializer)
from cortex.lib.user import (
	does_user_have_permission, does_user_have_system_permission)

systems_info_view_namespace = api_manager.namespace('systems_info_view', description='System\'s Info View API')

# pylint: disable=no-self-use
@systems_info_view_namespace.route('/')
class SystemsInfoViewCollection(Resource):

	"""
	API Handler for multiple rows from the systems_info_view.
	"""

	@api_login_required('get')
	@api_manager.expect(pagination_arguments)
	@api_manager.marshal_with(page_systems_info_view_serializer, mask='{page,pages,per_page,total,items{id,name}}')
	def get(self):
		"""
		Returns a paginated list of rows from the systems_info_view.
		"""

		page, per_page, limit_start, limit_length = process_pagination_arguments(request)

		if not (does_user_have_permission("systems.all.view") or does_user_have_permission("systems.own.view")):
			raise InvalidPermissionException

		class_name = None
		hide_inactive = False
		only_other = False
		show_expired = False
		show_nocmdb = False
		show_allocated_and_perms = False

		if does_user_have_permission("systems.all.view"):
			only_allocated_by = None
		else:
			# Show the systems where the user has permissions AND the ones they allocated.
			show_allocated_and_perms = True
			if request.authorization:
				only_allocated_by = request.authorization.username
			else:
				if 'username' in session:
					only_allocated_by = session['username']
				else:
					raise InvalidPermissionException

		total = cortex.lib.systems.get_system_count(class_name=class_name, hide_inactive=hide_inactive, only_other=only_other, show_expired=show_expired, show_nocmdb=show_nocmdb, show_allocated_and_perms=show_allocated_and_perms, only_allocated_by=only_allocated_by)
		results = cortex.lib.systems.get_systems(class_name=class_name, order='id', limit_start=limit_start, limit_length=limit_length, hide_inactive=hide_inactive, only_other=only_other, show_expired=show_expired, show_nocmdb=show_nocmdb, show_allocated_and_perms=show_allocated_and_perms, only_allocated_by=only_allocated_by)

		return pagination_response(results, page, per_page, total)

@systems_info_view_namespace.route('/<int:system_id>')
@api_manager.response(404, 'System not found.')
@api_manager.doc(params={'system_id': 'System ID.'})
class SystemsInfoViewItem(Resource):

	"""
	API Handler for a system in the systems_info_view.
	"""

	@api_login_required('get')
	@api_manager.marshal_with(systems_info_view_serializer)
	def get(self, system_id):
		"""
		Returns a single system from systems_info_view.
		"""
		if not does_user_have_system_permission(system_id, "view.detail", "systems.all.view"):
			raise InvalidPermissionException


		system = cortex.lib.systems.get_system_by_id(system_id)

		if not system:
			raise NoResultsFoundException

		return system

@systems_info_view_namespace.route('/<string:system_name>')
@api_manager.response(404, 'System not found.')
@api_manager.doc(params={'system_name': 'System Name.'})
class SystemsInfoViewItemByName(Resource):

	"""
	API Handler for a system in the systems_info_view.
	(Searching by System Name).
	"""

	@api_login_required('get')
	@api_manager.marshal_with(systems_info_view_serializer)
	def get(self, system_name):
		"""
		Returns a single system from systems_info_view, searching by name.
		"""

		system = cortex.lib.systems.get_system_by_name(system_name)

		if not system:
			raise NoResultsFoundException

		if not does_user_have_system_permission(system['id'], "view.detail", "systems.all.view"):
			raise InvalidPermissionException

		return system
