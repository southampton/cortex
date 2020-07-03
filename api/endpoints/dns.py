from flask import g
from flask_restx import Resource

from cortex import app
from cortex.api import api_login_required, api_manager
from cortex.api.serializers.dns import dns_serializer
from cortex.corpus import Corpus

dns_namespace = api_manager.namespace('dns', description='DNS API')

@dns_namespace.route('/<string:host>')
@api_manager.doc(params={'host':'Fully qualified domain name to lookup'})
class DNSLookupItem(Resource):

	"""
	API for DNS lookups
	"""

	@api_login_required()
	@api_manager.marshal_with(dns_serializer)
	def get(self, host):

		corpus = Corpus(g.db, app.config)
		return corpus.dns_lookup(host)
