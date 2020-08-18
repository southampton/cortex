import pypuppetdb


class PuppetDBConnector:

	def __init__(self, host, port, ssl_cert, ssl_key, ssl_verify):
		self.host = host
		self.port = port
		self.ssl_cert = ssl_cert
		self.ssl_key = ssl_key
		self.ssl_verify = ssl_verify
		self.facts = {}

		# Connect
		self.connect()

	def connect(self):
		self.db = pypuppetdb.connect(self.host, port=self.port, ssl_cert=self.ssl_cert, ssl_key=self.ssl_key, ssl_verify=self.ssl_verify)

	def query(self, endpoint, **kwargs):
		# pylint: disable=protected-access
		return self.db._query(endpoint, **kwargs)

	def get_nodes(self, with_status=False):
		return self.db.nodes(with_status=with_status)

	def get_node(self, node_name):
		return self.db.node(node_name)

	def get_environments(self):
		return [i['name'] for i in self.db.environments()]

	def get_all_facts(self, node_object, cached=True):
		"""Get facts about this node from puppet."""
		if node_object.name in self.facts and cached:
			return self.facts[node_object.name]

		facts = node_object.facts()
		facts_dict = {}
		if facts is not None:
			for fact in facts:
				facts_dict[fact.name] = fact.value

			self.facts[node_object.name] = facts_dict

		return facts_dict

	def get_network_facts(self, node_object, cached=True):
		"""Get network facts from puppet."""
		facts = self.get_all_facts(node_object, cached)
		try:
			return facts["networking"]
		except KeyError:
			return {}

	def get_disk_facts(self, node_object, cached=True):
		"""Get disk facts from puppet."""
		facts = self.get_all_facts(node_object, cached)
		try:
			return facts["disks"]
		except KeyError:
			return {}

	def get_mountpoint_facts(self, node_object, cached=True):
		"""Get mountpoint facts from puppet."""
		facts = self.get_all_facts(node_object, cached)
		try:
			return facts["mountpoints"]
		except KeyError:
			return {}
