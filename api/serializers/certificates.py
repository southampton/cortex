from flask_restx import fields

from cortex.api import api_manager
from cortex.api.serializers import pagination

certificates_serializer = api_manager.model('certificate', {
	'digest': fields.String(required=True, description='The SHA-1 digest of the certificate'),
	'subjectCN': fields.String(required=False, description='The common name (CN) of the subject of the certificate'),
	'subjectDN': fields.String(required=True, description='The distinguished name (DN) of the subject of the certificate'),
	'notBefore': fields.DateTime(required=True, description='The date and time this certificate is valid from'),
	'notAfter': fields.DateTime(required=True, description='The date and time this certificate expires'),
	'issuerCN': fields.String(required=False, description='The common name (CN) of the issuer of the certificate'),
	'issuerDN': fields.String(required=True, description='The distinguished name (DN) of the issuer of the certificate'),
	'lastSeen': fields.DateTime(required=False, description='The date and time that a certificate scan last identified this certificate on the network'),
	'numHosts': fields.Integer(required=True, description='The number of unique locations that the certificate has been discovered by certificate scans'),
	'keySize': fields.Integer(required=True, description='The size (in bits) of the key used with the certificate')
})

page_certificates_serializer = api_manager.inherit('Paginated certificates', pagination, {
	'items': fields.List(fields.Nested(certificates_serializer))
})

cert_last_seen_serializer = api_manager.model('certificate_last_seen', {
	'timestamp': fields.DateTime(required=True, description='The date and time the certificate was seen at this location'),
	'location': fields.String(required=True, description='The IP address and post where the certificate was seen'),
	'chain_state': fields.Integer(required=True, description='The state of the chain')
})

certificates_full_serializer = api_manager.inherit('Full certificate details', certificates_serializer, {
	'sans': fields.List(fields.String(required=True, description='A subject alternate name')),
	'seenAt': fields.List(fields.Nested(cert_last_seen_serializer))
})
