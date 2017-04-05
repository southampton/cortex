from cortex import app
from flask import g

import requests

from urlparse import urljoin

class Rubrik(object):
    """A restful client for Rubrik"""

    def __init__(self):
        self.api_url_base = app.config['RUBRIK_API_URL_BASE']
        self.headers = {'Accept': 'application/json'}
        self.rubrik_api_user = app.config['RUBRIK_API_USER']
        self.rubrik_api_pass = app.config['RUBRIK_API_PASS']

    def get_request(self, api_call, payload=None):
        url = urljoin(self.api_url_base, api_call)
        try:
            r = requests.get(url, headers=self.headers,
                    auth=(self.rubrik_api_user, self.rubrik_api_pass),
                    params=payload, verify=False)
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
            return self.get_request('vmware/vm', {'name': name, 'limit':
            1})['data'][0]
        except KeyError:
            raise Exception('VM not found')
