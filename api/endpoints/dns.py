from flask import request, session, g
from flask_restplus import Resource
import math

from cortex import app
from cortex.corpus import Corpus
from cortex.api import api_manager, api_login_required
from cortex.api.exceptions import InvalidPermissionException, NoResultsFoundException
from cortex.api.serializers.dns import dns_serializer

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

