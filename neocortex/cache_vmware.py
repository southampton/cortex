#!/usr/bin/python

import os
import MySQLdb as mysql
import sys
from pyVmomi import vim
from pyVmomi import vmodl
import time
import signal

def sigalrm_handler(signum, frame):
	"""
	Handles the SIGALRM signal, which we use to interrupt a read should it 
	take a long time. This prevents this task from never completing and 
	never getting killed.
	"""
	
	# Raise an exception, which should interrupt and terminate
	raise Exception("Timed out when communicating with vCenter")

def run(helper, options):
	"""
	Clears the necessary database tables and re-imports the data 
	from VMware. Performed as a single transaction, so if any part 
	of the import fails, the old data is retained.
	"""

	## Get a lock so that nobody will attempt to update the database cache
	## whilst we're running an update. We don't use MySQL locks because WRITE locks
	## prevent reads whilst we're running (!??!) and that would break cortex/neocortex
	## whilst we run this job which could take many minutes
	## The timeout is there in case this process dies or the server restarts or similar
	## and then the lock is never ever unlocked - the timeout ensures that eventually it is
	## and cortex might recover itself. maybe. the sleep is set to 1, up from the insane default of 0.1
	helper.event("vmware_cache_lock", "Obtaining VMware cache lock")
	with helper.lib.rdb.lock('lock/update_vmware_cache',timeout=1800,sleep=1):
		helper.end_event(description="Obtained VMware cache lock")

		## Get cursor to the database as a /seperate/ connection
		## so that the helper object can still make changes to mysql
		## whilst this big mysql transaction goes on
		tdb = helper.db_connect()
		curd = tdb.cursor(mysql.cursors.DictCursor)

		# Grab the timeout value from our configuration, or defaulting to
		# an hour if none exists
		if 'VMWARE_CACHE_UPDATE_TIMEOUT' in helper.config:
			timeout_alarm = int(helper.config['VMWARE_CACHE_UPDATE_TIMEOUT'])
		else:
			timeout_alarm = 3600

		# Set up the signal handler for SIGALRM to interrupt reads (as
		# PyVmomi doesn't appear to have a proper timeout on it's reads)
		signal.signal(signal.SIGALRM, sigalrm_handler)

		# Create a list for instances that were successful
		successful_instances = []

		# Create dictionaries for VM data
		vm_data = {}
		dcs = {}
		clusters = {}
		folders = {}

		skip_vms = False
		if options is not None and 'skip_vms' in options and options['skip_vms'] == True:
			skip_vms = True

		## For each vCenter that appears in the configuration
		for key in helper.config['VMWARE'].keys():
			# Get the hostname
			instance = helper.config['VMWARE'][key]

			helper.event("vmware_connect", "Connecting to VMware instance " + instance['hostname'])
			try:
				si = helper.lib.vmware_smartconnect(key)
				content = si.RetrieveContent()
			except Exception as e:
				helper.end_event(description="Failed to connect to instance " + instance['hostname'], success=False)
				continue
			else:
				helper.end_event(description="Connected to instance " + instance['hostname'])

				# Add the instance hostname to the successful instances.
				successful_instances.append(instance["hostname"])

				# If the task options don't say to skip VM information
				if not skip_vms:
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
					signal.alarm(timeout_alarm)
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

						# Ensure we have a config.uuid (it's kind of essential...)
						if 'config.uuid' not in vm:
							# If we don't, ignore this VM
							continue

						# Start a vm_data section for this vm
						vm_data[key][moId] = {}

						# Put in the resource pool name rather than a Managed Object
						if 'resourcePool' in vm:
							vm_data[key][moId]['cluster'] = vm['resourcePool'].owner.name
						else:
							vm_data[key][moId]['cluster'] = 'None'

						# Store moId
						vm_data[key][moId]['_moId'] = moId

						# Store attributes for the VM
						for attr in ['name', 'config.uuid', 'config.hardware.numCPU', 'config.hardware.memoryMB', 'runtime.powerState', 'config.guestFullName', 'config.guestId', 'config.version', 'guest.hostName', 'guest.ipAddress', 'config.annotation', 'guest.toolsRunningStatus', 'guest.toolsVersionStatus2', 'config.template']:
							if attr in vm:
								vm_data[key][moId][attr] = vm[attr]
							else:
								# Put in blank strings for data we don't have
								vm_data[key][moId][attr] = ''


					# Finish the event
					signal.alarm(0)
					helper.end_event(description="Downloaded virtual machine information for " + instance['hostname'])

				## List DCs ##########
				helper.event("vmware_cache_dc", "Downloading datacenter and folder information from " + instance['hostname'])
				signal.alarm(timeout_alarm)
				dcs[key] = helper.lib.vmware_get_objects(content, [vim.Datacenter])

				for datacenter in dcs[key]:
					folders[datacenter._moId] = []
					recurse_folder(datacenter.vmFolder,folders[datacenter._moId])

				signal.alarm(0)
				helper.end_event(description="Downloaded datacenter and folder information for " + instance['hostname'])

				## List clusters ##########
				helper.event("vmware_cache_cluster", "Downloading cluster information from " + instance['hostname'])
				signal.alarm(timeout_alarm)
				clusters_proxy = helper.lib.vmware_get_objects(content, [vim.ClusterComputeResource])
				clusters[key] = {}
				for cluster in clusters_proxy:
					# Get the managed object reference
					moId = cluster._moId

					# Start a section for this cluster
					clusters[key][moId] = {}

					## Recurse up to find the data center
					parent = cluster.parent
					found = False

					# Loop until we find the data center
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

					# Calculate cluster statistics
					total_ram   = 0
					total_cores = 0
					total_hz    = 0
					total_cpu_usage = 0
					total_ram_usage = 0

					# We check for Nones here for hosts that are in maintenance mode, which return
					# None rather than 0.
					for host in cluster.host:
						if host.hardware.memorySize is not None:
							total_ram = total_ram + host.hardware.memorySize
						if host.hardware.cpuInfo.numCpuCores is not None:
							total_cores = total_cores + host.hardware.cpuInfo.numCpuCores
						if host.hardware.cpuInfo.hz is not None:
							total_hz = total_hz + host.hardware.cpuInfo.hz
						if host.summary.quickStats.overallCpuUsage is not None:
							total_cpu_usage = total_cpu_usage + host.summary.quickStats.overallCpuUsage
						if host.summary.quickStats.overallMemoryUsage is not None:
							total_ram_usage = total_ram_usage + host.summary.quickStats.overallMemoryUsage

					# Put in our data
					clusters[key][moId]['_moId'] = moId
					clusters[key][moId]['name'] = cluster.name
					clusters[key][moId]['dc'] = clusterdc
					clusters[key][moId]['total_ram'] = total_ram
					clusters[key][moId]['total_cores'] = total_cores
					clusters[key][moId]['total_hz'] = total_hz
					clusters[key][moId]['total_cpu_usage'] = total_cpu_usage
					clusters[key][moId]['total_ram_usage'] = total_ram_usage
					clusters[key][moId]['host_count'] = len(cluster.host)

				# Finish the event
				signal.alarm(0)
				helper.end_event(description="Downloaded cluster machine information for " + instance['hostname'])

		# Note: We delete the cache from the database after downloading all the data, so 
		# as to not lock the table and have it empty whilst the job is running

		## Delete existing data from database
		# Only delete where the instance was successfully connected.
		for instance_hostname in successful_instances:
			helper.event("delete_cache", "Deleting existing cache for instance " + instance_hostname)
			curd.execute("START TRANSACTION")
			curd.execute("DELETE FROM `vmware_cache_clusters` WHERE `vcenter` = %s", (instance_hostname, ))
			curd.execute("DELETE FROM `vmware_cache_datacenters` WHERE `vcenter` = %s", (instance_hostname, ))
			curd.execute("DELETE FROM `vmware_cache_folders` WHERE `vcenter` = %s", (instance_hostname, ))
			if not skip_vms:
				curd.execute("DELETE FROM `vmware_cache_vm` WHERE `vcenter` = %s", (instance_hostname, ))
			helper.end_event(description="Deleted existing cache for instance " + instance_hostname)

		# Statistics gathering setup
		stats_vms = 0
		stats_linux = 0
		stats_winserver = 0
		stats_windesktop = 0
		stats_other = 0

		## For each vCenter that appears in the configuration
		for key in helper.config['VMWARE'].keys():
			# Get the hostname
			instance = helper.config['VMWARE'][key]

			# Check that this instance was successful
			if instance["hostname"] in successful_instances:

				# Start the event
				helper.event("vmware_cache_data", "Caching downloaded data from " + instance['hostname'])

				# If the task options doesn't say to skip VM information
				if not skip_vms:
					# For each VM
					for moId in vm_data[key]:
						# Get the VM
						vm = vm_data[key][moId]

						# Put the VM in the database
						curd.execute("INSERT INTO `vmware_cache_vm` (`id`, `vcenter`, `name`, `uuid`, `numCPU`, `memoryMB`, `powerState`, `guestFullName`, `guestId`, `hwVersion`, `hostname`, `ipaddr`, `annotation`, `cluster`, `toolsRunningStatus`, `toolsVersionStatus`, `template`) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", (vm['_moId'], instance['hostname'], vm['name'], vm['config.uuid'], vm['config.hardware.numCPU'], vm['config.hardware.memoryMB'], vm['runtime.powerState'], vm['config.guestFullName'], vm['config.guestId'], vm['config.version'], vm['guest.hostName'], vm['guest.ipAddress'], vm['config.annotation'], vm['cluster'], vm['guest.toolsRunningStatus'], vm['guest.toolsVersionStatus2'], vm['config.template']))

						# Decide what kind of OS we have and update statistics
						if vm['config.template'] == 0:
							ostr = vm['config.guestId']
							stats_vms += 1
							if 'win' in ostr:
								# Check between Windows Server and Desktop
								if 'winLonghornGuest' in ostr or 'winLonghorn64Guest' in ostr or 'windows7Guest' in ostr or 'windows7_64Guest' in ostr or 'windows8Guest' in ostr or 'windows8_64Guest' in ostr or 'windows9Guest' in ostr or 'windows9_64Guest' in ostr:
									stats_windesktop += 1
								else:
									stats_winserver += 1
							elif "Linux" in ostr or 'linux' in ostr or 'rhel' in ostr or 'sles' in ostr or 'ubuntu' in ostr or 'centos' in ostr or 'debian' in ostr:
								stats_linux += 1
							else:
								stats_other += 1

				# For each Data Center, put it in the database (and the folders too)
				for dc in dcs[key]:
					curd.execute("INSERT INTO `vmware_cache_datacenters` (`id`, `name`, `vcenter`) VALUES (%s, %s, %s)", (dc._moId, dc.name, instance['hostname']))

					for folder in folders[dc._moId]:
						curd.execute("INSERT INTO `vmware_cache_folders` (`id`, `name`, `vcenter`, `did`, `parent`) VALUES (%s, %s, %s, %s, %s)",(folder['_moId'], folder['name'], instance['hostname'], dc._moId, folder['parent']))

				# For each cluster
				for moId in clusters[key]:
					# Get the cluster
					cluster = clusters[key][moId]

					# Put the cluster in the database
					curd.execute("INSERT INTO `vmware_cache_clusters` (`id`, `name`, `vcenter`, `did`, `ram`, `cores`, `cpuhz`, `cpu_usage`, `ram_usage`, `hosts`) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", (cluster['_moId'], cluster['name'], instance['hostname'], cluster['dc'], cluster['total_ram'], cluster['total_cores'], cluster['total_hz'], cluster['total_cpu_usage'], cluster['total_ram_usage'], cluster['host_count']))

				helper.end_event(description="Cached information from " + instance['hostname'])

		# Update statistics tables
		helper.event("vmware_stats_update", "Updating statistics")
		curd.execute("INSERT INTO `stats_vm_count` (`timestamp`, `value`) VALUES (NOW(), %s)", (stats_vms,))
		curd.execute("INSERT INTO `stats_linux_vm_count` (`timestamp`, `value`) VALUES (NOW(), %s)", (stats_linux,))
		curd.execute("INSERT INTO `stats_windows_vm_count` (`timestamp`, `value`) VALUES (NOW(), %s)", (stats_winserver,))
		curd.execute("INSERT INTO `stats_desktop_vm_count` (`timestamp`, `value`) VALUES (NOW(), %s)", (stats_windesktop,))
		curd.execute("INSERT INTO `stats_other_vm_count` (`timestamp`, `value`) VALUES (NOW(), %s)", (stats_other,))
		helper.end_event(description="Statistics updated")

		# Commit all the changes to the database
		helper.event("vmware_cache_dc", "Saving cache to disk")
		tdb.commit()
		helper.end_event(description="Saved cache to disk")

def recurse_folder(folder, folders):
	children = folder.childEntity

	for child in children:
		if isinstance(child, vim.Folder):
			folders.append({'_moId': child._moId, 'name': child.name, 'parent': folder._moId})

			if len(child.childEntity) > 0:
				recurse_folder(child, folders)
 

