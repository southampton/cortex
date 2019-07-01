from flask_restplus import fields
from cortex.api import api_manager
from cortex.api.serializers import pagination

# This is not actually getting used since nothing should be returned

puppet_serializer = api_manager.model('puppet', {
	'id': fields.Integer(required=True, description='Entry ID'),
	'module_name': fields.String(required=True, description='Name of the puppet module'),
	'class_name': fields.String(required=True, description='Name of the puppet class'),
	'class_parameter': fields.String(required=False, description='Name of the parameter in that class'),
	'description': fields.String(required=False, description='The description of the parameter'),
	'tag_name': fields.String(required=False, description='Tag name for this entry'),
})

page_puppet_serializer = api_manager.inherit('Paginated puppet', pagination, {
	'items': fields.List(fields.Nested(puppet_serializer))
})
