#### F5 BigIP NLB Create HTTP Site Workflow Task

from urlparse import urljoin
import requests, time

# For NLB API
from f5.bigip import ManagementRoot

def run(helper, options):

	# Configuration of task
	config = options['wfconfig']
	actions = options['actions']

	# Validate we get a list
	assert type(actions) is list, "actions list is not a Python list object"

	## Allocate a hostname #################################################

	task_globals = {}

	# Start the task
	for action in actions:
		# Start the event
		helper.event(action['id'], action['action_description'])

		if action['id'] == 'generate_letsencrypt':
			r, task_globals = action_generate_letsencrypt(action, helper, config, task_globals)
		elif action['id'] == 'allocate_ip':
			r, task_globals = action_allocate_ip(action, helper, config, task_globals)
		elif action['id'] == 'create_node':
			r, task_globals = action_create_node(action, helper, config, task_globals)
		elif action['id'] == 'create_monitor':
			r, task_globals = action_create_monitor(action, helper, config, task_globals)
		elif action['id'] == 'create_pool':
			r, task_globals = action_create_pool(action, helper, config, task_globals)
		elif action['id'] == 'upload_key':
			r, task_globals = action_upload_key(action, helper, config, task_globals)
		elif action['id'] == 'upload_cert':
			r, task_globals = action_upload_cert(action, helper, config, task_globals)
		elif action['id'] == 'create_ssl_client_profile':
			r, task_globals = action_create_ssl_client_profile(action, helper, config, task_globals)
		elif action['id'] == 'create_http_profile':
			r, task_globals = action_create_http_profile(action, helper, config, task_globals)
		elif action['id'] == 'create_virtual_server':
			r, task_globals = action_create_virtual_server(action, helper, config, task_globals)

		# End the event (don't change the description) if the action
		# succeeded. The action_* functions either raise Exceptions or
		# end the events with a failure message on errors.
		if r:
			helper.end_event()

################################################################################

def connect_bigip(bigip_host, config):
	return ManagementRoot(bigip_host, config['NLB_USERNAME'], config['NLB_PASSWORD'])

################################################################################

def action_generate_letsencrypt(action, helper, config, task_globals):
	# Get the Infoblox host object reference for in the ACME Endpoint
	ref = helper.lib.infoblox_get_host_refs(config['LETSENCRYPT_HOST_FQDN'], config['LETSENCRYPT_DNS_VIEW'])
	if ref is None or (type(ref) is list and len(ref) == 0):
		raise Exception('Failed to get host ref for Let\'s Encrypt ACME endpoint')
	
	# Add the alias to the host object temporarily for the FQDN
	helper.lib.infoblox_add_host_record_alias(ref[0], action['fqdn'])

	# Do we need to do the SANs too?
	helper.lib.infoblox_add_host_record_alias(ref[0], action['sans'])

	# We might need to wait for the external nameservers to catch up
	time.sleep(config['DNS_WAIT_TIME'])

	# Call the UoS ACME API to request the cert
	r = requests.post(urljoin(config['ACME_API_URL'], 'create_certificate'), json={'fqdn': action['fqdn'], 'sans': action['sans']}, headers={'Content-Type': 'application/json', 'X-Client-Secret': config['ACME_API_SECRET']})
	if r is None:
		raise Exception('Request to ACME Create Certificate Endpoint failed')
	if r.status_code != 200:
		raise Exception('Request to ACME Create Certificate Endpoint failed with error code ' + str(r.status_code) + ': ' + r.text)

	# Extract the details
	js = r.json()
	cert = js['certificate_text']
	private_key = js['privatekey_text']
	cert_cn = js['cn'][0]
	cert_sans = js['sans']

	# Remove the aliases from the host object
	helper.lib.infoblox_remove_host_record_alias(ref[0], action['fqdn'])
	helper.lib.infoblox_remove_host_record_alias(ref[0], action['sans'])

	# Add the cert and key in to the task globals as it's needed elsewhere
	task_globals['le_cert'] = cert
	task_globals['le_key'] = private_key

	helper.end_event(description='Generated Let\'s Encrypt certificate, CN: ' + str(cert_cn) + ', SANs: ' + str(cert_sans))

	return True, task_globals

################################################################################

def action_allocate_ip(action, helper, config, task_globals):
	# Allocate an IP address
	ipv4addr = helper.lib.infoblox_create_host(action['fqdn'], action['network'], action['aliases'])

	# Handle errors - this will stop the task
	if ipv4addr is None:
		raise Exception('Failed to allocate an IP address')

	# End the event, logging what we allocated
	helper.end_event(description="Allocated the IP address " + ipv4addr)

	# Add the IP address to the task globals as it's needed elsewhere
	task_globals['allocated_ip'] = ipv4addr

	return True, task_globals

################################################################################

def action_create_node(action, helper, config, task_globals):
	# Connect
	bigip = connect_bigip(action['bigip'], config)

	# Create the node
	try:
		bigip.tm.ltm.nodes.node.create(name=action['name'], address=action['ip'], description=action['description'], partition=action['partition'])
	except Exception as e:
		raise Exception('Failed to create node: ' + str(e))

	return True, task_globals

################################################################################

def action_create_monitor(action, helper, config, task_globals):
	# Connect
	bigip = connect_bigip(action['bigip'], config)

	# Create the monitor
	try:
		if action['parent'] == 'http':
			bigip.tm.ltm.monitor.https.http.create(name=action['name'], partition=action['partition'], description=action['description'], send='GET ' + action['url'] + ' HTTP/1.1\r\nHost: ' + action['fqdn'] + '\r\n\r\n', recv=action['response'])
		elif action['parent'] == 'https':
			bigip.tm.ltm.monitor.https_s.https.create(name=action['name'], partition=action['partition'], description=action['description'], send = 'GET ' + action['url'] + ' HTTP/1.1\r\nHost: ' + action['fqdn'] + '\r\n\r\n', recv=action['response'])
		else:
			raise Exception('Unknown monitor parent: ' + str(action['parent']))
	except Exception as e:
		raise Exception('Failed to create monitor: ' + str(e))

	return True, task_globals

################################################################################

def action_create_pool(action, helper, config, task_globals):
	# Connect
	bigip = connect_bigip(action['bigip'], config)

	# Create the pool
	try:
		bigip.tm.ltm.pools.pool.create(name=action['name'], partition=action['partition'], description=action['description'], monitor=action['monitor'], members=action['members'])
	except Exception as e:
		raise Exception('Failed to create pool: ' + str(e))

	return True, task_globals

################################################################################

def action_upload_key(action, helper, config, task_globals):
	# Connect
	bigip = connect_bigip(action['bigip'], config)

	# Upload the key
	try:
		if 'from_letsencrypt' in action and action['from_letsencrypt'] is True:
			key_text = task_globals['le_key']
		else:
			key_text = action['content']

		bigip.shared.file_transfer.uploads.upload_bytes(key_text, action['filename'])
	except Exception as e:
		raise Exception('Failed to upload key: ' + str(e))

	# Create the key
	try:
		param_set = {'name': action['filename'], 'partition': action['partition'], 'from-local-file': '/var/config/rest/downloads/' + action['filename']}
		bigip.tm.sys.crypto.keys.exec_cmd('install', **param_set)
	except Exception as e:
		raise Exception('Failed to create key: ' + str(e))

	return True, task_globals

################################################################################

def action_upload_cert(action, helper, config, task_globals):
	# Connect
	bigip = connect_bigip(action['bigip'], config)

	# Upload the certificate
	try:
		if 'from_letsencrypt' in action and action['from_letsencrypt'] is True:
			cert_text = task_globals['le_cert']
		else:
			cert_text = action['content']

		bigip.shared.file_transfer.uploads.upload_bytes(cert_text, action['filename'])
	except Exception as e:
		raise Exception('Failed to upload certificate: ' + str(e))

	# Create the certificate
	try:
		param_set = {'name': action['filename'], 'partition': action['partition'], 'from-local-file': '/var/config/rest/downloads/' + action['filename']}
		bigip.tm.sys.crypto.certs.exec_cmd('install', **param_set)
	except Exception as e:
		raise Exception('Failed to create certificate: ' + str(e))

	return True, task_globals

################################################################################

def action_create_ssl_client_profile(action, helper, config, task_globals):
	# Connect
	bigip = connect_bigip(action['bigip'], config)

	# Create the SSL Client Profile
	try:
		bigip.tm.ltm.profile.client_ssls.client_ssl.create(name=action['name'], partition=action['partition'], key='/' + action['partition'] + '/' + action['key'], cert='/' + action['partition'] + '/' + action['cert'], chain=action['chain'], defaultsFrom=action['parent'])
	except Exception as e:
		raise Exception('Failed to create SSL Client Profile: ' + str(e))

	return True, task_globals

################################################################################

def action_create_http_profile(action, helper, config, task_globals):
	# Connect
	bigip = connect_bigip(action['bigip'], config)

	# Create the HTTP Profile
	try:
		# We pass in these kwargs slightly differently, just because the
		# parameters we need vary depending on what we're doing
		kwargs = {
			'name': action['name'],
			'partition': action['partition'],
			'defaultsFrom': action['parent'],
		}

		if 'hsts' in action and action['hsts'] is True:
			kwargs['hsts'] = {
				'mode': 'enabled',
				'maximumAge': config['HSTS_MAX_AGE']
			}
			if config['HSTS_INCLUDE_SUBDOMAINS'] is True:
				kwargs['hsts']['includeSubdomains'] = 'enabled'
			else:
				kwargs['hsts']['includeSubdomains'] = 'disabled'
		
		if 'outage_page' in action:
			kwargs['fallbackHost'] = action['outage_page']

		bigip.tm.ltm.profile.https.http.create(**kwargs)
	except Exception as e:
		raise Exception('Failed to create HTTP Profile: ' + str(e))

	return True, task_globals

################################################################################

def action_create_virtual_server(action, helper, config, task_globals):
	# Connect
	bigip = connect_bigip(action['bigip'], config)

	if 'ip' not in action or action['ip'] is None or len(action['ip']) == 0:
		ip = task_globals['allocated_ip']
	else:
		ip = action['ip']

	# Create the virtual server
	try: 
		# We pass in these kwargs slightly differently, just because the
		# parameters we need vary depending on what we're doing
		kwargs = {
			'name': action['name'],
			'partition': action['partition'],
			'description': action['description'],
			'destination': "%s:%s" % (ip, action['port']),
			'mask': '255.255.255.255',
			'ipProtocol': 'tcp',
			'rules': action['irules'],
			'profiles': [
				{
					'kind': 'ltm:virtual:profile',
					'name': 'tcp'
				}
			]
		}

		# If we don't have a pool, then we're just a HTTP->HTTPS forwarded,
		# so we don't need to SNAT, but if we do, then we need to set SNAT
		# to AutoMap
		if 'pool' in action:
			kwargs['sourceAddressTranslation'] = {'type': 'automap'}

		# If we have a pool, then set up persistence
		if 'pool' in action:
			kwargs['persist'] = 'cookie'
			kwargs['fallbackPersistence'] = 'source_addr'

		if 'pool' in action:
			kwargs['pool'] = '/' + action['partition'] + '/' + action['pool']

		# Add on an all the other profiles as necessary
		for profile in ['ssl_client_profile', 'ssl_server_profile', 'http_profile']:
			if profile in action:
				kwargs['profiles'].append({
					'kind': 'ltm:virtual:profile',
					'name': action[profile]
				})

		bigip.tm.ltm.virtuals.virtual.create(**kwargs)
		pass
	except Exception as e:
		raise Exception('Failed to create virtual server: ' + str(e))

	return True, task_globals
