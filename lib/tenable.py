"""
Helper functions for the Cortex Tenable.io / Nessus Integration
"""
import re
from urllib.parse import urljoin, urlparse

import requests
import requests.exceptions
import werkzeug.exceptions
from flask import current_app, g


class TenableIOHttpError(requests.exceptions.HTTPError):
	"""An HTTP error occured with Tenable.io"""
	pass

class TenableIOEndpointWhitelistError(werkzeug.exceptions.Forbidden):
	"""The requested API endpoint is not whitelisted"""
	pass

class TenableIOInvalidConfiguration(Exception):
	"""Invalid Configuration"""
	pass

class TenableIOApi:
	"""Tenable API Helper"""

	_REQUIRED_CONFIG = ["TENABLE_IO_URL", "TENABLE_IO_ACCESS_KEY", "TENABLE_IO_SECRET_KEY"]
	_API_ENDPOINT_WHITELIST = [
		"scanners\/1\/agents",
		"assets",
		"workbenches\/assets\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\/info",
		"workbenches\/assets\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\/vulnerabilities"
	]
	_API_ENDPOINT_REGEX = re.compile("^({})$".format("|".join(_API_ENDPOINT_WHITELIST)))

	def __init__(self, url, access_key, secret_key):

		self._base_url = "https://{base_url}/".format(base_url=self._extract_base_url(url))
		self._access_key = access_key
		self._secret_key = secret_key

	def _extract_base_url(self, url):
		"""Extract the base url from a url string e.g. for 'https://domain.tld'
		or 'domain.tld/path' this will always return 'domain.tld'"""
		return urlparse(url).netloc or urlparse(url).path.split("/", 1)[0]

	@property
	def _headers(self):
		"""Return a dictionary of HTTP headers to use for the API request"""
		return {
			"Accept": "application/json",
			"X-ApiKeys": "accessKey={access_key};secretKey={secret_key}".format(
				access_key = current_app.config["TENABLE_IO_ACCESS_KEY"],
				secret_key = current_app.config["TENABLE_IO_SECRET_KEY"]
			),
		}

	@staticmethod
	def validate_config(app_config):
		"""Ensure the Tenable.io config is present"""
		if not app_config:
			raise TenableIOInvalidConfiguration("Invalid Configuration: Application configuration is empty or None")
		for k in TenableIOApi._REQUIRED_CONFIG:
			if k not in app_config:
				raise TenableIOInvalidConfiguration("Invalid Configuration: Missing required configuration key '{k}' for Tenable.io".format(k=k))

		return True

	def api(self, path, method="GET", params=None, data=None):
		"""Send an API request to the tenable API"""

		if not self._API_ENDPOINT_REGEX.match(path):
			raise TenableIOEndpointWhitelistError("The path '{path}' is not in the API Endpoints whitelist")

		r = requests.request(
			method = method,
			url = urljoin(self._base_url, path),
			params = params or None,
			data = data or None,
			headers = self._headers
		)

		try:
			r.raise_for_status()
		except requests.exceptions.HTTPError as ex:
			raise TenableIOHttpError(ex) from ex

		return r.json()

def tio_connect():
	"""Return an instance of the TenableIOApi object"""

	tio = getattr(g, "tio", None)
	if tio is None and TenableIOApi.validate_config(current_app.config):
		tio = TenableIOApi(
			url = current_app.config["TENABLE_IO_URL"],
			access_key = current_app.config["TENABLE_IO_ACCESS_KEY"],
			secret_key = current_app.config["TENABLE_IO_ACCESS_KEY"],
		)
	return tio
