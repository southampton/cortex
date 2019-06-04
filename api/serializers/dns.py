from flask_restplus import fields
from cortex.api import api_manager
from cortex.api.serializers import pagination

dns_serializer = api_manager.model('DNS', {
	'ip': fields.String(required=True, description='Host IP Address'),
	'hostname': fields.String(required=True, description='Host name'),
	'error': fields.String(required=False, description='Error Resposne'),
	'success': fields.Integer(required=True, description='DNS Lookup Status - 0: failure 1: success'),
})

