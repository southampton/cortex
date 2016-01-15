#!/usr/bin/python

import os
import MySQLdb as mysql
import sys
from pyVmomi import vim
from pyVmomi import vmodl
from pyVim.connect import SmartConnect, Disconnect

def run(helper, options):
	"""
	Clears the necessary database tables and re-imports the data 
	from VMware. Performed as a single transaction, so if any part 
	of the import fails, the old data is retained.
	"""

	## Get cursor to the database as a /seperate/ connection
	## so that the helper object can still make changes to mysql
	## whilst this big mysql transaction goes on
	tdb = helper.db_connect()
	curd = tdb.cursor(mysql.cursors.DictCursor)

	# Create dictionaries for VM data
	vm_data = {}
	dcs = {}
	clusters = {}

	## For each vCenter that appears in the configuration
	for key in helper.config['VMWARE'].keys():
		# Get the hostname
		instance = helper.config['VMWARE'][key]

		helper.event("vmware_connect", "Connecting to VMware instance " + instance['hostname'])
		si = SmartConnect(host=instance['hostname'], user=instance['user'], pwd=instance['pass'], port=instance['port'])
		content = si.RetrieveContent()
		helper.end_event(description="Connected to instance " + instance['hostname'])

		vm_properties = ["name", "config.uuid", "config.hardware.numCPU",
		                 "config.hardware.memoryMB", "runtime.powerState",
		                 "config.guestFullName", "config.guestId",
		                 "config.version", "guest.hostName", "guest.ipAddress", 
		                 "config.annotation", "resourcePool", "guest.toolsRunningStatus", 
				 "guest.toolsVersionStatus2", "config.template"]

		## List VMs ##########
		helper.event("vmware_cache_vm", "Downloading virtual machine information from " + instance['hostname'])

		# Get the root of the VMware containers, and search for virtual machines
		root_folder = si.content.rootFolder
		view = helper.lib.vmware_get_container_view(si, obj_type=[vim.VirtualMachine])

		# Collect a subset of data on all VMs
		vm_data_proxy = helper.lib.vmware_collect_properties(si, view_ref=view,
		                                  obj_type=vim.VirtualMachine,
		                                  path_set=vm_properties,
		                                  include_mors=True)

		# Start a vm_data section for this vCenter
		vm_data[key] = {}

		# Copy data from the proxy that pyVmomi returns to a non-proxied dictionary
		for vm in vm_data_proxy:
			# Get the managed object reference
			moId = vm['obj']._moId

			# Start a vm_data section for this vm
			vm_data[key][moId] = {}

			# Put in blank strings for data we don't have
			for attr in ['config.annotation', 'guest.hostName', 'guest.ipAddress']:
				if attr not in vm:
					vm[attr] = ''

			# Put in the resource pool name rather than a Managed Object
			if 'resourcePool' in vm:
				vm_data[key][moId]['cluster'] = vm['resourcePool'].owner.name
			else:
				vm_data[key][moId]['cluster'] = "None"

			# Store moId
			vm_data[key][moId]['_moId'] = moId

			# Store attributes for the VM
			for attr in ['name', 'config.uuid', 'config.hardware.numCPU', 'config.hardware.memoryMB', 'runtime.powerState', 'config.guestFullName', 'config.guestId', 'config.version', 'guest.hostName', 'guest.ipAddress', 'config.annotation', 'guest.toolsRunningStatus', 'guest.toolsVersionStatus2', 'config.template']:
				vm_data[key][moId][attr] = vm[attr]

		# Finish the event
		helper.end_event(description="Downloaded virtual machine information for " + instance['hostname'])
	
		## List DCs ##########
		helper.event("vmware_cache_dc", "Downloading datacenter information from " + instance['hostname'])
		dcs[key] = helper.lib.vmware_get_objects(content, [vim.Datacenter])
		helper.end_event(description="Downloaded datacenter information for " + instance['hostname'])

		## List clusters ##########
		helper.event("vmware_cache_dc", "Downloading cluster information from " + instance['hostname'])
		clusters[key] = helper.lib.vmware_get_objects(content, [vim.ClusterComputeResource])
		helper.end_event(description="Downloaded cluster information from " + instance['hostname'])

	# Note: We delete the cache from the database after downloading all the data, so 
	# as to not lock the table

	## Delete existing data from database
	helper.event("delete_cache", "Deleting existing cache")
	curd.execute("START TRANSACTION")
	curd.execute("DELETE FROM `vmware_cache_clusters`")
	curd.execute("DELETE FROM `vmware_cache_datacenters`")
	curd.execute("DELETE FROM `vmware_cache_vm`")
	helper.end_event(description="Deleted existing cache")

	## For each vCenter that appears in the configuration
	for key in helper.config['VMWARE'].keys():
		# Get the hostname
		instance = helper.config['VMWARE'][key]

		# Start the event
		helper.event("vmware_cache_data", "Caching downloaded data from " + instance['hostname'])

		# For each VM
		for moId in vm_data[key]:
			# Get the VM
			vm = vm_data[key][moId]

			# Put the VM in the database
			curd.execute("INSERT INTO `vmware_cache_vm` (`id`, `vcenter`, `name`, `uuid`, `numCPU`, `memoryMB`, `powerState`, `guestFullName`, `guestId`, `hwVersion`, `hostname`, `ipaddr`, `annotation`, `cluster`, `toolsRunningStatus`, `toolsVersionStatus`, `template`) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", (vm['_moId'], instance['hostname'], vm['name'], vm['config.uuid'], vm['config.hardware.numCPU'], vm['config.hardware.memoryMB'], vm['runtime.powerState'], vm['config.guestFullName'], vm['config.guestId'], vm['config.version'], vm['guest.hostName'], vm['guest.ipAddress'], vm['config.annotation'], vm['cluster'], vm['guest.toolsRunningStatus'], vm['guest.toolsVersionStatus2'], vm['config.template']))

		# For each Data Center, put it in the database
		for dc in dcs[key]:
			curd.execute("INSERT INTO `vmware_cache_datacenters` (`id`, `name`, `vcenter`) VALUES (%s, %s, %s)", (dc._moId, dc.name, instance['hostname']))

		# For each cluster
		for cluster in clusters[key]:
			## Recurse up to find the data center
			parent = cluster.parent
			found = False

			# Loop until we find something
			while not found:
				try:
					# If we've got a Datacenter object as the parent
					# then we've foudn what we're looking for
					if isinstance(parent, vim.Datacenter):
						clusterdc = parent._moId
						found = True
					else:
						# Recurse to parent
						parent = parent.parent
				except Exception as ex:
					clusterdc = "Unknown"
					break

			# Put the cluster in the database
			curd.execute("INSERT INTO `vmware_cache_clusters` (`id`, `name`, `vcenter`, `did`) VALUES (%s, %s, %s, %s)", (cluster._moId, cluster.name, instance['hostname'], clusterdc))

		helper.end_event(description="Cached information from " + instance['hostname'])

	# Commit all the changes to the database
	helper.event("vmware_cache_dc", "Saving cache to disk")
	tdb.commit()
	helper.end_event(description="Saved cache to disk")
