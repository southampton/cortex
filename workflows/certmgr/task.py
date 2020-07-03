#### Create SSL Certificate Workflow Task

import time

# For DNS resolution
import DNS
# For certificate generation
import OpenSSL as openssl
import requests
# For NLB API
from f5.bigip import ManagementRoot


def run(helper, options):
	# check if workflows are locked
	if not helper.lib.check_workflow_lock():
		raise Exception("Workflows are currently locked")

	if options['provider']['type'] == 'self':
		create_self_signed_cert(helper, options)
	elif options['provider']['type'] == 'acme':
		create_acme_cert(helper, options)
	elif options['provider']['type'] == 'entca':
		create_entca_cert(helper, options)

# Uploads a certificate and key pair to the load balancers
def upload_cert_key_to_nlb(helper, options, cert, key):
	# Generate filenames
	key_filename = options['fqdn'] + '.key'
	cert_filename = options['fqdn'] + '.crt'

	# Upload key
	try:
		helper.event('upload_key', 'Uploading key to load balancer ' + options['nlb']['hostname'])
		bigip = ManagementRoot(options['nlb']['hostname'], options['nlb']['username'], options['nlb']['password'])
		bigip.shared.file_transfer.uploads.upload_bytes(key, key_filename)
		param_set = {'name': key_filename, 'partition': options['nlb']['partition'], 'from-local-file': '/var/config/rest/downloads/' + key_filename}
		bigip.tm.sys.crypto.keys.exec_cmd('install', **param_set)
		helper.end_event(description='Uploaded key to load balancer ' + options['nlb']['hostname'])

		helper.event('upload_cert', 'Uploading certificate to load balancer ' + options['nlb']['hostname'])
		bigip.shared.file_transfer.uploads.upload_bytes(cert, cert_filename)
		param_set = {'name': cert_filename, 'partition': options['nlb']['partition'], 'from-local-file': '/var/config/rest/downloads/' + cert_filename}
		bigip.tm.sys.crypto.certs.exec_cmd('install', **param_set)
		helper.end_event(description='Uploaded certificate to load balancer ' + options['nlb']['hostname'])
	except Exception as e:
		helper.end_event(description='Error uploading data to load balancer: ' + str(e), success=False)

def redis_cache_cert(helper, options, cert, key, chain=None):
	prefix = 'certmgr/' + str(helper.task_id) + '/'
	helper.lib.rdb.setex(prefix + "certificate", options['wfconfig']['CERT_CACHE_TIME'], cert)
	helper.lib.rdb.setex(prefix + "private", options['wfconfig']['CERT_CACHE_TIME'], key)
	if chain is not None:
		helper.lib.rdb.setex(prefix + "chain", options['wfconfig']['CERT_CACHE_TIME'], chain)

# Creates an SSL profile on the load balancers
def create_ssl_profile(helper, options, chain_cn=None):
	# Name is /<parition>/<prefix><fqdn><suffix>
	profile_name = '/' + options['nlb']['partition'] + '/' + (str(options['wfconfig']['CLIENT_SSL_PROFILE_PREFIX']) if 'CLIENT_SSL_PROFILE_PREFIX' in options['wfconfig'] else '') + options['fqdn'] + (str(options['wfconfig']['CLIENT_SSL_PROFILE_SUFFIX']) if 'CLIENT_SSL_PROFILE_SUFFIX' in options['wfconfig'] else '')

	helper.event('create_ssl_profile', 'Creating client SSL profile ' + profile_name + ' on ' + options['nlb']['hostname'])

	cert_key_chain = {
		'name': options['fqdn'] + '_',
		'cert': '/' + options['nlb']['partition'] + '/' + options['fqdn'] + '.crt',
		'key': '/' + options['nlb']['partition'] + '/' + options['fqdn'] + '.key'
	}

	# Add in the chain cert and update the name
	if chain_cn is not None:
		if chain_cn in options['wfconfig']['NLB_INTERMEDIATE_CN_FILES']:
			cert_key_chain['chain'] = options['wfconfig']['NLB_INTERMEDIATE_CN_FILES'][chain_cn]
			cert_key_chain['name'] = cert_key_chain['name'] + chain_cn.replace(' ', '').replace('\'', '')
		else:
			cert_key_chain['name'] = cert_key_chain['name'] + 'missingchain'
	else:
		cert_key_chain['name'] = cert_key_chain['name'] + 'selfsigned'

	# Add in OCSP stapling parameters if required
	if chain_cn in options['wfconfig']['NLB_INTERMEDIATE_CN_OCSP_STAPLING_PARAMS']:
		cert_key_chain['ocspStaplingParams'] = options['wfconfig']['NLB_INTERMEDIATE_CN_OCSP_STAPLING_PARAMS'][chain_cn]

	ssl_profile = {
		'name': profile_name,
		'defaultsFrom': options['nlb']['parent-ssl-profile'],
		'certKeyChain': [cert_key_chain]
	}

	bigip = ManagementRoot(options['nlb']['hostname'], options['nlb']['username'], options['nlb']['password'])
	bigip.tm.ltm.profile.client_ssls.client_ssl.create(**ssl_profile)

	helper.end_event(description='Creating client SSL profile ' + profile_name + ' on ' + options['nlb']['hostname'], success=True)

# For ACME-challenge certificates
def create_acme_cert(helper, options):
	# Get the configuration
	config = options['wfconfig']

	# Get the Infoblox host object reference for in the ACME Endpoint
	helper.event('add_acme_dns', 'Adding aliases to ACME host object in Infoblox')
	ref = helper.lib.infoblox_get_host_refs(options['acme']['acme_target_hostname'], config['ACME_DNS_VIEW'])
	if ref is None or (type(ref) is list and len(ref) == 0):
		raise Exception('Failed to get host ref for ACME endpoint')

	# Add the alias to the host object temporarily for the FQDN
	helper.lib.infoblox_add_host_record_alias(ref[0], options['fqdn'])

	# Do we need to do the SANs too?
	helper.lib.infoblox_add_host_record_alias(ref[0], options['aliases'])

	# End event
	helper.end_event(description='Added aliases to ACME host object in Infoblox', success=True)

	# We might need to wait for the external nameservers to catch up
	helper.event('dns_wait', 'Waiting for DNS updates')
	if 'DNS_PRE_WAIT_TIME' in config:
		time.sleep(config['DNS_PRE_WAIT_TIME'])
	wait_for_dns(config['EXTERNAL_DNS_SERVER_IP'], options['fqdn'], timeout=config['DNS_WAIT_TIME'], cname=options['acme']['acme_target_hostname'])
	helper.end_event(success=True)

	# Call the UoS ACME API to request the cert
	helper.event('generate_acme_cert', 'Requesting certificate for ' + options['fqdn'] + ' from ACME server')
	r = requests.post('https://' + options['acme']['hostname'] + '/create_certificate', json={'fqdn': options['fqdn'], 'sans': options['aliases']}, headers={'Content-Type': 'application/json', 'X-Client-Secret': options['acme']['api_token']}, verify=options['acme']['verify_ssl'])
	if r is None:
		raise Exception('Request to ACME Create Certificate Endpoint failed')
	if r.status_code != 200:
		raise Exception('Request to ACME Create Certificate Endpoint failed with error code ' + str(r.status_code) + ': ' + r.text)
	acme_response = r.json()
	helper.end_event(description='Requested certificate from ACME server')

	# Remove the aliases from the host object
	helper.event('remove_acme_dns', 'Removing aliases to ACME host object in Infoblox')
	helper.lib.infoblox_remove_host_record_alias(ref[0], options['fqdn'])
	helper.lib.infoblox_remove_host_record_alias(ref[0], options['aliases'])
	helper.end_event(description='Removed aliases to ACME host object in Infoblox', success=True)

	# Cache the certificates
	helper.event('prep_download', description="Preparing certificates for download")
	redis_cache_cert(helper, options, acme_response['certificate'], acme_response['privatekey'], acme_response['chain'])
	helper.end_event(description='Certificates ready for download', success=True)

	# If we need to create an SSL profile...
	if options['create_ssl_profile']:
		# Upload to NLB if required
		if options['provider']['nlb_upload']:
			upload_cert_key_to_nlb(helper, options, acme_response['certificate'], acme_response['privatekey'])

		create_ssl_profile(helper, options, acme_response['chain_cn'])

# For Enterprise certificates
def create_entca_cert(helper, options):
	# Get the configuration
	options['wfconfig']

	# Call the Enterprise CA API to request the cert
	helper.event('generate_entca_cert', 'Requesting certificate for ' + options['fqdn'] + ' from Enterprise CA API')
	r = requests.post('https://' + options['entca']['hostname'] + '/create_entca_certificate', json={'fqdn': options['fqdn'], 'sans': options['aliases']}, headers={'Content-Type': 'application/json', 'X-Client-Secret': options['entca']['api_token']}, verify=options['entca']['verify_ssl'])
	if r is None:
		raise Exception('Request to Enterprise CA API Create Certificate Endpoint failed')
	if r.status_code != 200:
		raise Exception('Request to Enterprise CA API Create Certificate Endpoint failed with error code ' + str(r.status_code) + ': ' + r.text)
	entca_response = r.json()
	helper.end_event(description='Requested certificate from Enterprise CA API')

	# Cache the certificates
	helper.event('prep_download', description="Preparing certificates for download")
	redis_cache_cert(helper, options, entca_response['certificate'], entca_response['privatekey'], entca_response['chain'])
	helper.end_event(description='Certificates ready for download', success=True)

	# If we need to create an SSL profile...
	if options['create_ssl_profile']:
		# Upload to NLB if required
		if options['provider']['nlb_upload']:
			upload_cert_key_to_nlb(helper, options, entca_response['certificate'], entca_response['privatekey'])

		create_ssl_profile(helper, options, entca_response['chain_cn'])

# For self-signed certificates
def create_self_signed_cert(helper, options):

	helper.event('generate_key', 'Generate ' + str(options['key_size']) + ' bit private key')
	try:
		key = openssl.crypto.PKey()
		key.generate_key(openssl.crypto.TYPE_RSA, options['key_size'])
		helper.end_event(description='Generated ' + str(options['key_size']) + ' bit private key')
	except Exception as e:
		helper.end_event(description='Failed to generate private key: ' + str(e), success=False)
		return False

	helper.event('generate_cert', 'Generate self-signed certificate for ' + str(options['fqdn']))
	try:
		# Build the SAN X509v3 extension
		san_aliases_string = ','.join(['DNS:' + alias for alias in (options['aliases'] + [options['fqdn']])])
		san_extension = openssl.crypto.X509Extension(b'subjectAltName', False, san_aliases_string.encode('utf-8'))

		# Build the certificate
		cert = openssl.crypto.X509()
		subject = cert.get_subject()
		subject.C = options['wfconfig']['CERT_SELF_SIGNED_C']
		subject.ST = options['wfconfig']['CERT_SELF_SIGNED_ST']
		subject.L = options['wfconfig']['CERT_SELF_SIGNED_L']
		subject.O = options['wfconfig']['CERT_SELF_SIGNED_O']
		subject.OU = options['wfconfig']['CERT_SELF_SIGNED_OU']
		subject.CN = options['fqdn']
		cert.set_serial_number(1)
		cert.gmtime_adj_notBefore(0)
		cert.gmtime_adj_notAfter(int(options['length']) * 24 * 60 * 60)
		cert.set_issuer(cert.get_subject())
		cert.set_pubkey(key)

		# Add the SANs extension
		cert.add_extensions([san_extension])

		# Self-sign the certificate
		cert.sign(key, 'sha256')
		helper.end_event(description='Generated self-signed certificate for ' + str(options['fqdn']))
	except Exception as e:
		helper.end_event(description='Failed to generate self-signed certificate: ' + str(e), success=False)
		return False

	helper.event('prep_download', description="Preparing certificates for download")

	# Get the certificates
	pem_cert = openssl.crypto.dump_certificate(openssl.crypto.FILETYPE_PEM, cert)
	pem_key = openssl.crypto.dump_privatekey(openssl.crypto.FILETYPE_PEM, key)

	# Cache
	redis_cache_cert(helper, options, pem_cert, pem_key, None)

	helper.end_event(description='Certificates ready for download', success=True)

	# If we need to create an SSL profile...
	if options['create_ssl_profile']:
		# Upload to NLB if required
		if options['provider']['nlb_upload']:
			upload_cert_key_to_nlb(helper, options, pem_cert, pem_key)

		create_ssl_profile(helper, options)

################################################################################

def wait_for_dns(external_dns_server, fqdn, timeout=30, address=None, cname=None):
	"""Waits for a DNS record to appear in all nameservers for the domain."""

	# Input validation
	if external_dns_server is None or len(external_dns_server) == 0:
		raise ValueError("An 'external_dns_server' IP address must be specified")
	if address is None and cname is None:
		raise ValueError("A value for 'address' or 'cname' must be specified")

	# Split the FQDN in to each of it's domain parts
	split_fqdn = fqdn.split('.')

	# Further input validation
	if len(split_fqdn) <= 1:
		raise ValueError("'fqdn' must specify a fully-qualified domain name")

	# Search for NS records for each part recursively (e.g. for a.b.c.d, then b.c.d, then c.d, then d)
	for i in range(len(split_fqdn) - 1):
		# Rejoin the domain name
		ns_fqdn_search = '.'.join(split_fqdn[i:])

		# Perform the DNS request
		r = DNS.DnsRequest(ns_fqdn_search, qtype='NS', server=[external_dns_server])
		ns_res = r.req()

		# If we got NS servers, then stop searching. The explicit check for NS records is
		# required because doing an NS record search for a record that is a CNAME doesn't
		# do what you might expect.
		if ns_res.header['status'] == 'NOERROR' and len([answer for answer in ns_res.answers if answer['typename'] == 'NS']) > 0:
			break
	else:
		# We reached the end of the list, and didn't find a valid NS record, so raise exception
		raise Exception('Unable to find NS records for domain')

	# Extract the list of NS servers we need to check
	ns_list = [answer['data'] for answer in ns_res.answers if answer['typename'] == 'NS']

	# Empty list of nameservers that contain the right result
	completed_name_servers = []
	start_time = time.time()

	# Determine the query type
	if address is not None:
		# Determine if we're doing a v6 lookup
		if ':' in address:
			qtype = 'AAAA'

			# The data we get back from DNS is "packed" (byte representation)
			address = ipaddress.IPv6Address(str(address)).packed
		else:
			qtype = 'A'
	elif cname is not None:
		qtype = 'CNAME'

		# CNAME checks needs to be case-insensitive
		cname = cname.lower()

	# Loop whilst we're waiting for all the nameservers to pick up, but don't exceed our timeout
	while len(completed_name_servers) != len(ns_list) and time.time() - start_time < timeout:
		# Iterate over all nameservers
		for nameserver in ns_list:
			# Skip past nameservers we've already validated
			if nameserver in completed_name_servers:
				continue

			# Perform the DNS lookup
			r = DNS.DnsRequest(fqdn, qtype=qtype, server=[nameserver])
			res = r.req()

			# If the query succeeded
			if res.header['status'] == 'NOERROR':
				# Iterate over the answers and make sure we have an A record for the address
				for answer in res.answers:
					if address is not None and answer['typename'] == qtype and answer['data'] == address:
						completed_name_servers.append(nameserver)
					elif cname is not None and answer['typename'] == qtype and answer['data'].lower() == cname:
						completed_name_servers.append(nameserver)

		# If we've not got all nameservers, sleep a little
		if len(completed_name_servers) != len(ns_list):
			time.sleep(1)

	# If we didn't ever succeed, raise an exception
	if len(completed_name_servers) != len(ns_list):
		raise Exception("Timeout whilst waiting for DNS records to update. Completed: " + str(completed_name_servers))
