import requests

from urllib.parse import urljoin
from urllib.parse import quote

class RubrikVMNotFound(Exception):
	pass

class RubrikVCenterNotFound(Exception):
	def __init__(self, vcenter):
		self.vcenter = vcenter

class Rubrik(object):
	"""A RESTful client for Rubrik"""

	def __init__(self, helper):
		"""Initialise the client and create a bearer token"""

		self._helper = helper
		self._api_url_base = helper.config["RUBRIK_API_URL_BASE"]
		self._api_default_version = helper.config["RUBRIK_API_DEFAULT_VERSION"]
		self._verify = helper.config["RUBRIK_API_VERIFY_SERVER"]
		self._headers = {"Accept": "application/json"}
		self._auth = (helper.config["RUBRIK_API_USER"], helper.config["RUBRIK_API_PASS"])
		self._get_api_token()

	def _url(self, endpoint, version=None):
		"""Construct the URL for a given endpoint"""
		# If the version was not specified use the default
		if not version:
			version = self._api_default_version
		# Version must have a trailing slash
		if not version.endswith("/"):
			version = version + "/"
		# Endpoint shouldn"t have a leading slash
		if endpoint.startswith("/"):
			endpoint = endpoint[1:]

		return urljoin(urljoin(self._api_url_base, version), endpoint)

	def _get_api_token(self):
		"""Obtain a bearer token and insert it into the client"s headers"""
		try:
			r = requests.post(
				self._url("session"),
				headers=self._headers,
				auth=self._auth,
				verify=self._verify,
			)
			r.raise_for_status()
		except requests.exceptions.HTTPError:
			raise
		else:
			self._headers["Authorization"] = "Bearer " + r.json().get("token")

	def _request(self, method, endpoint, version, **kwargs):
		"""Make an API request to an endpoint"""

		# Remove the keys we will override
		for k in ("headers", "verify"):
			kwargs.pop(k, None)
		# Attempt to make a request
		try:
			r = requests.request(
				method,
				self._url(endpoint, version=version),
				headers=self._headers,
				verify=self._verify,
				**kwargs
			)
			r.raise_for_status()
			return r.json()
		# Non 2XX status code
		except requests.exceptions.HTTPError:
			raise
		# JSON decode failed
		except ValueError:
			raise

	def get_request(self, endpoint, version=None, payload=None):
		"""Make a GET request to an API endpoint"""
		return self._request("GET", endpoint, version, params=payload)

	def patch_request(self, endpoint, version=None, payload={}):
		"""Make a PATCH request to an API endpoint"""
		return self._request("PATCH", endpoint, version, json=payload)

	def get_sla_domains(self):
		"""Gets the backup SLA categories from Rubrik"""
		return self.get_request("sla_domain")

	def get_vcenter_managed_id(self, vcenter_hostname):
		"""Gets the Managed ID of the vCenter object in Rubrik for a given vCenter hostname."""

		# Get all the vCenter information from Rubrik
		vcenters = self.get_request("vmware/vcenter")

		# For case insensitive comparison
		vcenter_hostname = vcenter_hostname.lower()

		# Iterate over the vCenters
		vcManagedId = None
		for vc in vcenters["data"]:
			# If this is the right vCenter
			if vc["hostname"].lower() == vcenter_hostname:
				vcManagedId = vc["id"]
				break

		if vcManagedId is None:
			raise RubrikVCenterNotFound(vcenter_hostname)

		return vcManagedId

	def get_vm_managed_id(self, system):
		"""Works out the Rubrik Managed ID of a VM"""

		# Format of Rubrik Managed ID is:
		# VirtualMachine:::<vcenter-rubrik-managed-id>-<vm-moId>

		if "vmware_vcenter" not in system or "vmware_moid" not in system:
			raise KeyError("Missing vCenter or moId information from system")

		if system["vmware_vcenter"] is None or system["vmware_moid"] is None:
			raise RuntimeError("No vCenter or moId information available")

		# Get the vCenter managed ID
		vcManagedId = self.get_vcenter_managed_id(system["vmware_vcenter"])

		# Remove the leading "vCenter:::" text
		vcManagedId = vcManagedId[10:]

		return "VirtualMachine:::" + vcManagedId + "-" + system["vmware_moid"]

	def get_vm(self, system):
		"""Detailed view of a VM
		param system The details of the system as a dict-like object (i.e. row from systems_info_view)
		"""
		try:
			vm_id = self.get_vm_managed_id(system)
		# bubble up the RubrikVMNotFound and RubrikVCenterNotFound exceptions
		except (RubrikVMNotFound, RubrikVCenterNotFound) as ex:
			raise ex
		except Exception as ex:
			import traceback
			self._helper.logger.error("Error getting Rubrik VM ID:\n" + traceback.format_exc())
			raise Exception("Error getting Rubrik VM ID: " + str(ex))

		try:
			return self.get_request("vmware/vm/{id}".format(id = quote(vm_id)))
		except requests.exceptions.HTTPError as ex:
			if ex.response is not None and ex.response.status_code == 404:
				raise RubrikVMNotFound()
			else:
				import traceback
				self._helper.logger.error("Error getting Rubrik VM ID:\n" + traceback.format_exc())
				raise Exception("Error getting VM from Rubrik: " + str(ex))
		except Exception as ex:
			import traceback
			self._helper.logger.error("Error getting Rubrik VM ID:\n" + traceback.format_exc())
			raise Exception("Error getting VM from Rubrik: " + str(ex))

	def get_vm_snapshots(self, id, **kwargs):
		"""Get a list of snapshots for the vm"""
		return self.get_request("vmware/vm/{id}/snapshot".format(id = quote(id)))

	def update_vm(self, id, data):
		"""update a vm with a new set of properties"""
		return self.patch_request("vmware/vm/{id}".format(id = quote(id)), payload=data)
