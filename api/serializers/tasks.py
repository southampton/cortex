from flask_restx import fields
from cortex.api import api_manager
from cortex.api.serializers import pagination

tasks_serializer = api_manager.model('task', {
	'id': fields.Integer(required=True, description='Task ID.'),
	'module': fields.String(required=True, description='The module that started the task'),
	'username': fields.String(required=True, description='The user that started the task'),
	'start': fields.DateTime(required=False, description='The date and time this task was started'),
	'end': fields.DateTime(required=False, description='The date and time this task finished'),
	'status': fields.Integer(required=True, description='The status of the task - 0: in progress, 1: success, 2: failure, 3: warnings'),
	'description': fields.String(required=False, description='The description of the task'),
})

page_tasks_serializer = api_manager.inherit('Paginated tasks', pagination, {
	'items': fields.List(fields.Nested(tasks_serializer))
})

