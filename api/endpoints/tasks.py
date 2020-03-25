from flask import request, session
from flask_restx import Resource, reqparse
import math

from cortex.api import api_manager, api_login_required
from cortex.api.exceptions import InvalidPermissionException, NoResultsFoundException
from cortex.api.parsers import pagination_arguments
from cortex.api.serializers.tasks import page_tasks_serializer, tasks_serializer

from cortex.lib.user import does_user_have_permission
import cortex.lib.core

tasks_arguments = reqparse.RequestParser()
tasks_arguments.add_argument('username', type=str, required=False, default=None, help='User who started the task')
tasks_arguments.add_argument('module', type=str, required=False, default=None, help='The module who started the task')
tasks_arguments.add_argument('status', type=int, required=False, default=None, help='The status code of the task')

tasks_namespace = api_manager.namespace('tasks', description='Tasks API')

@tasks_namespace.route('/')
class TasksCollection(Resource):

	"""
	API Handler for multiple rows for tasks.
	"""

	@api_login_required()
	@api_manager.expect(pagination_arguments, tasks_arguments)
	@api_manager.marshal_with(page_tasks_serializer, mask='{page,pages,per_page,total,items}')
	def get(self):
		"""
		Returns a paginated list of rows from the tasks lists.
		"""
		args = pagination_arguments.parse_args(request)
		page = args.get('page', 1)
		per_page = args.get('per_page', 10)

		limit_start = (page-1)*per_page
		limit_length = per_page

		if not does_user_have_permission("tasks.view"):
			raise InvalidPermissionException

		tasks_args = tasks_arguments.parse_args(request)
		username = tasks_args.get('username', None)
		module = tasks_args.get('module', None)
		status = tasks_args.get('status', None)

		total = cortex.lib.core.tasks_count(username=username, module=module, status=status)
		results = cortex.lib.core.tasks_get(username=username, module=module, status=status, order='id', limit_start=limit_start, limit_length=limit_length)

		if not results:
			raise NoResultsFoundException
		
		return {
			'page': page,
			'per_page': per_page,
			'pages': math.ceil(float(total)/float(per_page)),
			'total': total,
			'items': results,
		}

@tasks_namespace.route('/<int:task_id>')
@api_manager.response(404, 'Task not found.')
@api_manager.doc(params={'task_id': 'Task ID.'})
class TaskItem(Resource):

	"""
	API Handler for a task in the tasks list.
	"""

	@api_login_required()
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
