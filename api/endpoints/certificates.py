from flask import request, session, g
from flask_restplus import Resource, reqparse
import math
import MySQLdb as mysql

from cortex import app
from cortex.corpus import Corpus
from cortex.api import api_manager, api_login_required
from cortex.api.exceptions import InvalidPermissionException, NoResultsFoundException
from cortex.api.parsers import pagination_arguments
from cortex.api.serializers.certificates import certificates_serializer, page_certificates_serializer

from cortex.lib.user import does_user_have_permission

certificates_namespace = api_manager.namespace('certificates', description='Certificate API')

certificates_arguments = reqparse.RequestParser()
certificates_arguments.add_argument('cn_or_san', type=str, required=False, default=None, help='A subject CN or SAN to search for')

@certificates_namespace.route('/')
class CertificatesCollection(Resource):
	"""
	API Handler for multiple rows from the certificates table.
	"""

	@api_login_required('get', True)
	@api_manager.expect(pagination_arguments, certificates_arguments)
	@api_manager.marshal_with(page_certificates_serializer, mask='{page,pages,per_page,total,items}')
	def get(self):
		"""
		Returns a paginated list of rows from the certificates table.
		"""

		args = pagination_arguments.parse_args(request)
		page = int(args.get('page', 1))
		per_page = int(args.get('per_page', 10))

		limit_start = (page-1)*per_page
		limit_length = per_page

		if 'api_token_valid' not in session or session['api_token_valid'] is not True:
			if not does_user_have_permission("certificates.view"):
				raise InvalidPermissionException

		# Parse our arguments
		certificates_args = certificates_arguments.parse_args(request)
		cn_or_san = certificates_args.get('cn_or_san', None)

		# Build a where clause
		where_clause = ''
		query_parts = []
		if cn_or_san is not None:
			# Search for the CN or SAN
			where_clause = ' WHERE `certificate`.`subjectCN` = %s OR `certificate_sans`.`san` = %s'

			# Add on query param for CN
			query_parts.append(cn_or_san)

			# Add on query param for SAN, which need a "DNS:" prefix
			query_parts.append('DNS:' + cn_or_san)

		# Get the number of certificates
		curd = g.db.cursor(mysql.cursors.DictCursor)
		curd.execute('SELECT COUNT(DISTINCT `certificate`.`digest`) AS `count` FROM `certificate` LEFT JOIN `certificate_sans` ON `certificate`.`digest` = `certificate_sans`.`cert_digest`' + where_clause, tuple(query_parts))
		total = curd.fetchone()['count']

		# Get the list of certificates
		curd.execute('SELECT `certificate`.`digest` AS `digest`, `certificate`.`subjectCN` AS `subjectCN`, `certificate`.`subjectDN` AS `subjectDN`, `certificate`.`notBefore` AS `notBefore`, `certificate`.`notAfter` AS `notAfter`, `certificate`.`issuerCN` AS `issuerCN`, `certificate`.`issuerDN` AS `issuerDN`, MAX(`scan_result`.`when`) AS `lastSeen`, COUNT(DISTINCT `scan_result`.`host`) AS `numHosts`, `certificate`.`keySize` AS `keySize` FROM `certificate` LEFT JOIN `scan_result` ON `certificate`.`digest` = `scan_result`.`cert_digest` LEFT JOIN `certificate_sans` ON `certificate`.`digest` = `certificate_sans`.`cert_digest`' + where_clause + ' GROUP BY `certificate`.`digest` LIMIT ' + str(limit_start) + ',' + str(limit_length), tuple(query_parts))

		results = curd.fetchall()

		return {
			'page': page,
			'per_page': per_page,
			'pages': math.ceil(float(total)/float(per_page)),
			'total': total,
			'items': results,
		}
	
@certificates_namespace.route('/<string:digest>')
@api_manager.response(404, 'Certificate not found')
@api_manager.doc(params={'digest':'The SHA-1 digest of the certificate'})
class CertificateItem(Resource):
	"""
	API for individual certificates.
	"""

	@api_login_required('get', True)
	@api_manager.marshal_with(certificates_serializer)
	def get(self, digest):
		if 'api_token_valid' not in session or session['api_token_valid'] is not True:
			if not does_user_have_permission("certificates.view"):
				raise InvalidPermissionException

		curd = g.db.cursor(mysql.cursors.DictCursor)
		curd.execute('SELECT `certificate`.`digest` AS `digest`, `certificate`.`subjectCN` AS `subjectCN`, `certificate`.`subjectDN` AS `subjectDN`, `certificate`.`notBefore` AS `notBefore`, `certificate`.`notAfter` AS `notAfter`, `certificate`.`issuerCN` AS `issuerCN`, `certificate`.`issuerDN` AS `issuerDN`, MAX(`scan_result`.`when`) AS `lastSeen`, COUNT(DISTINCT `scan_result`.`host`) AS `numHosts`, `certificate`.`keySize` AS `keySize` FROM `certificate` LEFT JOIN `scan_result` ON `certificate`.`digest` = `scan_result`.`cert_digest` WHERE `digest` = %s GROUP BY `certificate`.`digest`', (digest,))
		result = curd.fetchone()

		if result is None:
			return certificates_namespace.abort(404, 'Certificate not found')

		return result

	@api_login_required('delete', allow_api_token=True)
	@api_manager.response(204, 'Certificate was deleted')
	def delete(self, digest):
		"""
		Removes a certificate from the list of known certificates
		"""

		if 'api_token_valid' not in session or session['api_token_valid'] is not True:
			if not does_user_have_permission("certificates.view"):
				raise InvalidPermissionException

		# Make sure the certificate exists
		curd = g.db.cursor(mysql.cursors.DictCursor)
		curd.execute('SELECT `digest` FROM `certificate` WHERE `digest` = %s', (digest,))
		result = curd.fetchone()

		if result is None:
			return certificates_namespace.abort(404, 'Certificate not found')

		curd.execute('DELETE FROM `certificate` WHERE `digest` = %s', (digest,))
		g.db.commit()

		return "", 204

