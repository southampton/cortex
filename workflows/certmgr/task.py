#### Create SSL Certificate Workflow Task

import requests, time

# For NLB API
from f5.bigip import ManagementRoot

# For certificate generation
import OpenSSL as openssl

def run(helper, options):
	# Configuration of task
	config = options['wfconfig']

	if options['provider']['type'] == 'self':
		result = create_self_signed_cert(helper, options)
	elif options['provider']['type'] == 'acme':
		result = create_acme_cert(helper, options)

# Code for uploading to NLB
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

# For ACME-challenge certificates
def create_acme_cert(helper, options):
	# Get the configuration
	config = options['wfconfig']

	# Get the Infoblox host object reference for in the ACME Endpoint
	helper.event('add_acme_dns', 'Adding aliases to ACME host object in Infoblox')
	ref = helper.lib.infoblox_get_host_refs(config['ACME_HOST_FQDN'], config['ACME_DNS_VIEW'])
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
	time.sleep(config['DNS_WAIT_TIME'])
	helper.end_event(success=True)

	# Call the UoS ACME API to request the cert
	helper.event('generate_acme_cert', 'Requesting certificate for ' + options['fqdn'] + ' from ACME server')
	r = requests.post('http://' + options['acme']['hostname'] + '/create_certificate', json={'fqdn': options['fqdn'], 'sans': options['aliases']}, headers={'Content-Type': 'application/json', 'X-Client-Secret': options['acme']['api_token']})
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

	helper.event('prep_download', description="Preparing certificates for download")

	# Get the certificates
	helper.lib.rdb.setex("certmgr/" + str(helper.task_id) + "/certificate", 3600, acme_response['certificate_text'])
	helper.lib.rdb.setex("certmgr/" + str(helper.task_id) + "/private", 3600, acme_response['privatekey_text'])
	helper.lib.rdb.setex("certmgr/" + str(helper.task_id) + "/chain", 3600, acme_response['chain'])

	helper.end_event(description='Certificates ready for download', success=True)

	# Upload to NLB if required
	if options['provider']['upload_nlb']:
		upload_cert_key_to_nlb(helper, options, acme_response['certificate_text'], acme_response['privatekey_text'])

	# Create SSL Profile

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
		san_extension = openssl.crypto.X509Extension('subjectAltName', False, san_aliases_string)

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

	helper.lib.rdb.setex("certmgr/" + str(helper.task_id) + "/certificate", 3600, pem_cert)
	helper.lib.rdb.setex("certmgr/" + str(helper.task_id) + "/private", 3600, pem_key)

	helper.end_event(description='Certificates ready for download', success=True)

	# Upload to NLB if required
	if options['provider']['nlb_upload']:
		upload_cert_key_to_nlb(helper, options, pem_cert, pem_key)
