#!/usr/bin/python

from cortex import app
from cortex.lib.workflow import CortexWorkflow
import cortex.lib.core
import cortex.lib.systems
import cortex.views
from cortex.corpus import Corpus
from flask import Flask, request, session, redirect, url_for, flash, g, abort, render_template, jsonify
import re, datetime, requests
from urllib.parse import urljoin
import MySQLdb as mysql

# For DNS queries
import socket

# For NLB API
from f5.bigip import ManagementRoot

# For certificate validation
import OpenSSL as openssl

# For securely passing the actions list via the browser
from itsdangerous import JSONWebSignatureSerializer

workflow = CortexWorkflow(__name__)
workflow.add_permission('nlbweb.create', 'Create NLB Web Service')

# IPv4 Address Regex
ipv4_re = re.compile(r"^((([0-9])|([1-9][0-9])|(1[0-9][0-9])|(2[0-4][0-9])|(25[0-5]))\.){3}((([0-9])|([1-9][0-9])|(1[0-9][0-9])|(2[0-4][0-9])|(25[0-5])))$")

# FQDN regex
fqdn_re = re.compile(r"^([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}$")

@workflow.route('create', title='Create NLB Web Service', order=40, permission="nlbweb.create", methods=['GET', 'POST'])
def nlbweb_create():


	# Check if workflows are disabled or not
	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute('SELECT `value` FROM `kv_settings` WHERE `key`=%s;',('workflow_lock_status',))
	current_value = curd.fetchone()
	if current_value['value'] == 'Locked':
		raise Exception("Workflows are currently locked. \n Please try again later.")


	# Get the workflow settings
	wfconfig = workflow.config

	# Turn envs in to a dict
	envs_dict = { env['id']: env for env in wfconfig['ENVS'] }

	# Turn SSL providers in to a dict
	ssl_providers_dict = { ssl_provider['id']: ssl_provider for ssl_provider in wfconfig['SSL_PROVIDERS'] }

	# Turn SSL client profiles in to a dict
	ssl_client_profiles_dict = { profile['id']: profile for profile in wfconfig['SSL_CLIENT_PROFILES'] }

	if request.method == 'GET':
		## Show form
		return render_template(__name__ + "::nlbweb.html", title="Create NLB Web Service", envs=wfconfig['ENVS'], ssl_providers=wfconfig['SSL_PROVIDERS'], default_ssl_provider=wfconfig['DEFAULT_SSL_PROVIDER'], envs_dict=envs_dict, letsencrypt_provider=wfconfig['LETSENCRYPT_PROVIDER_ID'], ssl_client_profiles=wfconfig['SSL_CLIENT_PROFILES'], default_ssl_client_profile=wfconfig['DEFAULT_SSL_CLIENT_PROFILE'], letsencrypt_enabled=wfconfig['LETSENCRYPT_ENABLED'])

	elif request.method == 'POST':
		valid_form = True
		form_fields = {}

		# Load the Corpus library (for Infoblox helper functions)
		corpus = Corpus(g.db, app.config)

		# Get parameters from form, stripped with defaults
		for field in ['service', 'env', 'fqdn', 'aliases', 'ip', 'http_port', 'https_port', 'monitor_url', 'monitor_response', 'ssl_key', 'ssl_cert', 'ssl_provider', 'outage_page', 'http_irules', 'https_irules', 'ssl_client_profile']:
			form_fields[field] = request.form.get(field, '').strip()

		# Get parameters from form - checkboxes
		for field in ['enable_ssl', 'redirect_http', 'encrypt_backend', 'use_xforwardedfor', 'generate_letsencrypt', 'enable_hsts']:
			form_fields[field] = field in request.form

		# If the Let's Encrypt functionality is disabled, force it to be
		if 'generate_letsencrypt' in form_fields and not wfconfig['LETSENCRYPT_ENABLED']:
			form_fields['generate_letsencrypt'] = False

		# Refactor: these are fixed
		form_fields['short_service'] = form_fields['fqdn']
		form_fields['partition'] = wfconfig['DEFAULT_PARTITION']

		# Get parameters from form - nodes
		form_fields['node_hosts'] = request.form.getlist('node_host[]')
		form_fields['node_http_ports'] = request.form.getlist('node_http_port[]')
		form_fields['node_https_ports'] = request.form.getlist('node_https_port[]')
		form_fields['node_ips'] = request.form.getlist('node_ip[]')

		# Service parameter validation
		if len(form_fields['service']) == 0:
			flash('You must enter a service name', 'alert-danger')
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
			elif fqdn_re.match(form_fields['fqdn']) is None:
				flash('The specified service domain name is not valid', 'alert-danger')
				valid_form = False
		if len(form_fields['aliases']) > 0:
			split_aliases = [x for x in form_fields['aliases'].split(' ') if x != '']
			for alias in split_aliases:
				if '.' not in alias:
					flash('All service aliases must be fully qualified domain names', 'alert-danger')
					valid_form = False
					break
				elif fqdn_re.match(alias) is None:
					flash('All service alises must be valid domain names: ' + alias, 'alert-danger')
					valid_form = False
					break
		else:
			split_aliases = []
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
		if form_fields['enable_ssl'] and not form_fields['generate_letsencrypt'] and len(form_fields['ssl_key']) == 0:
			flash('You must provide an SSL private key', 'alert-danger')
			valid_form = False
		openssl_ssl_key = None
		if form_fields['enable_ssl'] and not form_fields['generate_letsencrypt'] and len(form_fields['ssl_key']) > 0:
			try:
				openssl_ssl_key = openssl.crypto.load_privatekey(openssl.crypto.FILETYPE_PEM, form_fields['ssl_key'])
			except Exception as e:
				flash('Error reading SSL private key: ' + str(e), 'alert-danger')
				valid_form = False
		if form_fields['enable_ssl'] and not form_fields['generate_letsencrypt'] and len(form_fields['ssl_cert']) == 0:
			flash('You must provide an SSL certificate', 'alert-danger')
			valid_form = False
		openssl_ssl_cert = None
		if form_fields['enable_ssl'] and not form_fields['generate_letsencrypt'] and len(form_fields['ssl_cert']) > 0:
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
		if form_fields['enable_ssl'] and not form_fields['generate_letsencrypt'] and len(form_fields['ssl_provider']) == 0:
			flash('You must provide an SSL certificate provider', 'alert-danger')
			valid_form = False
		if form_fields['enable_ssl'] and not form_fields['generate_letsencrypt'] and len(form_fields['ssl_provider']) > 0 and form_fields['ssl_provider'] != "*SELF" and form_fields['ssl_provider'] not in [provider['id'] for provider in wfconfig['SSL_PROVIDERS']]:
			flash('Invalid SSL provider', 'alert-danger')
			valid_form = False
		if form_fields['enable_ssl'] and form_fields['generate_letsencrypt']:
			form_fields['ssl_provider'] = wfconfig['LETSENCRYPT_PROVIDER_ID']
		if form_fields['enable_ssl'] and form_fields['ssl_client_profile'] not in [profile['id'] for profile in wfconfig['SSL_CLIENT_PROFILES']]:
			flash('Invalid Parent SSL Client Profile', 'alert-danger')
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

		# Connect to the NLB now as we need the NLB to validate the
		# iRule list, which if they fail is a fatal error
		bigip_host = envs_dict[form_fields['env']]['nlb']
		bigip = ManagementRoot(bigip_host, wfconfig['NLB_USERNAME'], wfconfig['NLB_PASSWORD'])

		# Get the list of HTTP and HTTPS iRules and validate that they all exist
		try:
			http_irules = parse_irule_list(form_fields['http_irules'], bigip)
			https_irules = parse_irule_list(form_fields['https_irules'], bigip)
		except ValueError as e:
			# parse_irule_list returns a ValueError with the message to alert on
			flash(str(e), 'alert-danger')
			valid_form = False

		# Check if an Infoblox host record already exists
		existing_host_ref = corpus.infoblox_get_host_refs(form_fields['fqdn'])
		existing_host_ip = None
		if existing_host_ref is not None:
			last_ip = None

			# Loop to check if all host objects have one single IP
			# and it's the same across all of them
			for ref in existing_host_ref:
				# Get details about the host object
				host_object = corpus.infoblox_get_host_by_ref(ref)

				if len(host_object['ipv4addrs']) != 1:
					# If there are multiple IPs, then bail with an error
					flash('Host object for ' + form_fields['fqdn'] + ' already exists with multiple IPs.', 'alert-danger')
					valid_form = False
					break
				else:
					# Single IP, check to see if it's the same as the others
					if last_ip is not None and last_ip != host_object['ipv4addrs'][0]['ipv4addr']:
						# If a different IP is found, then bail with an error
						flash('Host object for ' + form_fields['fqdn'] + ' already exists with multiple IPs.', 'alert-danger')
						valid_form = False
						break

					# Store the IP for comparision with the next object
					last_ip = host_object['ipv4addrs'][0]['ipv4addr']

				# Store the IP for use later
				existing_host_ip = last_ip

		if not valid_form:
			# Turn envs in to a dict
			envs_dict = { env['id']: env for env in wfconfig['ENVS'] }

			return render_template(__name__ + "::nlbweb.html", title="Create NLB Web Service", envs=wfconfig['ENVS'], ssl_providers=wfconfig['SSL_PROVIDERS'], default_ssl_provider=wfconfig['DEFAULT_SSL_PROVIDER'], values=form_fields, envs_dict=envs_dict, letsencrypt_provider=wfconfig['LETSENCRYPT_PROVIDER_ID'], ssl_client_profiles=wfconfig['SSL_CLIENT_PROFILES'], default_ssl_client_profile=wfconfig['DEFAULT_SSL_CLIENT_PROFILE'], letsencrypt_enabled=wfconfig['LETSENCRYPT_ENABLED'])

		# We've now done some basic validation on the inputs

		# Build an array of nodes
		back_end_nodes = []
		for i in range(0, len(form_fields['node_hosts'])):
			back_end_nodes.append({'hostname': form_fields['node_hosts'][i], 'http_port': form_fields['node_http_ports'][i], 'https_port': form_fields['node_https_ports'][i], 'ip': form_fields['node_ips'][i]})

		# Lowercase the FQDN
		form_fields['fqdn'] = form_fields['fqdn'].lower()

		details = {'ssl': 0, 'ssl_have_cert': False, 'warnings': [], 'actions': []}
		if form_fields['enable_ssl']:
			details['ssl'] = 1

		if form_fields['enable_ssl'] and not form_fields['generate_letsencrypt']:
			# Extract certificate details
			details['ssl_have_cert'] = True
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

			# Determine if the certificate is self-signed
			details['ssl_cert_self_signed'] = details['ssl_cert_subject_ou'] == details['ssl_cert_issuer_ou'] and details['ssl_cert_subject_ou'] == details['ssl_cert_issuer_ou'] and details['ssl_cert_subject_ou'] == details['ssl_cert_issuer_ou'] and details['ssl_cert_subject_ou'] == details['ssl_cert_issuer_ou'] and details['ssl_cert_subject_ou'] == details['ssl_cert_issuer_ou']

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
				details['warnings'].append('SSL certificate subject CN (' + str(details['ssl_cert_subject_cn']) + ') does not match service FQDN (' + str(form_fields['fqdn']) + ')')

			# Ensure subjectAltName exists, and that the FQDN of the service is contained within
			if 'ssl_cert_subjectAltName' in details:
				if 'DNS:' + form_fields['fqdn'] not in details['ssl_cert_subjectAltName']:
					details['warnings'].append('SSL certificate subjectAltName does not contain the service FQDN (' + str(form_fields['fqdn']) + ')')
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

			if form_fields['ssl_provider'] == '*SELF':
				if not details['ssl_cert_self_signed']:
					details['warnings'].append('Self-signed certificate provider chosen on non-self-signed cert! No chain will be added to SSL profile. Check the certificate and SSL provider')
				else:
					if wfconfig['SSL_SELF_SIGNED_WARNING']:
						details['warnings'].append('Self-signed certificate. Not recommended for production use')
			else:
				if details['ssl_cert_self_signed']:
					details['warnings'].append('Self-signed certificate detected, which does not match chosen SSL provider. Check the certificate and SSL provider')

		## That's everything validated: now check the NLB to validate against that

		# Work out if the port numbers for HTTP / HTTPS on all the nodes are the same
		identical_http_ports = all([back_end_node['http_port'] == back_end_nodes[0]['http_port'] for back_end_node in back_end_nodes])
		if identical_http_ports:
			http_port_suffix = '-' + back_end_nodes[0]['http_port']
		else:
			http_port_suffix = '-http'
		identical_https_ports = all([back_end_node['https_port'] == back_end_nodes[0]['https_port'] for back_end_node in back_end_nodes])
		if identical_https_ports:
			https_port_suffix = '-' + back_end_nodes[0]['https_port']
		else:
			https_port_suffix = '-https'
		
		# Generate the names we think we need: pool name. Suffixed with
		# either -$http(s)_port if all the port numbers of the nodes are
		# the same or -http and -https if they differ
		pool_name_base = wfconfig['POOL_PREFIX'] + form_fields['short_service'] + envs_dict[form_fields['env']]['suffix']
		pool_name_http = pool_name_base + http_port_suffix
		pool_name_https = pool_name_base + https_port_suffix
		monitor_name_http = wfconfig['MONITOR_PREFIX'] + form_fields['short_service'] + envs_dict[form_fields['env']]['suffix'] + http_port_suffix
		monitor_name_https = wfconfig['MONITOR_PREFIX'] + form_fields['short_service'] + envs_dict[form_fields['env']]['suffix'] + https_port_suffix
		virtual_server_base = wfconfig['VIRTUAL_SERVER_PREFIX'] + form_fields['short_service'] + envs_dict[form_fields['env']]['suffix']
		virtual_server_http = virtual_server_base + '-' + str(form_fields['http_port'])
		http_profile_name = wfconfig['HTTP_PROFILE_PREFIX'] + form_fields['short_service'] + envs_dict[form_fields['env']]['suffix']

		if form_fields['enable_ssl'] and form_fields['generate_letsencrypt']:
			# See if a Let's Encrypt certificate already exists
			r = requests.get(urljoin(wfconfig['ACME_API_URL'], 'get_certificate') + '/' + form_fields['fqdn'], headers={'Content-Type': 'application/json', 'X-Client-Secret': wfconfig['ACME_API_SECRET']})
			if r.status_code == 200:
				details['actions'].append({
					'action_description': 'Retrieve existing Let\'s Encrypt certificate for ' + form_fields['fqdn'],
					'id': 'retrieve_existing_letsencrypt',
					'fqdn': form_fields['fqdn']})
				details['warnings'].append('CONFLICT: Let\'s Encrypt certificate for CN ' + form_fields['fqdn'] + ' already exists - re-using. Check the SANs afterwards to ensure they are correct!')
				
			else:
				details['actions'].append({
					'action_description': 'Generate a Let\'s Encrypt certificate for ' + form_fields['fqdn'],
					'id': 'generate_letsencrypt',
					'fqdn': form_fields['fqdn'],
					'sans': split_aliases})

		if form_fields['enable_ssl']:
			virtual_server_https = virtual_server_base + '-' + str(form_fields['https_port'])
			ssl_profile_name = wfconfig['SSL_PROFILE_PREFIX'] + form_fields['fqdn']
			ssl_cert_file = form_fields['fqdn'] + '.crt'
			ssl_key_file = form_fields['fqdn'] + '.key'

		# The logic of some of the objects we create here is as follows:
		#
		# +--------------------++------------------------------+
		# | Variables          || Results                      |
		# +-----+-------+------++------+-------+-------+-------+
		# | SSL | REDIR | BACK || HTTP | HTTPS | HTTP  | HTTPS |
		# | ON  | HTTP  | SSL  || POOL | POOL  | VS    | VS    |
		# +-----+-------+------++------+-------+-------+-------+
		# | 0   | -     | -    || 1    | 0     | 1     | 0     |
		# | 1   | 0     | 0    || 1    | 0     | 1     | 1     |
		# | 1   | 0     | 1    || 1    | 1     | 1     | 1 (S) | (S) = Server SSL Profile
		# | 1   | 1     | 0    || 1    | 0     | 1 (R) | 1     | (R) = redirected to HTTPS by NLB
		# | 1   | 1     | 1    || 0    | 1     | 1 (R) | 1 (S) |
		# +-----+-------+------++------+-------+-------+-------+

		# Determine if we need pools (and indeed monitors for those pools) for both 
		# HTTP and HTTPS. We need an HTTP pool (and monitor) in the following situations:
		#  - SSL is disabled (regardless of anything else)
		#  - SSL is enabled, and we're not forcing a redirect from HTTP to HTTPS on the NLB
		#  - SSL is enabled, we are forcing a redirect to HTTPS, but the backend is not encrypted
		# We need an HTTPS pool (and monitor) in the situation of SSL being enabled and
		# we're doing SSL to the backend (any redirect from HTTP to HTTPS is irrelevant)
		create_http_pools = (not form_fields['enable_ssl']) or (form_fields['enable_ssl'] and not form_fields['redirect_http']) or (form_fields['enable_ssl'] and form_fields['redirect_http'] and not form_fields['encrypt_backend'])
		create_https_pools = form_fields['enable_ssl'] and form_fields['encrypt_backend']

		# Check if an Infoblox host record already exists for us
		if existing_host_ref is None:
			# Set up an action to allocate an IP from Infoblox if we haven't specified one
			if form_fields['ip'] == '':
				details['actions'].append({
					'action_description': 'Allocate an IP address from ' + str(envs_dict[form_fields['env']]['network']) + ' in Infoblox',
					'id': 'allocate_ip',
					'network': envs_dict[form_fields['env']]['network'],
					'fqdn': form_fields['fqdn'],
					'aliases': split_aliases})
			else:
				details['actions'].append({
					'action_description': 'Create host object for ' + form_fields['fqdn'] + ' in Infoblox',
					'id': 'create_host',
					'ip': form_fields['ip'],
					'fqdn': form_fields['fqdn'],
					'aliases': split_aliases})
		else:
			if form_fields['ip'] == '':
				# If we're auto-allocating an IP and the record already exists
				# then use that one, and warn that we're changing
				details['warnings'].append('SKIPPED: Host object for ' + form_fields['fqdn'] + ' already exists in Infoblox with IP ' + existing_host_ip + ' - using that instead of allocating')
				form_fields['ip'] = existing_host_ip
			else:
				if form_fields['ip'] != existing_host_ip:
					# If we're not auto-allocating, and the IPs differ, then
					# we have to use the one that's there to not break things
					details['warnings'].append('CONFLICT: Host object for ' + form_fields['fqdn'] + ' already exists in Infoblox with IP ' + existing_host_ip + ' - using that instead of ' + form_fields['ip'])
					form_fields['ip'] = existing_host_ip

		# Check if any of the nodes are already present on the NLB
		for back_end_node in back_end_nodes:
			back_end_node_name = back_end_node['hostname'].lower()

			# Check if a node of the same name exists
			if bigip.tm.ltm.nodes.node.exists(name=back_end_node_name, partition=form_fields['partition']):
				# If it exists, load the object
				nlb_node = bigip.tm.ltm.nodes.node.load(name=back_end_node_name, partition=form_fields['partition'])

				# Check the IP of the existing object to see if we need to create or not
				if back_end_node['ip'] != nlb_node.address:
					details['warnings'].append('CONFLICT: Node ' + back_end_node['hostname'] + ' already exists with different IP. Not updating.')
				else:
					details['warnings'].append('SKIPPED: Node ' + back_end_node['hostname'] + ' already exists with correct IP. Not creating.')
			else:
				details['actions'].append({
					'action_description': 'Create node ' + back_end_node['hostname'] + ' on ' + bigip_host,
					'id': 'create_node',
					'name': back_end_node['hostname'],
					'description': form_fields['service'] + ' ' + envs_dict[form_fields['env']]['name'] + ' Node',
					'ip': back_end_node['ip'],
					'bigip': bigip_host,
					'partition': form_fields['partition']})

		if create_http_pools:
			# Check if the HTTP monitor already exists
			if bigip.tm.ltm.monitor.https.http.exists(name=monitor_name_http, partition=form_fields['partition']):
				details['warnings'].append('SKIPPED: Monitor ' + monitor_name_http + ' already exists. Not creating or updating.')
			else:
				details['actions'].append({
					'action_description': 'Create HTTP monitor ' + monitor_name_http + ' on ' + bigip_host,
					'id': 'create_monitor',
					'name': monitor_name_http,
					'fqdn': form_fields['fqdn'],
					'description': form_fields['service'] + ' ' + envs_dict[form_fields['env']]['name'] + ' HTTP Monitor',
					'parent': 'http',
					'url': form_fields['monitor_url'],
					'response': form_fields['monitor_response'],
					'bigip': bigip_host,
					'partition': form_fields['partition']})

		if create_https_pools:
			# Check if the HTTPS monitor already exists
			if bigip.tm.ltm.monitor.https_s.https.exists(name=monitor_name_https, partition=form_fields['partition']):
				details['warnings'].append('SKIPPED: Monitor ' + monitor_name_https + ' already exists. Not creating or updating.')
			else:
				details['actions'].append({
					'action_description': 'Create HTTPS monitor ' + monitor_name_https + ' on ' + bigip_host,
					'id': 'create_monitor',
					'name': monitor_name_https,
					'fqdn': form_fields['fqdn'],
					'description': form_fields['service'] + ' ' + envs_dict[form_fields['env']]['name'] + ' HTTPS Monitor',
					'parent': 'https',
					'url': form_fields['monitor_url'],
					'response': form_fields['monitor_response'],
					'bigip': bigip_host,
					'partition': form_fields['partition']})

		if create_http_pools:
			# Check if the HTTP pool already exists. 
			if bigip.tm.ltm.pools.pool.exists(name=pool_name_http, partition=form_fields['partition']):
				details['warnings'].append('SKIPPED: Pool ' + pool_name_http + ' already exists. Not creating or updating.')
			else:
				details['actions'].append({
					'action_description': 'Create HTTP Pool ' + pool_name_http + ' on ' + bigip_host,
					'id': 'create_pool',
					'name': pool_name_http,
					'description': form_fields['service'] + ' ' + envs_dict[form_fields['env']]['name'] + ' HTTP Pool',
					'monitor': monitor_name_http,
					'members': [back_end_node['hostname'] + ':' + back_end_node['http_port'] for back_end_node in back_end_nodes],
					'bigip': bigip_host,
					'partition': form_fields['partition']})

		if create_https_pools:
			# Check if the HTTPS pool already exists
			if bigip.tm.ltm.pools.pool.exists(name=pool_name_https, partition=form_fields['partition']):
				details['warnings'].append('SKIPPED: Pool ' + pool_name_https + ' already exists. Not creating or updating.')
			else:
				details['actions'].append({
					'action_description': 'Create HTTPS Pool ' + pool_name_https + ' on ' + bigip_host,
					'id': 'create_pool',
					'name': pool_name_https,
					'description': form_fields['service'] + ' ' + envs_dict[form_fields['env']]['name'] + ' HTTPS Pool',
					'monitor': monitor_name_https,
					'members': [back_end_node['hostname'] + ':' + back_end_node['https_port'] for back_end_node in back_end_nodes],
					'bigip': bigip_host,
					'partition': form_fields['partition']})

		if form_fields['enable_ssl']:
			if bigip.tm.sys.crypto.keys.key.exists(name=ssl_key_file, partition=form_fields['partition']):
				details['warnings'].append('SKIPPED: SSL Private Key ' + ssl_key_file + ' already exists. Not creating or updating.')
			else:
				new_action = {
					'action_description': 'Upload private key ' + ssl_key_file + ' on ' + bigip_host,
					'id': 'upload_key',
					'filename': ssl_key_file,
					'bigip': bigip_host,
					'partition': form_fields['partition']
				}
				if form_fields['generate_letsencrypt']:
					new_action['from_letsencrypt'] = True
					new_action['action_description'] = new_action['action_description'] + ' (from Let\'s Encrypt)'
				else:
					new_action['content'] = form_fields['ssl_key']
				details['actions'].append(new_action)
			if bigip.tm.sys.crypto.certs.cert.exists(name=ssl_cert_file, partition=form_fields['partition']):
				details['warnings'].append('SKIPPED: SSL Certificate ' + ssl_cert_file + ' already exists. Not creating or updating.')
			else:
				new_action = {
					'action_description': 'Upload certificate ' + ssl_cert_file + ' on ' + bigip_host,
					'id': 'upload_cert',
					'filename': ssl_cert_file,
					'bigip': bigip_host,
					'partition': form_fields['partition']
				}
				if form_fields['generate_letsencrypt']:
					new_action['from_letsencrypt'] = True
					new_action['action_description'] = new_action['action_description'] + ' (from Let\'s Encrypt)'
				else:
					new_action['content'] = form_fields['ssl_cert']
				details['actions'].append(new_action)
				
		# Check if the SSL Profile already exists
		if form_fields['enable_ssl']:
			if bigip.tm.ltm.profile.client_ssls.client_ssl.exists(name=ssl_profile_name, partition=form_fields['partition']):
				details['warnings'].append('SKIPPED: SSL Client Profile ' + ssl_profile_name + ' already exists. Not creating or updating.')
			else:
				new_action = {
					'action_description': 'Create SSL Client Profile ' + ssl_profile_name + ' on ' + bigip_host,
					'id': 'create_ssl_client_profile',
					'name': ssl_profile_name,
					'key': ssl_key_file,
					'cert': ssl_cert_file,
					'parent': ssl_client_profiles_dict[form_fields['ssl_client_profile']]['profile'],
					'bigip': bigip_host,
					'partition': form_fields['partition']
				}
				if form_fields['ssl_provider'] != '*SELF':
					new_action['chain'] = ssl_providers_dict[form_fields['ssl_provider']]['nlb-chain-file']
				details['actions'].append(new_action)

		# Determine if we need to create an HTTP profile
		create_http_profile = False
		if form_fields['outage_page'] or (form_fields['enable_ssl'] and form_fields['enable_hsts']):
			# HSTS or an outage page always requires a custom HTTP profile
			create_http_profile = True
		else:
			# If we're using X-Forwarded-For and the config doesn't
			# give us a parent HTTP profile, then we also need to
			# create a HTTP profile
			if form_fields['use_xforwardedfor'] and wfconfig['HTTP_PROFILE_XFORWARDEDFOR'] is None:
				create_http_profile = True

		# Check to see if the HTTP profile already exists
		if create_http_profile:
			if bigip.tm.ltm.profile.https.http.exists(name=http_profile_name, partition=form_fields['partition']):
				details['warnings'].append('SKIPPED: HTTP Profile ' + http_profile_name + ' already exists. Not creating or updating.')
			else:
				new_action = {
					'action_description': 'Create HTTP Profile ' + http_profile_name + ' on ' + bigip_host,
					'id': 'create_http_profile',
					'name': http_profile_name,
					'bigip': bigip_host,
					'partition': form_fields['partition'],
					'hsts': form_fields['enable_hsts'],
				}
				if form_fields['use_xforwardedfor']:
					if wfconfig['HTTP_PROFILE_XFORWARDEDFOR'] is None:
						new_action['parent'] = wfconfig['HTTP_PROFILE_DEFAULT']
						new_action['x-forwarded-for'] = True
					else:
						new_action['parent'] = wfconfig['HTTP_PROFILE_XFORWARDEDFOR']
				if form_fields['outage_page'] != '':
					new_action['outage_page'] = form_fields['outage_page']
				details['actions'].append(new_action)

		# Check to see if the HTTP virtual server already exists
		if bigip.tm.ltm.virtuals.virtual.exists(name=virtual_server_http, partition=form_fields['partition']):
			details['warnings'].append('SKIPPED: Virtual Server ' + virtual_server_http + ' already exists. Not creating or updating.')
		else:
			new_action = {
				'action_description': 'Create HTTP Virtual Server ' + virtual_server_http + ' on ' + bigip_host,
				'id': 'create_virtual_server',
				'name': virtual_server_http,
				'port': form_fields['http_port'],
				'irules': [],
				'bigip': bigip_host,
				'partition': form_fields['partition'],
				'description': form_fields['service'] + ' ' + envs_dict[form_fields['env']]['name'] + ' Virtual Server HTTP'
			}

			# This iRule must come first as it needs to take precedence over
			# other iRules (particularly any HTTPS redirect)
			if form_fields['generate_letsencrypt']:
				new_action['irules'].append(wfconfig['LETSENCRYPT_IRULE'])

			if form_fields['ip'] != '':
				new_action['ip'] = form_fields['ip']
			if form_fields['redirect_http']:
				new_action['irules'].append('/Common/_sys_https_redirect')
				new_action['http_profile'] = '/Common/http'
			else:
				new_action['pool'] = pool_name_http

				# The HTTP profile only makes a difference (in our case) when
				# we're not forcing to HTTPS
				if create_http_profile:
					new_action['http_profile'] = http_profile_name
				else:
					if form_fields['use_xforwardedfor']:
						new_action['http_profile'] = wfconfig['HTTP_PROFILE_XFORWARDEDFOR']
				
			# Any other iRules come after the HTTPS redirect if the user chose it
			new_action['irules'].extend(http_irules)

			details['actions'].append(new_action)
		
		# Check to see if the HTTPS virtual server already exists
		if form_fields['enable_ssl']:
			if bigip.tm.ltm.virtuals.virtual.exists(name=virtual_server_https, partition=form_fields['partition']):
				details['warnings'].append('SKIPPED: Virtual Server ' + virtual_server_https + ' already exists. Not creating or updating.')
			else:
				new_action = {
					'action_description': 'Create HTTPS Virtual Server ' + virtual_server_https + ' on ' + bigip_host,
					'id': 'create_virtual_server',
					'name': virtual_server_https,
					'port': form_fields['https_port'],
					'irules': https_irules,
					'ssl_client_profile': ssl_profile_name,
					'bigip': bigip_host,
					'partition': form_fields['partition'],
					'description': form_fields['service'] + ' ' + envs_dict[form_fields['env']]['name'] + ' Virtual Server HTTPS',
				}
				if form_fields['ip'] != '':
					new_action['ip'] = form_fields['ip']
				if form_fields['encrypt_backend']:
					new_action['ssl_server_profile'] = 'serverssl'
					new_action['pool'] = pool_name_https
				else:
					new_action['pool'] = pool_name_http
				if create_http_profile:
					new_action['http_profile'] = http_profile_name
				else:
					if form_fields['use_xforwardedfor']:
						new_action['http_profile'] = wfconfig['HTTP_PROFILE_XFORWARDEDFOR']
					else:
						new_action['http_profile'] = '/Common/http'

				details['actions'].append(new_action)

		# If there is only one action which is generating/retrieving a 
		# certificate, then drop the action
		if len(details['actions']) == 1 and details['actions'][0]['id'] in ['generate_letsencrypt', 'retrieve_existing_letsencrypt']:
			del details['actions'][0]

		# If after all that there are no actions, log a warning
		if len(details['actions']) == 0:
			details['warnings'].append('No actions to perform. Is the service already set up?')

		# Turn the actions list into a signed JSON document via itsdangerous
		signer = JSONWebSignatureSerializer(app.config['SECRET_KEY'])
		json_data = signer.dumps(details['actions'])

		# Show the user the details, warnings, and what we're going to do
		return render_template(__name__ + "::validate.html", title="Create NLB Web Service", details=details, json_data=json_data)

@workflow.route('validate', title='Create NLB Web Service', permission="nlbweb.create", methods=['POST'], menu=False)
def nlbweb_validate():
	# Get the workflow settings
	wfconfig = workflow.config
	
	# If we've got the confirmation, start the task:
	if 'submit' in request.form and 'actions' in request.form:
		options = {}
		options['wfconfig'] = wfconfig

		## Decode the actions data 
		signer = JSONWebSignatureSerializer(app.config['SECRET_KEY'])
		try:
			options['actions'] = signer.loads(request.form['actions'])
		except itsdangerous.BadSignature as ex:
			abort(400)

		# Connect to NeoCortex and start the task
		neocortex = cortex.lib.core.neocortex_connect()
		task_id = neocortex.create_task(__name__, session['username'], options, description="Creates the necessary objects on the NLB to run a basic HTTP(S) website / service")

		# Redirect to the status page for the task
		return redirect(url_for('task_status', id=task_id))
	else:
		return abort(400)

@workflow.route('dnslookup', permission="nlbweb.create", menu=False)
def nlbweb_dns_lookup():
	
	host = request.args['host']

	# Load the Corpus library (for Infoblox helper functions)
	corpus = Corpus(g.db, app.config)
	
	return jsonify(corpus.dns_lookup(host))

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

def parse_irule_list(irules_text, bigip):
	# On empty string, return empty list
	if len(irules_text) == 0:
		return []

	# Split the space-separated string and filter out empty values
	irules_list = [x for x in irules_text.split(' ') if x != '']

	# Start a results list
	result = []

	# Iterate over all the rules in the list
	for irule in irules_list:
		# All the names should start with a slash and can be at minimum four 
		# characters long (e.g. /a/b)
		if len(irule) < 4 or irule[0] != '/':
			raise ValueError('Invalid iRule name: ' + irule)

		# Split the iRule into partition and name
		irule_split = irule.split('/')

		# We should have three entries: ['', partition_name, rule_name]
		if len(irule_split) != 3:
			raise ValueError('Invalid iRule name: ' + irule)

		# Grab the appropriate values
		irule_partition = irule_split[1]
		irule_name = irule_split[2]

		# Both the partition name and the iRule name should be non-empty
		if len(irule_name) == 0 or len(irule_partition) == 0:
			raise ValueError('Invalid iRule name: ' + irule)
		
		# The name looks to be at least semi-valid. See if it exists
		if bigip.tm.ltm.rules.rule.exists(name=irule_name, partition=irule_partition):
			result.append(irule)
		else:
			raise ValueError('iRule does not exist: ' + irule)

	return result
