from flask_restplus import fields
from cortex.api import api_manager
from cortex.api.serializers import pagination

system_groups_serializer = api_manager.model('puppet', {
	'id': fields.Integer(required=True, description='Entry ID'),
	'name': fields.String(required=True, description='Name of the system group'),
})
