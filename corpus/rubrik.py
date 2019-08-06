from flask import g

import requests

from urllib.parse import urljoin
from urllib.parse import quote

class Rubrik(object):
	"""A restful client for Rubrik"""

	def __init__(self, helper):
		app = helper
		self.api_url_base = app.config['RUBRIK_API_URL_BASE']
		self.headers = {'Accept': 'application/json'}
		self.rubrik_api_user = app.config['RUBRIK_API_USER']
		self.rubrik_api_pass = app.config['RUBRIK_API_PASS']
		self.get_api_token()

	def get_api_token(self):
		url = urljoin(self.api_url_base, 'session')
		try:
			r = requests.post(url, headers={'Accept': 'application/json'},
								auth=(self.rubrik_api_user, self.rubrik_api_pass),
								verify=False)
			r.raise_for_status()
			self.headers['Authorization'] = 'Bearer ' + r.json().get('token')
		except requests.exceptions.HTTPError as e:
			raise

	def get_request(self, api_call, payload=None):
		url = urljoin(self.api_url_base, api_call)
		try:
			r = requests.get(url, headers=self.headers,
					params=payload, verify=False)
			r.raise_for_status()
			return r.json()
		except requests.exceptions.HTTPError as e:
			raise
		except ValueError as e:
			#json decode fail
			raise

	def patch_request(self, api_call, payload={}):
		url = urljoin(self.api_url_base, api_call)
		try:
			r = requests.patch(url, headers=self.headers,
								json=payload, verify=False)
			r.raise_for_status()
			return r.json()
		except requests.exceptions.HTTPError as e:
			raise
		except ValueError as e:
			#json decode fail
			raise

	def get_sla_domains(self):
		"""Gets the backup SLA categories from Rubrik"""
		return self.get_request('sla_domain')

	def get_vcenter_managed_id(self, vcenter_hostname):
		"""Gets the Managed ID of the vCenter object in Rubrik for a given vCenter hostname."""

		# Get all the vCenter information from Rubrik
		vcenters = self.get_request('vmware/vcenter')

		# For case insensitive comparison
		vcenter_hostname = vcenter_hostname.lower()

		# Iterate over the vCenters
		vcManagedId = None
		for vc in vcenters['data']:
			# If this is the right vCenter
			if vc['hostname'].lower() == vcenter_hostname:
				vcManagedId = vc['id']
				break

		if vcManagedId is None:
			raise RuntimeError('Failed to find vCenter "' + vcenter + '" in Rubrik')

		return vcManagedId

	def get_vm_managed_id(self, system):
		"""Works out the Rubrik Managed ID of a VM"""

		# Format of Rurrik Managed ID is:
		# VirtualMachine:::<vcenter-rubrik-managed-id>-<vm-moId>

		if 'vmware_vcenter' not in system or 'vmware_moid' not in system:
			raise KeyError('Missing vCenter or moId information from system')

		if system['vmware_vcenter'] is None or system['vmware_moid'] is None:
			raise RuntimeError('No vCenter or moId information available')

		# Get the vCenter managed ID
		vcManagedId = self.get_vcenter_managed_id(system['vmware_vcenter'])

		# Remove the leading "vCenter:::" text
		vcManagedId = vcManagedId[10:]

		return "VirtualMachine:::" + vcManagedId + "-" + system['vmware_moid']

	def get_vm(self, system):
		"""Detailed view of a VM
		param system The details of the system as a dict-like object (i.e. row from systems_info_view)
		"""
		try:
			vm_id = self.get_vm_managed_id(system)
		except Exception as e:
			import traceback
			app.logger.error('Error getting Rubrik VM ID:\n' + traceback.format_exc())
			raise Exception('Error getting Rubrik VM ID: ' + str(e))

		try:
			return self.get_request('vmware/vm/' + quote(vm_id))
		except Exception as e:
			import traceback
			app.logger.error('Error getting Rubrik VM ID:\n' + traceback.format_exc())
			raise Exception('Error getting VM from Rubrik: ' + str(e))

	def get_vm_snapshots(self, id):
		"""Get a list of snapshots for the vm"""
		return self.get_request('vmware/vm/' + quote(id) + '/snapshot')

	def update_vm(self, id, data):
		"""update a vm with a new set of properties"""
		return self.patch_request('vmware/vm/' + quote(id), data)
