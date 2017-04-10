from cortex import app
from flask import g

import requests

from urlparse import urljoin
from urllib import quote

class Rubrik(object):
    """A restful client for Rubrik"""

    def __init__(self):
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

    def get_vm(self, name):
        """Detailed view of a VM
        param id ID of the virtual machine
        """
        try:
            #try to get the only vm in the response
            return self.get_request('vmware/vm', {'name': quote(name), 'limit':
            1})['data'][0]
        except KeyError:
            raise Exception('VM not found')

    def get_vm_snapshots(self, id):
        """Get a list of snapshots for the vm"""
        return self.get_request('vmware/vm/' + quote(id) + '/snapshot')

    def update_vm(self, id, data):
        """update a vm with a new set of properties"""
        return self.patch_request('vmware/vm/' + quote(id), data)
