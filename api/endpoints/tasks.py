from flask import request, session
from flask_restplus import Resource
import math

from cortex.api import api_manager, api_login_required
from cortex.api.exceptions import InvalidPermissionException, NoResultsFoundException
from cortex.api.parsers import pagination_arguments
#from cortex.api.serializers.tasks import page_tasks_serializer, tasks_serializer
from cortex.api.serializers.tasks import tasks_serializer

from cortex.lib.user import does_user_have_permission
import cortex.lib.core

tasks_namespace = api_manager.namespace('tasks', description='Tasks API')

#@tasks_namespace.route('/')
#class SystemsInfoViewCollection(Resource):
#
#	"""
#	API Handler for multiple rows from the systems_info_view.
#	"""
#
#	@api_login_required('get')
#	@api_manager.expect(pagination_arguments)
#	@api_manager.marshal_with(page_tasks_serializer, mask='{page,pages,per_page,total,items{id,name}}')
#	def get(self):
#		"""
#		Returns a paginated list of rows from the systems_info_view.
#		"""
#		args = pagination_arguments.parse_args(request)
#		page = args.get('page', 1)
#		per_page = args.get('per_page', 10)
#
#		limit_start = (page-1)*per_page
#		limit_length = per_page
#
#		if not does_user_have_permission("tasks.view"):
#			raise InvalidPermissionException
#
#		#results = cortex.lib.systems.get_systems(class_name=class_name, order='id', limit_start=limit_start, limit_length=limit_length, hide_inactive=hide_inactive, only_other=only_other, show_expired=show_expired, show_nocmdb=show_nocmdb, show_allocated_and_perms=show_allocated_and_perms, only_allocated_by=only_allocated_by)
#
#		if not results:
#			raise NoResultsFoundException
#		
#		return {
#			'page': page,
#			'per_page': per_page,
#			'pages': math.ceil(float(total)/float(per_page)),
#			'total': total,
#			'items': results,
#		}

@tasks_namespace.route('/<int:task_id>')
@api_manager.response(404, 'Task not found.')
@api_manager.doc(params={'task_id': 'Task ID.'})
class SystemsInfoViewItem(Resource):

	"""
	API Handler for a task in the tasks list.
	"""

	@api_login_required('get')
	@api_manager.marshal_with(tasks_serializer)
	def get(self, task_id):
		"""
		Returns a single task from the tasks list.
		"""
		if not does_user_have_permission("tasks.view"):
			raise InvalidPermissionException

		task = cortex.lib.core.task_get(task_id)

		if not task:
			raise NoResultsFoundException

		return task
