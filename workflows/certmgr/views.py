import MySQLdb as mysql
from cortex import app
from cortex.lib.workflow import CortexWorkflow, raise_if_workflows_locked
import cortex.lib.core
import cortex.lib.systems
import cortex.views
from cortex.corpus import Corpus
from flask import Flask, request, session, redirect, url_for, flash, g, abort, render_template, jsonify, Response
import re, datetime, requests
from urllib.parse import urljoin
import json
# For downloading ZIP file
import zipfile
from io import BytesIO

# For NLB API
from f5.bigip import ManagementRoot

# For certificate validation
import OpenSSL as openssl

# For securely passing the actions list via the browser
from itsdangerous import JSONWebSignatureSerializer

workflow = CortexWorkflow(__name__, check_config={'PROVIDERS': list, 'DEFAULT_PROVIDER': str, 'ENVS': list, 'DEFAULT_ENV': str, 'KEY_SIZES': list, 'DEFAULT_KEY_SIZE': int, 'LENGTHS': list, 'DEFAULT_LENGTH': int, 'NLBS': list, 'ACME_SERVERS': list, 'ENTCA_SERVERS': list, 'NLB_INTERMEDIATE_CN_FILES': dict, 'NLB_INTERMEDIATE_CN_OCSP_STAPLING_PARAMS': dict, 'CLIENT_SSL_PROFILE_PREFIX': str, 'CLIENT_SSL_PROFILE_SUFFIX': str, 'CERT_SELF_SIGNED_C': str, 'CERT_SELF_SIGNED_ST': str, 'CERT_SELF_SIGNED_L': str, 'CERT_SELF_SIGNED_O': str, 'CERT_SELF_SIGNED_OU': str, 'ACME_DNS_VIEW': str, 'DNS_WAIT_TIME': int, 'CERT_CACHE_TIME': int, 'EXTERNAL_DNS_SERVER_IP': str})
workflow.add_permission('certmgr.create', 'Create SSL Certificate')

# FQDN regex
fqdn_re = re.compile(r"^([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}$")

def abort_on_missing_task():
	if 'task' not in request.args:
		abort(404)

	# Check that the task exists
	task = cortex.lib.core.task_get(request.args['task'])
	if task is None:
		abort(404)

	if task['module'] != 'certmgr':
		abort(400)

	return task

def get_certificate_from_redis(task):
	# Defaults
	pem_cert = None
	pem_key = None
	pem_chain = None
	prefix = 'certmgr/' + str(task['id']) + '/'

	if g.redis.exists(prefix + 'certificate') and g.redis.exists(prefix + 'private'):
		pem_cert = g.redis.get(prefix + 'certificate')
		pem_key = g.redis.get(prefix + 'private')
		if g.redis.exists(prefix + 'chain'):
			pem_chain = g.redis.get(prefix + 'chain')

	return (pem_cert, pem_key, pem_chain)

@workflow.route('download', title='Create SSL Certificate', permission="certmgr.create", methods=['GET'], menu=False)
def certmgr_download():
	# Check that the task exists
	task = abort_on_missing_task()

	return render_template(__name__ + "::download.html", title="Create SSL Certificate", task_id=int(task['id']))

@workflow.route('download/zip', title='Download SSL Certificate', permission='certmgr.create', methods=['GET'], menu=False)
def certmgr_download_zip():
	# Check that the task exists
	task = abort_on_missing_task()

	# Get the certificate
	(pem_cert, pem_key, pem_chain) = get_certificate_from_redis(task)
	if pem_cert is None:
		abort(404)

	# Open a Zip file in memory for writing
	zip_data = BytesIO()
	zip_file = zipfile.ZipFile(zip_data, 'w', zipfile.ZIP_DEFLATED)

	# Add in the certificate and private key
	zip_file.writestr('certificate.pem', pem_cert)
	zip_file.writestr('private_key.pem', pem_key)

	# Add in the chain if it exists
	if pem_chain is not None:
		zip_file.writestr('chain.pem', pem_chain)

	zip_file.close()

	return Response(zip_data.getvalue(), mimetype='application/zip', headers={'Content-Disposition': 'attachment; filename="' + str(task['id']) + '.zip"'})

@workflow.route('download/pkcs12', title='Download SSL Certificate', permission='certmgr.create', methods=['GET'], menu=False)
def certmgr_download_pkcs12():
	# Check that the task exists
	task = abort_on_missing_task()

	# Get the certificate
	(pem_cert, pem_key, pem_chain) = get_certificate_from_redis(task)
	if pem_cert is None:
		abort(404)

	# Load the OpenSSL objects 
	pkey = openssl.crypto.load_privatekey(openssl.crypto.FILETYPE_PEM, pem_key)
	cert = openssl.crypto.load_certificate(openssl.crypto.FILETYPE_PEM, pem_cert)
	if pem_chain is not None:
		chain = openssl.crypto.load_certificate(openssl.crypto.FILETYPE_PEM, pem_chain)

	# Generate a PKCS12 object
	pkcs12 = openssl.crypto.PKCS12()
	pkcs12.set_certificate(cert)
	pkcs12.set_privatekey(pkey)
	if pem_chain is not None:
		pkcs12.set_ca_certificates([chain])

	return Response(pkcs12.export(), mimetype='application/x-pkcs12', headers={'Content-Disposition': 'attachment; filename="' + str(task['id']) + '.pfx"'})
	
@workflow.route('ajax_get_raw', title='Create SSL Certificate', permission="certmgr.create", methods=['GET'], menu=False)
def certmgr_ajax_get_raw():
	# Check that the task exists
	task = abort_on_missing_task()

	# Get the certificate
	(pem_cert, pem_key, pem_chain) = get_certificate_from_redis(task)
	if pem_cert is None:
		return jsonify(error="Certificate is no longer in Cortex's cache. Regenerate the certificate or obtain it from the original source.")
	else:
		return jsonify(certificate=pem_cert, key=pem_key, chain=pem_chain)

@workflow.route('create', title='Create SSL Certificate', order=40, permission="certmgr.create", methods=['GET', 'POST'])
def certmgr_create():
	# Don't go any further if workflows are currently locked
	raise_if_workflows_locked()

	# Get the workflow settings
	wfconfig = workflow.config

	# Turn envs in to a dict
	envs_dict = { env['id']: env for env in wfconfig['ENVS'] }

	# Turn providers in to a dict
	providers_dict = { provider['id']: provider for provider in wfconfig['PROVIDERS'] }

	# Turn NLBs in to a dict
	nlbs_dict = { nlb['id']: nlb for nlb in wfconfig['NLBS'] }

	# Turn ACME servers in to a dict
	acme_dict = { acme['id']: acme for acme in wfconfig['ACME_SERVERS'] }

	# Turn ENTCA servers in to a dict
	entca_dict = { entca['id']: entca for entca in wfconfig['ENTCA_SERVERS'] }

	if request.method == 'GET':
		## Show form
		return render_template(__name__ + "::create.html", title="Create SSL Certificate", envs=wfconfig['ENVS'], envs_dict=envs_dict, default_env=wfconfig['DEFAULT_ENV'], providers=wfconfig['PROVIDERS'], providers_dict=providers_dict, default_provider=wfconfig['DEFAULT_PROVIDER'], key_sizes=wfconfig['KEY_SIZES'], default_key_size=wfconfig['DEFAULT_KEY_SIZE'], cert_lengths=wfconfig['LENGTHS'], default_cert_length=wfconfig['DEFAULT_LENGTH'], nlbs=wfconfig['NLBS'], nlbs_dict=nlbs_dict, acme_servers=wfconfig['ACME_SERVERS'], acme_dict=acme_dict, entca_servers=wfconfig['ENTCA_SERVERS'], entca_dict=entca_dict)

	elif request.method == 'POST':
		valid_form = True
		form_fields = {}

		# Get parameters from form, stripped with defaults
		for field in ['provider', 'env', 'hostname', 'domain', 'aliases', 'key_size', 'length']:
			form_fields[field] = request.form.get(field, '').strip()

		# Get parameters from form - checkboxes
		form_fields['create_ssl_profile'] = 'create_ssl_profile' in request.form

		if len(form_fields['provider']) == 0:
			flash('You must specify an SSL provider', 'alert-danger')
			valid_form = False
		if len(form_fields['env']) == 0:
			flash('You must specify an environment', 'alert-danger')
			valid_form = False
		if len(form_fields['hostname']) == 0:
			flash('You must enter a hostname part for the CN of the certificate', 'alert-danger')
			valid_form = False
		if len(form_fields['domain']) == 0:
			flash('You must enter a valid domain part for the CN of the certificate', 'alert-danger')
			valid_form = False

		if len(form_fields['hostname']) > 0 and len(form_fields['domain']) > 0:
			fqdn = form_fields['hostname'] + '.' + form_fields['domain']
			if fqdn_re.match(fqdn) is None:
				flash('The FQDN of the service must be a valid domain name', 'alert-danger')
				valid_form = False

		if providers_dict[form_fields['provider']]['selectable_key_size']:
			if len(form_fields['key_size']) == 0:
				flash('You must choose a key size', 'alert-danger')
				valid_form = False
			elif int(form_fields['key_size']) not in wfconfig['KEY_SIZES']:
				flash('You must select a valid key size', 'alert-danger')
				valid_form = False

		if providers_dict[form_fields['provider']]['selectable_expiration']:
			if len(form_fields['length']) == 0:
				flash('You must choose a validity length for the certificate', 'alert-danger')
				valid_form = False
			elif int(form_fields['length']) not in wfconfig['LENGTHS']:
				flash('You must select a valid validity length for the certificate', 'alert-danger')
				valid_form = False

		if len(form_fields['aliases']) > 0:
			split_aliases = [x for x in form_fields['aliases'].split(' ') if x != '']
			for alias in split_aliases:
				if '.' not in alias:
					flash('All SANs must be fully qualified domain names', 'alert-danger')
					valid_form = False
					break
				elif fqdn_re.match(alias) is None:
					flash('All service alises must be valid domain names: ' + alias, 'alert-danger')
					valid_form = False
					break
		else:
			split_aliases = []

		# If we've got some errors, go back to the form
		if not valid_form:
			return render_template(__name__ + "::create.html", title="Create SSL Certificate", envs=wfconfig['ENVS'], envs_dict=envs_dict, default_env=wfconfig['DEFAULT_ENV'], providers=wfconfig['PROVIDERS'], providers_dict=providers_dict, default_provider=wfconfig['DEFAULT_PROVIDER'], key_sizes=wfconfig['KEY_SIZES'], default_key_size=wfconfig['DEFAULT_KEY_SIZE'], cert_lengths=wfconfig['LENGTHS'], default_cert_length=wfconfig['DEFAULT_LENGTH'], nlbs=wfconfig['NLBS'], nlbs_dict=nlbs_dict, acme_servers=wfconfig['ACME_SERVERS'], acme_dict=acme_dict, values=form_fields, entca_servers=wfconfig['ENTCA_SERVERS'], entca_dict=entca_dict)

		# Build the options
		options = {}
		options['wfconfig'] = wfconfig
		options['fqdn'] = fqdn
		options['aliases'] = split_aliases
		options['provider'] = providers_dict[form_fields['provider']]
		options['env'] = form_fields['env']
		options['create_ssl_profile'] = form_fields['create_ssl_profile']
		options['nlb'] = nlbs_dict[envs_dict[form_fields['env']]['nlb']]
		options['acme'] = acme_dict[envs_dict[form_fields['env']]['acme']]
		options['entca'] = entca_dict[envs_dict[form_fields['env']]['entca']]
		options['key_size'] = int(form_fields['key_size'])
		options['length'] = int(form_fields['length'])

		# Everything is fine. Start the task
		neocortex = cortex.lib.core.neocortex_connect()
		task_id = neocortex.create_task(__name__, session['username'], options, description="Creates an SSL certificate")

		# Redirect to the download page
		return redirect(url_for('certmgr_download', task=task_id))
