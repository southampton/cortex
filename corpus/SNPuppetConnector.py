#!/usr/bin/python
import json
import pypuppetdb
import requests
from requests.exceptions import HTTPError
import syslog

class SNPuppetConnector:

	# Table Definitions
	LINUX_SERVER_TABLE = "cmdb_ci_linux_server"
	DISKS_TABLE = "cmdb_ci_disk"
	FILESYSTEMS_TABLE = "cmdb_ci_file_system"
	NETWORK_ADAPTER_TABLE = "cmdb_ci_network_adapter"

	def __init__(self, 
		sn_host, sn_version, sn_user, sn_pass,
		puppet_host, puppet_port, puppet_ssl_cert, puppet_ssl_key, puppet_ssl_verify
	):
		# Create the ServiceNowAPI / PuppetDB Objects.
		self.sn = ServiceNowAPI(sn_host, sn_version, sn_user, sn_pass)
		self.puppet = PuppetDB(puppet_host, puppet_port, puppet_ssl_cert, puppet_ssl_key, puppet_ssl_verify)

	def message(self, message, category=None):
		"""
		Called when we want to display a message.
		"""
		syslog.syslog(message)

	def get_nodes_from_puppet(self):
		"""
		Return all the node objects from puppet.
		"""
		return	self.puppet.nodes()

	def get_node_from_puppet(self, node_name):
		"""
		Return the node object with the given node name.
		"""
		return self.puppet.node(node_name)
	
	def push_facts(self, node, cmdb_id, **kwargs):
		"""
		Push facts from Puppet to ServiceNow
		Args:
			cmbd_id - ServiceNow Sys ID
		"""

		self.push_server_facts(node, cmdb_id, **kwargs)
		self.push_networking_facts(node, cmdb_id, **kwargs)
		self.push_disk_facts(node, cmdb_id, **kwargs)
		self.push_mountpoint_facts(node, cmdb_id, **kwargs)

	def push_server_facts(self, node, node_sys_id, **kwargs):
		"""
		Push server facts from Puppet to ServiceNow.
		"""
		facts = self.puppet.get_all_facts(node)
		try:
			sn_server_data = {}
			sn_server_data["serial_number"] = facts["serialnumber"]
			sn_server_data["os_domain"] = facts["networking"]["domain"]
			sn_server_data["dns_domain"] = facts["networking"]["domain"]
			sn_server_data["ip_address"] = facts["ipaddress"]
			sn_server_data["cpu_count"] = facts["processors"]["physicalcount"]
			sn_server_data["cpu_core_count"] = int(facts["processors"]["count"]) / int(facts["processors"]["physicalcount"])

			# Sum the disks
			total_disk_space = 0
			for disk_name, disk_data in facts["disks"].iteritems():
				if not (disk_name[:2] == "fd" or disk_name[:2] == "sr"):
					total_disk_space += int(disk_data["size_bytes"])

			# Convert to GB
			sn_server_data["disk_space"] = "%.2f"%(float(total_disk_space)/1024**3)

			# See if VMWare RAM was passed.
			ram = kwargs.get('vmware_ram', None)
			if ram is not None:
				sn_server_data["ram"] = ram

			try:
				response = self.sn.put(self.LINUX_SERVER_TABLE, node_sys_id, data=sn_server_data)
			except HTTPError as e:
				self.message("Could not update %s. Error: %s" %(node.name, str(e)), "error")
				raise

		except KeyError as e:
			self.message("Error adding server data. Error: %s" %(str(e)), "error")
			raise

	def push_networking_facts(self, node, node_sys_id, **kwargs):
		"""
		Push networking facts from Puppet to ServiceNow
		"""
		# Get the network facts from Puppet.
		network_facts = self.puppet.get_network_facts(node) 
		
		try:
			for interface_name, interface_data in network_facts["interfaces"].iteritems():
				# Build the data dictionary to send to SN.
				sn_interface_data = {}
				sn_interface_data["name"] = interface_name
				sn_interface_data["install_status"] = "1"
				sn_interface_data["cmdb_ci"] = node_sys_id
				if "mac" in interface_data:
					sn_interface_data["mac_address"] = interface_data["mac"]
				if "ip" in interface_data:
					sn_interface_data["ip_address"] = interface_data["ip"]
				if "netmask" in interface_data:
					sn_interface_data["netmask"] = interface_data["netmask"]
				
				try:
					adapter_response = self.sn.get_table(
						self.NETWORK_ADAPTER_TABLE,
						sysparm_query='cmdb_ci=%s^name=%s'%(node_sys_id, interface_name),
					)
				except HTTPError as e:
					if e.response.status_code == 404:
						# POST request needed as this nic doesn't exist yet.
						try:
							response = self.sn.post(self.NETWORK_ADAPTER_TABLE, data=sn_interface_data)
						except HTTPError as e:
							self.message("Could not add interface %s. Error: %s" %(interface_name, str(e)), "error")
							raise
					else:
						# HTTP Error.
						self.message("Could not add interface %s. Error: %s" %(interface_name, str(e)), "error")
						raise
				else:
					# PUT request needed.
					try:
						adapter_id = adapter_response["result"][0]["sys_id"]
						response = self.sn.put(self.NETWORK_ADAPTER_TABLE, adapter_id, data=sn_interface_data)
					except HTTPError as e:
						self.message("Could not update interface %s. Error: %s" %(interface_name, str(e)), "error")
						raise

		except KeyError as e:
			self.message("Error adding network interfaces. Error: %s" %(str(e)), "error")
			raise

	def push_disk_facts(self, node, node_sys_id, **kwargs):
		"""
		Push disk facts from Puppet to ServiceNow
		"""
		# Get disk facts from Puppet
		disk_facts = self.puppet.get_disk_facts(node)

		try:
			for disk_name, disk_data in disk_facts.iteritems():
				sn_disk_data = {}
				sn_disk_data["computer"] = node_sys_id
				sn_disk_data["name"] = disk_name
				sn_disk_data["short_description"] = "Disk drive"
				sn_disk_data["size"] = disk_data["size"]
				sn_disk_data["size_bytes"] = disk_data["size_bytes"]
				sn_disk_data["install_status"] = "1"
				sn_disk_data["disk_space"] = "%.2f"%(float(disk_data["size_bytes"])/1024**3)
				try:
					disk_response = self.sn.get_table(self.DISKS_TABLE, sysparm_query='computer=%s^name=%s'%(node_sys_id, disk_name))
				except HTTPError as e:
					if e.response.status_code == 404:
						# POST request needed as this nic doesn't exist yet.
						try:
							response = self.sn.post(self.DISKS_TABLE, data=sn_disk_data)
						except HTTPError as e:
							self.message("Could not add disk %s. Error: %s" %(disk_name, str(e)), "error")
							raise
					else:
						# HTTP Error.
						self.message("Could not add disk %s. Error: %s" %(disk_name, str(e)), "error")
						raise

				else:
					# PUT request needed.
					try:
						disk_id = disk_response["result"][0]["sys_id"]
						response = self.sn.put(self.DISKS_TABLE, disk_id, data=sn_disk_data)
					except HTTPError as e:
						self.message("Could not update disk %s. Error: %s" %(disk_name, str(e)), "error")
						raise
		except KeyError:
			self.message("Error adding disks. Error: %s" %(str(e)), "error")
			raise

	def push_mountpoint_facts(self, node, node_sys_id, **kwargs):
		"""
		Push mountpoint facts from Puppet to ServiceNow
		"""
		# Get mountpoint facts from puppet.
		mountpoint_facts = self.puppet.get_mountpoint_facts(node)

		try:
			for mountpoint_name, mountpoint_data in mountpoint_facts.iteritems():
				sn_mountpoint_data = {}
				sn_mountpoint_data["computer"] = node_sys_id
				sn_mountpoint_data["name"] = mountpoint_name
				sn_mountpoint_data["mount_point"] = mountpoint_name
				sn_mountpoint_data["size"] = mountpoint_data["size"]
				sn_mountpoint_data["size_bytes"] = mountpoint_data["size_bytes"]
				sn_mountpoint_data["install_status"] = "1"
				sn_mountpoint_data["disk_space"] = "%.2f"%(float(mountpoint_data["size_bytes"])/1024**3)
				sn_mountpoint_data["free_space"] = mountpoint_data["available"]
				sn_mountpoint_data["free_space_bytes"] = mountpoint_data["available_bytes"]
				sn_mountpoint_data["file_system"] = mountpoint_data["filesystem"]
			
				try:
					mountpoint_response = self.sn.get_table(self.FILESYSTEMS_TABLE, sysparm_query='computer=%s^name=%s'%(node_sys_id, mountpoint_name))
				except HTTPError as e:
					if e.response.status_code == 404:
						# POST request needed as this nic doesn't exist yet.
						try:
							response = self.sn.post(self.FILESYSTEMS_TABLE, data=sn_mountpoint_data)
						except HTTPError as e:
							self.message("Could not add mountpoint %s. Error: %s" %(mountpoint_name, str(e)), "error")
							raise
					else:
						# HTTP Error.
						self.message("Could not add mountpoint %s. Error: %s" %(mountpoint_name, str(e)), "error")
						raise

				else:
					# PUT request needed.
					try:
						mountpoint_id = mountpoint_response["result"][0]["sys_id"]
						response = self.sn.put(self.FILESYSTEMS_TABLE, mountpoint_id, data=sn_mountpoint_data)
					except HTTPError as e:
						self.message("Could not update mountpoint %s. Error: %s" %(mountpoint_name, str(e)), "error")
						raise
		except KeyError:
			self.message("Error adding mountpoints. Error: %s" %(str(e)), "error")
			raise


class ServiceNowAPI():

	def __init__(self, host, version, username, password):
		self.host = host
		self.version = version
		self.username=username
		self.password = password

	def get_table(self, table, **kwargs):

		url = "https://" + self.host + "/api/now/" + self.version + "/table/" + table

		if kwargs:
			url = url + "?"
			# Add keyword arguments to the url.
			for key, value in kwargs.iteritems():
				url = url + str(key) + "=" + str(value) + "&"
			url = url.strip('&')

		response = requests.get(url, auth=(self.username, self.password), headers={"Accept":"application/json"})
		response.raise_for_status()

		return response.json()

	def get(self, table, sys_id):
		url = "https://" + self.host + "/api/now/" + self.version + "/table/" + table + "/" + sys_id
		headers = {"Content-Type":"application/json","Accept":"application/json"}
		response = requests.get(url, auth=(self.username, self.password), headers=headers)

		response.raise_for_status()

		return response.json()

	def put(self, table, sys_id, data):

		url = "https://" + self.host + "/api/now/" + self.version + "/table/" + table + "/" + sys_id
		headers = {"Content-Type":"application/json","Accept":"application/json"}
		response = requests.put(url, auth=(self.username, self.password), headers=headers, data=json.dumps(data))

		response.raise_for_status()

		return response.json()

	def post(self, table, data):

		url = "https://" + self.host + "/api/now/" + self.version + "/table/" + table
		headers = {"Content-Type":"application/json","Accept":"application/json"}
		response = requests.post(url, auth=(self.username, self.password), headers=headers, data=json.dumps(data))

		response.raise_for_status()

		return response.json()

class PuppetDB:

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

	def nodes(self):
		return self.db.nodes()

	def node(self, node_name):
		return self.db.node(node_name)

	def get_all_facts(self, node_object, cached=True):
		"""Get facts about this node from puppet."""
		if node_object.name in self.facts and cached:
			return self.facts[node_object.name]
		else:
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
