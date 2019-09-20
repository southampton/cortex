from flask import request, session
from flask_restplus import Resource
import math

from cortex.api import api_manager, api_login_required
from cortex.api.exceptions import InvalidPermissionException, NoResultsFoundException
from cortex.api.parsers import pagination_arguments
from cortex.api.serializers.systems_info_view import page_systems_info_view_serializer, systems_info_view_serializer

from cortex.lib.user import does_user_have_permission, does_user_have_system_permission, does_user_have_any_system_permission
import cortex.lib.systems

systems_info_view_namespace = api_manager.namespace('systems_info_view', description='System\'s Info View API')

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
		args = pagination_arguments.parse_args(request)
		page = args.get('page', 1)
		per_page = args.get('per_page', 10)

		limit_start = (page-1)*per_page
		limit_length = per_page

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

		if not results:
			raise NoResultsFoundException
		
		return {
			'page': page,
			'per_page': per_page,
			'pages': math.ceil(float(total)/float(per_page)),
			'total': total,
			'items': results,
		}
		
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
		if not does_user_have_system_permission(system_id,"view.detail","systems.all.view"):
			raise InvalidPermissionException

		
		system = cortex.lib.systems.get_system_by_id(system_id)

		if not system:
			raise NoResultsFoundException

		return system

@systems_info_view_namespace.route('/<string:system_name>')
@api_manager.response(404, 'System not found.')
@api_manager.doc(params={'system_name': 'System Name.'})
class SystemsInfoViewItem(Resource):

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

		if not does_user_have_system_permission(system['id'],"view.detail","systems.all.view"):
			raise InvalidPermissionException

		return system
