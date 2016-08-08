import requests
import json

class CorpusInfoblox:
	
	def __init__(self, config):
		self.config = config

	def get_host_refs(self,fqdn):
		"""Returns a list of host references (Infoblox record IDs) from Infoblox
		matching exactly the specified fully qualified domain name (FQDN). If no
		records are found None is returned. If an error occurs LookupError is raised"""

		payload = {'name:': fqdn}
		r = requests.get("https://" + self.config['INFOBLOX_HOST'] + "/wapi/v2.0/record:host", data=json.dumps(payload), auth=(self.config['INFOBLOX_USER'], self.config['INFOBLOX_PASS']))

		results = []

		if r.status_code == 200:
			response = r.json()

			if isinstance(response, list):
				if len(response) == 0:
					return None
				else:
					for record in response:
						if '_ref' in record:
							results.append(record['_ref'])
				
				return results
			else:
				raise LookupError("Invalid data returned from Infoblox API. Code " + str(r.status_code) + ": " + r.text)			
		else:
			raise LookupError("Error returned from Infoblox API. Code " + str(r.status_code) + ": " + r.text)
