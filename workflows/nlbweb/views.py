#!/usr/bin/python

from cortex import app
from cortex.lib.workflow import CortexWorkflow
import cortex.lib.core
import cortex.lib.systems
import cortex.views
from flask import Flask, request, session, redirect, url_for, flash, g, abort, render_template, jsonify
import re, datetime

# For DNS queries
import socket

# For NLB API
import requests

# For certificate validation
import OpenSSL as openssl

workflow = CortexWorkflow(__name__)
workflow.add_permission('nlbweb.create', 'Creates NLB Web Service')

# IPv4 Address Regex
ipv4_re = re.compile(r"^((([0-9])|([1-9][0-9])|(1[0-9][0-9])|(2[0-4][0-9])|(25[0-5]))\.){3}((([0-9])|([1-9][0-9])|(1[0-9][0-9])|(2[0-4][0-9])|(25[0-5])))$")

@workflow.route('create', title='Create NLB Web Service', order=40, permission="nlbweb.create", methods=['GET', 'POST'])
def nlbweb_create():
	# Get the workflow settings
	wfconfig = workflow.config

	# Turn envs in to a dict
	envs_dict = { env['id']: env for env in wfconfig['ENVS'] }

	if request.method == 'GET':
		## Show form
		return render_template(__name__ + "::nlbweb.html", title="Create NLB Web Service", envs=wfconfig['ENVS'], partition=wfconfig['DEFAULT_PARTITION'], ssl_providers=wfconfig['SSL_PROVIDERS'], default_ssl_provider=wfconfig['DEFAULT_SSL_PROVIDER'], envs_dict=envs_dict)

	elif request.method == 'POST':
		valid_form = True
		form_fields = {}

		# Get service parameters
		form_fields['service'] = request.form.get('service', '').strip()
		form_fields['short_service'] = request.form.get('short_service', '').strip()
		form_fields['env'] = request.form.get('env', '').strip()
		form_fields['partition'] = request.form.get('partition', '').strip()

		# Get service access parameters
		form_fields['fqdn'] = request.form.get('fqdn', '').strip()
		form_fields['ip'] = request.form.get('ip', '').strip()
		form_fields['http_port'] = request.form.get('http_port', '').strip()
		form_fields['https_port'] = request.form.get('https_port', '').strip()
		form_fields['enable_ssl'] = 'enable_ssl' in request.form
		form_fields['monitor_url'] = request.form.get('monitor_url', '').strip()
		form_fields['monitor_response'] = request.form.get('monitor_response', '').strip()

		# Get SSL options
		form_fields['redirect_http'] = 'redirect_http' in request.form
		form_fields['encrypt_backend'] = 'encrypt_backend' in request.form
		form_fields['ssl_key'] = request.form.get('ssl_key', '').strip()
		form_fields['ssl_cert'] = request.form.get('ssl_cert', '').strip()
		form_fields['ssl_provider'] = request.form.get('ssl_provider', '').strip()

		# Get the nodes
		form_fields['node_hosts'] = request.form.getlist('node_host[]')
		form_fields['node_http_ports'] = request.form.getlist('node_http_port[]')
		form_fields['node_https_ports'] = request.form.getlist('node_https_port[]')
		form_fields['node_ips'] = request.form.getlist('node_ip[]')

		# Service parameter validation
		if len(form_fields['service']) == 0:
			flash('You must enter a service name', 'alert-danger')
			valid_form = False
		if len(form_fields['short_service']) == 0:
			flash('You must enter a short service name', 'alert-danger')
			valid_form = False
		if ' ' in form_fields['short_service']:
			flash('Short service name can only contain numbers, letters and dashes', 'alert-danger')
			valid_form = False
		if len(form_fields['env']) == 0:
			flash('You must specify an environment', 'alert-danger')
			valid_form = False
		if form_fields['env'] not in [e['id'] for e in wfconfig['ENVS']]:
			flash('Invalid environment specified', 'alert-danger')
			valid_form = False
		if len(form_fields['partition']) == 0:
			flash('You must enter a partition name', 'alert-danger')
			valid_form = False

		# Validate service access parameters
		if len(form_fields['fqdn']) == 0:
			flash('You must enter a fully-qualified domain name for the service', 'alert-danger')
			valid_form = False
		else:
			if '.' not in form_fields['fqdn']:
				flash('The domain name of the service must be fully qualified', 'alert-danger')
				valid_form = False
		if len(form_fields['ip']) > 0:
			if ipv4_re.match(form_fields['ip']) is None:
				flash('Invalid IPv4 service address', 'alert-danger')
				valid_form = False
		if len(form_fields['http_port']) == 0:
			flash('You must enter an HTTP port number for the service', 'alert-danger')
			valid_form = False
		if len(form_fields['http_port']) > 0:
			try:
				port = int(form_fields['http_port'])
				if port <= 0 or port > 65535:
					raise ValueError()
			except Exception as e:
				flash('You must specify a valid HTTP port number for the service', 'alert-danger')
				valid_form = False
		if form_fields['enable_ssl'] and len(form_fields['https_port']) == 0:
			flash('You must enter an HTTPS port number for the service', 'alert-danger')
			valid_form = False
		if form_fields['enable_ssl'] and len(form_fields['https_port']) > 0:
			try:
				port = int(form_fields['https_port'])
				if port <= 0 or port > 65535:
					raise ValueError()
			except Exception as e:
				flash('You must specify a valid HTTPS port number for the service', 'alert-danger')
				valid_form = False
		if len(form_fields['monitor_url']) == 0:
			flash('You must enter a valid URL on the service to monitor', 'alert-danger')
			valid_form = False
		if form_fields['enable_ssl'] and len(form_fields['ssl_key']) == 0:
			flash('You must provide an SSL private key', 'alert-danger')
			valid_form = False
		openssl_ssl_key = None
		if form_fields['enable_ssl'] and len(form_fields['ssl_key']) > 0:
			try:
				openssl_ssl_key = openssl.crypto.load_privatekey(openssl.crypto.FILETYPE_PEM, form_fields['ssl_key'])
			except Exception as e:
				flash('Error reading SSL private key: ' + str(e), 'alert-danger')
				valid_form = False
		if form_fields['enable_ssl'] and len(form_fields['ssl_cert']) == 0:
			flash('You must provide an SSL certificate', 'alert-danger')
			valid_form = False
		openssl_ssl_cert = None
		if form_fields['enable_ssl'] and len(form_fields['ssl_cert']) > 0:
			try:
				openssl_ssl_cert = openssl.crypto.load_certificate(openssl.crypto.FILETYPE_PEM, form_fields['ssl_cert'])
			except Exception as e:
				flash('Error reading SSL certificate: ' + str(e), 'alert-danger')
				valid_form = False
			if openssl_ssl_key is not None and openssl_ssl_cert is not None:
				ctx = openssl.SSL.Context(openssl.SSL.TLSv1_METHOD)
				ctx.use_privatekey(openssl_ssl_key)
				ctx.use_certificate(openssl_ssl_cert)
				try:
					ctx.check_privatekey()
				except Exception as e:
					flash('SSL key/certficate validation error. Do the key and certificate match? Details: ' + str(e), 'alert-danger')
					valid_form = False
		if form_fields['enable_ssl'] and len(form_fields['ssl_provider']) == 0:
			flash('You must provide an SSL certificate provider', 'alert-danger')
			valid_form = False
		if form_fields['enable_ssl'] and len(form_fields['ssl_provider']) > 0 and form_fields['ssl_provider'] != "*SELF" and form_fields['ssl_provider'] not in [provider['id'] for provider in wfconfig['SSL_PROVIDERS']]:
			flash('Invalid SSL provider', 'alert-danger')
			valid_form = False

		# Validate the hosts
		valid_nodes = True
		if len(form_fields['node_hosts']) == 0 or len(form_fields['node_http_ports']) == 0 or len(form_fields['node_https_ports']) == 0 or len(form_fields['node_ips']) == 0:
			flash('Missing back-end nodes. You must specify at least one back-end node.', 'alert-danger')
			valid_form = False
			valid_nodes = False
		if len(form_fields['node_hosts']) != len(form_fields['node_http_ports']) or len(form_fields['node_hosts']) != len(form_fields['node_https_ports']) or len(form_fields['node_hosts']) != len(form_fields['node_ips']):
			flash('Invalid back-end node configuration', 'alert-danger')
			valid_form = False
			valid_nodes = False
		for i in range(0, len(form_fields['node_hosts'])):
			if len(form_fields['node_hosts'][i]) == 0:
				flash('You must specify a hostname for every back-end node', 'alert-danger')
				valid_form = False
				valid_nodes = False
				break
		if form_fields['enable_ssl'] and not form_fields['redirect_http']:
			for i in range(0, len(form_fields['node_http_ports'])):
				if len(form_fields['node_http_ports'][i]) == 0:
					flash('You must specify an HTTP port for every back-end node', 'alert-danger')
					valid_form = False
					valid_nodes = False
					break
				try:
					port = int(form_fields['node_http_ports'][i])
					if port <= 0 or port > 65535:
						raise ValueError()
				except Exception as e:
					flash('You must specify a valid HTTP port for every back-end node', 'alert-danger')
					valid_form = False
					valid_nodes = False
					break
		if form_fields['enable_ssl']:
			for i in range(0, len(form_fields['node_https_ports'])):
				if len(form_fields['node_https_ports'][i]) == 0:
					flash('You must specify an HTTPS port for every back-end node', 'alert-danger')
					valid_form = False
					valid_nodes = False
					break
				try:
					port = int(form_fields['node_https_ports'][i])
					if port <= 0 or port > 65535:
						raise ValueError()
				except Exception as e:
					flash('You must specify a valid HTTPS port for every back-end node', 'alert-danger')
					valid_form = False
					valid_nodes = False
					break
					
		for i in range(0, len(form_fields['node_ips'])):
			if len(form_fields['node_ips'][i]) == 0:
				flash('You must specify an IP address for every back-end node', 'alert-danger')
				valid_form = False
				valid_nodes = False
				break
			else:
				if ipv4_re.match(form_fields['node_ips'][i]) is None:
					flash('You must specify a valid IPv4 address for every back-end node', 'alert-danger')
					valid_form = False
					break

		if not valid_form:
			# Turn envs in to a dict
			envs_dict = { env['id']: env for env in wfconfig['ENVS'] }

			return render_template(__name__ + "::nlbweb.html", title="Create NLB Web Service", envs=wfconfig['ENVS'], partition=wfconfig['DEFAULT_PARTITION'], ssl_providers=wfconfig['SSL_PROVIDERS'], default_ssl_provider=wfconfig['DEFAULT_SSL_PROVIDER'], values=form_fields, envs_dict=envs_dict)

		# We've now done some basic validation on the inputs

		# Lowercase the FQDN
		form_fields['fqdn'] = form_fields['fqdn'].lower()

		details = {'ssl': 0, 'warnings': []}
		if form_fields['enable_ssl']:
			# Extract certificate details
			details['ssl'] = 1
			details['ssl_key_size'] = openssl_ssl_key.bits()
			details['ssl_cert_subject_cn'] = openssl_ssl_cert.get_subject().CN
			details['ssl_cert_subject_ou'] = openssl_ssl_cert.get_subject().OU
			details['ssl_cert_subject_o'] = openssl_ssl_cert.get_subject().O
			details['ssl_cert_subject_l'] = openssl_ssl_cert.get_subject().L
			details['ssl_cert_subject_st'] = openssl_ssl_cert.get_subject().ST
			details['ssl_cert_subject_c'] = openssl_ssl_cert.get_subject().C
			details['ssl_cert_notbefore'] = parse_zulu_time(openssl_ssl_cert.get_notBefore())
			details['ssl_cert_notafter'] = parse_zulu_time(openssl_ssl_cert.get_notAfter())
			details['ssl_cert_issuer_cn'] = openssl_ssl_cert.get_issuer().CN
			details['ssl_cert_issuer_ou'] = openssl_ssl_cert.get_issuer().OU
			details['ssl_cert_issuer_o'] = openssl_ssl_cert.get_issuer().O
			details['ssl_cert_issuer_l'] = openssl_ssl_cert.get_issuer().L
			details['ssl_cert_issuer_st'] = openssl_ssl_cert.get_issuer().ST
			details['ssl_cert_issuer_c'] = openssl_ssl_cert.get_issuer().C

			# Process certificate extensions
			for i in range(0, openssl_ssl_cert.get_extension_count()):
				ext = openssl_ssl_cert.get_extension(i)
				if ext.get_short_name() == 'subjectAltName':
					alt_names = decode_subject_alt_name(ext.get_data())
					details['ssl_cert_subjectAltName'] = []
					for name in alt_names:
						if   name[0] == 1:  # 
							details['ssl_cert_subjectAltName'].append('RFC822:' + name[1])
						elif name[0] == 2:  # DNS name
							details['ssl_cert_subjectAltName'].append('DNS:' + name[1])
						elif name[0] == 6:  # URI
							details['ssl_cert_subjectAltName'].append('URI:' + name[1])

			# Ensure SSL key size is of appropriate length
			if int(details['ssl_key_size']) < wfconfig['SSL_MIN_KEY_SIZE']:
				details['warnings'].append('SSL private key is only ' + str(details['ssl_key_size']) + ' bits in length. Consider increasing it to at least ' + str(wfconfig['SSL_MIN_KEY_SIZE']) + ' bits')

			# Ensure certificate subject CN matches service FQDN
			if details['ssl_cert_subject_cn'].lower() != form_fields['fqdn']:
				details['warnings'].append('SSL certificate CN does not match service FQDN')

			# Ensure subjectAltName exists, and that the FQDN of the service is contained within
			if 'ssl_cert_subjectAltName' in details:
				if 'DNS:' + form_fields['fqdn'] not in details['ssl_cert_subjectAltName']:
					details['warnings'].append('SSL certificate subjectAltName does not contain the service FQDN')
			else:
				details['warnings'].append('SSL certificate does not have a subjectAltName field')

			# Get current UTC time so we can validate certificate timestamp
			utc_now = datetime.datetime.utcnow()

			# Ensure certificate has started
			if utc_now < details['ssl_cert_notbefore']:
				details['warnings'].append('SSL certificate is not valid yet')

			# Ensure certificate is not expired
			if utc_now > details['ssl_cert_notafter']:
				details['warnings'].append('SSL certificate has expired')

			# Ensure certificate won't expire within a given threshold
			if utc_now + datetime.timedelta(days=wfconfig['SSL_MIN_REMAINING_TIME']) > details['ssl_cert_notafter']:
				details['warnings'].append('SSL certificate expires soon. Consider getting a new certificate')

			# Check the details of the certificate to ensure they're what we would expect
			if 'SSL_EXPECTED_SUBJECT_OU' in wfconfig and wfconfig['SSL_EXPECTED_SUBJECT_OU'] is not None and details['ssl_cert_subject_ou'] != wfconfig['SSL_EXPECTED_SUBJECT_OU']:
				details['warnings'].append('SSL certificate subject Organisational Unit does not match expected "' + str(wfconfig['SSL_EXPECTED_SUBJECT_OU']) + '"')
			if 'SSL_EXPECTED_SUBJECT_O' in wfconfig and wfconfig['SSL_EXPECTED_SUBJECT_O'] is not None and details['ssl_cert_subject_o'] != wfconfig['SSL_EXPECTED_SUBJECT_O']:
				details['warnings'].append('SSL certificate subject Organisation does not match expected "' + str(wfconfig['SSL_EXPECTED_SUBJECT_O']) + '"')
			if 'SSL_EXPECTED_SUBJECT_L' in wfconfig and wfconfig['SSL_EXPECTED_SUBJECT_L'] is not None and details['ssl_cert_subject_l'] != wfconfig['SSL_EXPECTED_SUBJECT_L']:
				details['warnings'].append('SSL certificate subject Locality does not match expected "' + str(wfconfig['SSL_EXPECTED_SUBJECT_L']) + '"')
			if 'SSL_EXPECTED_SUBJECT_ST' in wfconfig and wfconfig['SSL_EXPECTED_SUBJECT_ST'] is not None and details['ssl_cert_subject_st'] != wfconfig['SSL_EXPECTED_SUBJECT_ST']:
				details['warnings'].append('SSL certificate subject State does not match expected "' + str(wfconfig['SSL_EXPECTED_SUBJECT_ST']) + '"')
			if 'SSL_EXPECTED_SUBJECT_C' in wfconfig and wfconfig['SSL_EXPECTED_SUBJECT_C'] is not None and details['ssl_cert_subject_c'] != wfconfig['SSL_EXPECTED_SUBJECT_C']:
				details['warnings'].append('SSL certificate subject Country does not match expected "' + str(wfconfig['SSL_EXPECTED_SUBJECT_C']) + '"')

		# That's everything validated: now check the NLB to validate against that

		# Show the user the details, warnings, and what we're going to do
		return render_template(__name__ + "::validate.html", title="Create NLB Web Service", details=details)

@workflow.route('validate', title='Create NLB Web Service', permission="nlbweb.create", methods=['POST'], menu=False)
def nlbweb_validate():
	# Get the workflow settings
	wfconfig = workflow.config
	
	# If we've got the confirmation, start the task:
	if 'confirm' in request.form and int(request.form['confirm']) == 1:
		options = {}
		options['wfconfig'] = wfconfig

		# Connect to NeoCortex and start the task
		neocortex = cortex.lib.core.neocortex_connect()
		task_id = neocortex.create_task(__name__, session['username'], options, description="Creates the necessary objects on the NLB to run a basic HTTP(S) website / service")

		# Redirect to the status page for the task
		return redirect(url_for('task_status', id=task_id))

@workflow.route('dnslookup', permission="nlbweb.create", menu=False)
def nlbweb_dns_lookup():
	host = request.args['host']
	add_default_domain = False
	if host.find('.') == -1:
		add_default_domain = True
	else:
		host_parts = host.split('.')
		if len(host_parts) == 2:
			if host_parts[1] in workflow.config['KNOWN_DOMAIN_SUFFIXES']:
				add_default_domain = True

	if add_default_domain:
		host = host + '.' + workflow.config['DEFAULT_DOMAIN']

	result = {'success': 0}
	try:
		result['ip'] = socket.gethostbyname(host)
		result['success'] = 1
	except Exception, e:
		pass

	return jsonify(result)

# Processes a Zulu time
def parse_zulu_time(s):
	return datetime.datetime(int(s[0:4]), int(s[4:6]), int(s[6:8]), int(s[8:10]), int(s[10:12]), int(s[12:14]))

# Reads an ASN1 IA5 String (i.e. a string where all octets are < 128)
def read_asn1_string(byte_string, offset):
	# Get the length of the string
	(length, offset) = read_asn1_length(byte_string, offset)

	if length != -1:
		return (byte_string[offset:offset + length], offset + length)
	else:
		# Search for the end of the string
		end_byte_idx = offset
		while byte_string[end_byte_offset] != 0b10000000:
			end_byte_idx = end_byte_idx + 1

		return (byte_string[offset:end_byte_index], end_byte_index + 1)

# Reads an ASN1 length
def read_asn1_length(byte_string, offset):
	# ASN1 lengths can be determined by single byte, multibyte, or be unknown
	length_data = ord(byte_string[offset])
	length_lead = (length_data & 0b10000000) >> 7
	length_tail = length_data & 0b01111111
	if length_lead == 0:
		# Single byte, contained, short length ( < 128 bytes )
		length = length_tail
		offset = offset + 1
	elif length_lead == 1 and length_tail == 0:
		# Indefinite (unknown) length
		length = -1
		offset = offset + 1
	elif length_lead == 1 and length_tail == 127:
		raise ValueError('Reserved length in ASN1 length octet')
	else:
		length_bytes = length_tail
		length_byte_idx = offset + 1
		offset = offset + 1
		length_end_byte = length_byte_idx + length_bytes
		length = 0
		while length_byte_idx < length_end_byte:
			length = length << 8
			length = length | ord(byte_string[length_byte_idx])
			length_byte_idx = length_byte_idx + 1
			offset = offset + 1

	return (length, offset)

def decode_subject_alt_name(byte_string):
	results = []

	# A quick summary of ASN1 tags:
	# Format: Single octet bits: AABCCCCC
	#    AA = Tag Class (00 = Universal, 01 = Application, 02 = Context-specific, 03 = Private)
	#     B = Primitive (0) or Constructed (1)
	# CCCCC = Tag number (see the ASN1 docs)
	context_type = ord(byte_string[0])
	if context_type == 0b00110000:	# Universal, Constructed, Sequence
		# Length follows the ASN1 tag
		(length, first_data_byte_idx) = read_asn1_length(byte_string, 1)

		# We've established our sequence length and where the first byte is.
		# Now it gets complicated
		byte_idx = first_data_byte_idx
		while byte_idx < length + 2:
			seq_el_type = ord(byte_string[byte_idx])
			byte_idx = byte_idx + 1
			
			if   seq_el_type == 0b10000000:  # otherName [0]
				raise ValueError('Unsupported subjectAltName type (0)')
			elif seq_el_type == 0b10000001:  # rfc822Name [1]
				(result, byte_idx) = read_asn1_string(byte_string, byte_idx)
				results.append((1, result))
			elif seq_el_type == 0b10000010:  # dNSName [2]
				(result, byte_idx) = read_asn1_string(byte_string, byte_idx)
				results.append((2, result))
			elif seq_el_type == 0b10000011:  # x400Address [3]
				raise ValueError('Unsupported subjectAltName type (3)')
			elif seq_el_type == 0b10000100:  # directoryName [4]
				raise ValueError('Unsupported subjectAltName type (4)')
			elif seq_el_type == 0b10000101:  # ediPartyName [5]
				raise ValueError('Unsupported subjectAltName type (5)')
			elif seq_el_type == 0b10000110:  # uniformResourceIdentifier [6]
				(result, byte_idx) = read_asn1_string(byte_string, byte_idx)
				results.append((6, result))
			elif seq_el_type == 0b10000111:  # IPAddress [7]
				raise ValueError('Unsupported subjectAltName type (7)')
			elif seq_el_type == 0b10001000:  # registeredID [8]
				raise ValueError('Unsupported subjectAltName type (8)')
			else:
				raise ValueError('Unknown subjectAltName type (' + str(seq_el_type) + ')')

		return results

	else:
		raise ValueError('subjectAltName does not start with ASN1 sequence')
