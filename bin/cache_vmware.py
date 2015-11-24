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

	## Get cursor to the database
	curd = helper.curd

	helper.event("delete_cache", "Deleting existing cache")

	## Delete existing data from database
	curd.execute("START TRANSACTION")
	curd.execute("DELETE FROM `vmware_cache_clusters`")
	curd.execute("DELETE FROM `vmware_cache_datacenters`")
	curd.execute("DELETE FROM `vmware_cache_vm`")

	helper.end_event(description="Deleted existing cache")

	## For each vCenter that appears in the configuration
	for key in helper.config['VMWARE'].keys():
		# Get the hostname
		instance = helper.config['VMWARE'][key]

		helper.event("vmware_connect", "Connecting to vmware instance " + instance['hostname'])
		si = SmartConnect(host=instance['hostname'], user=instance['user'], pwd=instance['pass'], port=instance['port'])
		content = si.RetrieveContent()
		helper.end_event(description="Connected to instance " + instance['hostname'])

		vm_properties = ["name", "config.uuid", "config.hardware.numCPU",
		                 "config.hardware.memoryMB", "guest.guestState",
		                 "config.guestFullName", "config.guestId",
		                 "config.version", "guest.hostName", "guest.ipAddress", 
		                 "config.annotation", "resourcePool", "guest.toolsRunningStatus", "guest.toolsVersionStatus2"]


		## List VMs ##########
		helper.event("vmware_cache_vm", "Caching virtual machine information from " + instance['hostname'])

		# Get the root of the VMware containers, and search for virtual machines
		root_folder = si.content.rootFolder
		view = helper.lib.vmware_get_container_view(si, obj_type=[vim.VirtualMachine])

		# Collect a subset of data on all VMs
		vm_data = helper.lib.vmware_collect_properties(si, view_ref=view,
		                                  obj_type=vim.VirtualMachine,
		                                  path_set=vm_properties,
		                                  include_mors=True)

		# For each VM
		for vm in vm_data:
			# Put in blank strings for data we don't have
			if 'config.annotation' not in vm:
				vm['config.annotation'] = ''

			if 'guest.hostName' not in vm:
				vm['guest.hostName'] = ''

			if 'guest.ipAddress' not in vm:
				vm['guest.ipAddress'] = ''

			# Put in the resource pool name rather than a Managed Object
			if 'resourcePool' in vm:
				vm['cluster'] = vm['resourcePool'].owner.name
			else:
				vm['cluster'] = "None"

			# Put the VM in the database
			curd.execute("INSERT INTO `vmware_cache_vm` (`id`, `vcenter`, `name`, `uuid`, `numCPU`, `memoryMB`, `guestState`, `guestFullName`, `guestId`, `hwVersion`, `hostname`, `ipaddr`, `annotation`, `cluster`, `toolsRunningStatus`, `toolsVersionStatus`) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", (vm['obj']._moId, instance['hostname'], vm['name'], vm['config.uuid'], vm['config.hardware.numCPU'], vm['config.hardware.memoryMB'], vm['guest.guestState'], vm['config.guestFullName'], vm['config.guestId'], vm['config.version'], vm['guest.hostName'], vm['guest.ipAddress'], vm['config.annotation'], vm['cluster'], vm['guest.toolsRunningStatus'], vm['guest.toolsVersionStatus2']))			

		helper.end_event(description="Cached virtual machine information for " + instance['hostname'])

		## List data centers ##########
		helper.event("vmware_cache_dc", "Caching datacenter information from " + instance['hostname'])
		print "Caching DCs"
		dcs = helper.lib.vmware_get_objects(content, [vim.Datacenter])

		# For each Data Center, put it in the database
		for dc in dcs:
			curd.execute("INSERT INTO `vmware_cache_datacenters` (`id`, `name`, `vcenter`) VALUES (%s, %s, %s)", (dc._moId, dc.name, instance['hostname']))

		helper.end_event(description="Cached datacenter information for " + instance['hostname'])

		## List clusters ##########
		helper.event("vmware_cache_dc", "Caching cluster information from " + instance['hostname'])
		print "Caching Clusters"
		clusters = helper.lib.vmware_get_objects(content, [vim.ClusterComputeResource])

		# For each cluster
		for cluster in clusters:
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

		helper.end_event(description="Cached cluster information from " + instance['hostname'])

	# Commit all the changes to the database
	helper.event("vmware_cache_dc", "Saving cache to disk")
	helper.db.commit()
	helper.end_event(description="Saved cache to disk")
