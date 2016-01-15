#!/usr/bin/python

import Pyro4
import os
import MySQLdb as mysql
import sys
import json
import time

import requests
requests.packages.urllib3.disable_warnings()

## for vmware
from pyVmomi import vim
from pyVmomi import vmodl
from pyVim.connect import SmartConnect, Disconnect

class NeoCortexLib(object):
	"""Library functions used in both neocortex itself and the neocortex tasks, hence a seperate object"""

	OS_TYPE_BY_ID   = {0: "None", 1: "Linux", 2: "Windows" }
	OS_TYPE_BY_NAME = {"None": 0, "Linux": 1, "Windows": 2}
	SYSTEM_TYPE_BY_ID = {0: "System", 1: "Legacy", 2: "Other"}
	SYSTEM_TYPE_BY_NAME = {"System": 0, "Legacy": 1, "Other": 2}

	class TaskFatalError(Exception):
		def __init__(self, message="The task failed for an unspecified reason"):
			self.message = str(message)

		def __str__(self):
			return self.message

	class VMwareTaskError(Exception):
		def __init__(self, message="An error was returned from vmware"):
			self.message = str(message)

		def __str__(self):
			return self.message

	def __init__(self, db, config):
		self.db = db
		self.config = config

	################################################################################

	def allocate_name(self, class_name, comment, username, num=1):
		"""Allocates 'num' systems, of type 'class_name' each with the given
		comment. Returns a dictionary with mappings between each new name
		and the corresponding row ID in the database table."""

		# dictionary of new systems
		new_systems = {}

		# Get a cursor to the database
		cur = self.db.cursor(mysql.cursors.DictCursor)

		# The following MySQL code is a bit complicated but as an explanation:
		#  * The classes table contains the number of the next system in each
		#    class to allocate.
		#  * To prevent race conditions when allocating (and thus so two
		#    systems don't get allocated with the same number) we lock the 
		#    tables we want to view/modify during this function.
		#  * This prevents other simultanteously running calls to this function
		#    from allocating a name temporarily (the call to LOCK TABLE will
		#    block/hang until the tables become unlocked again).
		#  * Once a lock is aquired, we get the next number to allocate from
		#    the classes table, update that table with the next new number,
		#    based on how many names we're simultaneously allocating, and then
		#    create the systems in the systems table.
		#  * This is all commited as one transaction so either this all happens
		#    or none of it happens (i.e. in case of an error)
		#  * In all scenarios, we end by unlocking the table so other calls to
		#    this function can carry on.

		## 1. Lock the table to prevent other requests issuing names whilst we are
		cur.execute('LOCK TABLE `classes` WRITE, `systems` WRITE; ')

		# 2a. Get the class (along with the next nubmer to allocate)
		try:
			cur.execute("SELECT * FROM `classes` WHERE `name` = %s",(class_name))
			class_data = cur.fetchone()
		except Exception as ex:
			cur.execute('UNLOCK TABLES;')
			raise Exception("Selected system class does not exist: cannot allocate system name")

		# 2b. Ensure the class was found and that it is not disabled
		if class_data == None:
			cur.execute('UNLOCK TABLES;')
			raise Exception("Selected system class does not exist: cannot allocate system name")
		elif int(class_data['disabled']) == 1:
			cur.execute('UNLOCK TABLES;')
			raise Exception("Selected system class has been disabled: cannot allocate: cannot allocate system name")

		try:
			## 3. Increment the number by the number we're simultaneously allocating
			cur.execute("UPDATE `classes` SET `lastid` = %s WHERE `name` = %s", (int(class_data['lastid']) + int(num), class_name))

			## 4. Create the appropriate number of servers
			for i in xrange(1, num+1):
				new_number = int(class_data['lastid']) + i
				new_name   = self.pad_system_name(class_name, new_number, class_data['digits'])

				cur.execute("INSERT INTO `systems` (`type`, `class`, `number`, `name`, `allocation_date`, `allocation_who`, `allocation_comment`) VALUES (%s, %s, %s, %s, NOW(), %s, %s)",
					(self.SYSTEM_TYPE_BY_NAME['System'], class_name, new_number, new_name, username, comment))

				# store a record of the new system so we can give this back to the browser in a minute
				new_systems[new_name] = cur.lastrowid

			## 5. All names are now created and the table incremented. Time to commit.
			self.db.commit()
		except Exception as ex:
			cur.execute('UNLOCK TABLES;')
			raise ex

		## 6. Finally, unlock the tables so others can allocate
		cur.execute('UNLOCK TABLES;')

		return new_systems

	################################################################################

	def pad_system_name(self, prefix, number, digits):
		"""Takes a class name ('prefix') a system number, and the number of
		digits that class should have in its name and formats a string to that
		specification. For example, if prefix is 'test', number is '12' and
		'digits' is 5, then this returns 'test00012'"""

		return ("%s%0" + str(int(digits)) + "d") % (prefix, number)	

	################################################################################

	def infoblox_create_host(self, name, subnet):
		payload = {'name': name, "ipv4addrs": [{"ipv4addr":"func:nextavailableip:" + subnet}],}
		r = requests.post("https://" + self.config['INFOBLOX_HOST'] + "/wapi/v2.0/record:host", data=json.dumps(payload), auth=(self.config['INFOBLOX_USER'], self.config['INFOBLOX_PASS']))

		if r.status_code == 201:
			objectid = str(r.json())
			r = requests.get("https://" + self.config['INFOBLOX_HOST'] + "/wapi/v2.0/" + objectid, auth=(self.config['INFOBLOX_USER'], self.config['INFOBLOX_PASS']))
	
			if r.status_code == 200:
				response = r.json()

				try:
					return response['ipv4addrs'][0]['ipv4addr']
				except Exception as ex:
					raise InfobloxError("Malformed JSON response from Infoblox API")
			else:
				raise InfobloxError("Error returned from Infoblox API. Code " + str(r.status_code) + ": " + r.text)
		else:
			raise InfobloxError("Error returned from Infoblox API. Code " + str(r.status_code) + ": " + r.text)

	################################################################################

	def vmware_get_obj(self, content, vimtype, name):
		"""
		Return an object by name, if name is None the
		first found object is returned. Searches within
		content.rootFolder (i.e. everything on the vCenter)
		"""

		return self.vmware_get_obj_within_parent(content, vimtype, name, content.rootFolder)

	################################################################################

	def vmware_get_obj_within_parent(self, content, vimtype, name, parent):
		"""
		Return an object by name, if name is None the
		first found object is returned. Set parent to be
		a Folder, Datacenter, ComputeResource or ResourcePool under
		which to search for the object.
		"""
		obj = None
		container = content.viewManager.CreateContainerView(parent, vimtype, True)
		for c in container.view:
			if name:
				if c.name == name:
					obj = c
					break
			else:
				obj = c
				break

		return obj

	################################################################################

	def vmware_task_wait(self, task):
		"""Waits for vCenter task to finish"""

		task_done = False

		while not task_done:
			if task.info.state == 'success':
				return True

			if task.info.state == 'error':
				return False

			## other states are 'queued' and 'running'
			## which we should just wait on.

			## lets not busy wait CPU 100%...
			time.sleep(1)

	################################################################################

	def vmware_task_complete(self, task, on_error="VMware API Task Failed"):
		"""
		Block until the given task is complete. An exception is 
		thrown if the task results in an error state. This function
		does not return a variable.
		"""

		task_done = False

		while not task_done:
			if task.info.state == 'success':
				return

			if task.info.state == 'error':
			
				## Try to get a meaningful error message
				if hasattr(task.info.error,'msg'):
					error_message = task.info.error.msg
				else:
					error_message = str(task.info.error)

				on_error = on_error + ': '

				raise RuntimeError(on_error + error_message)

			## If not success or error, then sleep a bit and check again.
			## Otherwise we just busywaitloop the CPU at 100% for no reason.
			time.sleep(1)

	################################################################################

	def vmware_vm_custspec(self, dhcp=True, gateway=None, netmask=None, ipaddr=None, dns_servers="8.8.8.8", dns_domain="localdomain", os_type=None, os_domain="localdomain", timezone=None, hwClockUTC=True, domain_join_user=None, domain_join_pass=None, fullname=None, orgname=None, productid=""):
		"""This function generates a vmware VM customisation spec for use in cloning a VM. 

		   If you choose DHCP (the default) the gateway, netmask, ipaddr, dns_servers and dns_domain parameters are ignored.

		   For Linux use these optional parameters:
		   os_domain - usually soton.ac.uk
		   hwClockUTC - usually True
		   timezone - usually 'Europe/London'

		   For Windows use these optional parameters:
		   timezone - numerical ID, usually 85 for UK.
		   os_domain   - the AD domain to join, usually soton.ac.uk
		   domain_join_user - the user to join AD with
		   domain_join_pass - the user's password
		   fullname - the fullname of the customer
		   orgname - the organisation name of the customer

		"""

		## global IP settings
		globalIPsettings = vim.vm.customization.GlobalIPSettings()

		## these are optional for DHCP
		if not dhcp:
			globalIPsettings.dnsSuffixList = [dns_domain]
			globalIPsettings.dnsServerList  = dns_servers

		## network settings master object
		ipSettings                   = vim.vm.customization.IPSettings()

		## the IP address
		if dhcp:
			ipSettings.ip            = vim.vm.customization.DhcpIpGenerator()
		else:
			fixedIP                  = vim.vm.customization.FixedIp()
			fixedIP.ipAddress        = ipaddr
			ipSettings.ip            = fixedIP
			ipSettings.dnsDomain     = dns_domain
			ipSettings.dnsServerList = dns_servers
			ipSettings.gateway       = [gateway]
			ipSettings.subnetMask    = netmask

		## Create the 'adapter mapping'
		adapterMapping            = vim.vm.customization.AdapterMapping()
		adapterMapping.adapter    = ipSettings

		# create the customisation specification
		custspec                  = vim.vm.customization.Specification()
		custspec.globalIPSettings = globalIPsettings
		custspec.nicSettingMap    = [adapterMapping]

		if os_type == self.OS_TYPE_BY_NAME['Linux']:

			linuxprep            = vim.vm.customization.LinuxPrep()
			linuxprep.domain     = os_domain
			linuxprep.hostName   = vim.vm.customization.VirtualMachineNameGenerator()
			linuxprep.hwClockUTC = hwClockUTC
			linuxprep.timeZone   = timezone

			## finally load in the sysprep into the customisation spec
			custspec.identity = linuxprep
	
		elif os_type == self.OS_TYPE_BY_NAME['Windows']:

			## the windows sysprep /CRI
			guiUnattended = vim.vm.customization.GuiUnattended()
			guiUnattended.autoLogon = False
			guiUnattended.autoLogonCount = 0
			guiUnattended.timeZone = timezone

			sysprepIdentity = vim.vm.customization.Identification()
			sysprepIdentity.domainAdmin = domain_join_user
			sysprepPassword = vim.vm.customization.Password()
			sysprepPassword.plainText = True
			sysprepPassword.value = domain_join_pass
			sysprepIdentity.domainAdminPassword = sysprepPassword
			sysprepIdentity.joinDomain = os_domain

			sysprepUserData = vim.vm.customization.UserData()
			sysprepUserData.computerName = vim.vm.customization.VirtualMachineNameGenerator()
			sysprepUserData.fullName = fullname
			sysprepUserData.orgName = orgname
			sysprepUserData.productId = productid

			sysprep                = vim.vm.customization.Sysprep()
			sysprep.guiUnattended  = guiUnattended
			sysprep.identification = sysprepIdentity
			sysprep.userData       = sysprepUserData

			## finally load in the sysprep into the customisation spec
			custspec.identity = sysprep

		else:
			raise Exception("Invalid os_type")

		return custspec

	################################################################################

	def vmware_smartconnect(self, tag):
		instance = self.config['VMWARE'][tag]
		return SmartConnect(host=instance['hostname'], user=instance['user'], pwd=instance['pass'], port=instance['port'])

	################################################################################
	
	def vmware_clone_vm(self, service_instance, vm_template, vm_name, vm_datacenter=None, vm_datastore=None, vm_folder=None, vm_cluster=None, vm_rpool=None, vm_network=None, vm_poweron=False, custspec=None):
		"""This function connects to vcenter and clones a virtual machine. Only vm_template and
		   vm_name are required parameters although this is unlikely what you'd want - please
		   read the parameters and check if you want to use them.

		   If you want to customise the VM after cloning attach a customisation spec via the 
		   custspec optional parameter.

		   TODO: vm_network currently does not work.
		   TODO: exception throwing when objects are not found...

		"""

		content = service_instance.RetrieveContent()

		## Get the template
		template = self.vmware_get_obj(content, [vim.VirtualMachine], vm_template)

		## VMware datacenter - this is only used to get the folder
		datacenter = self.vmware_get_obj(content, [vim.Datacenter], vm_datacenter)

		## VMware folder
		if vm_folder:
			destfolder = get_obj(content, [vim.Folder], vm_folder)
		else:
			destfolder = datacenter.vmFolder

		## VMware datastore
		datastore = self.vmware_get_obj(content, [vim.Datastore], vm_datastore)

		## Get the VMware Cluster
		cluster = self.vmware_get_obj(content, [vim.ClusterComputeResource], vm_cluster)

		## You can't specify a cluster for a VM to be created on, instead you specify either a host or a resource pool.
		## We will thus create within a resource pool. 

		# If this function isn't passed a resource pool then choose the default:
		if vm_rpool == None:
			rpool = cluster.resourcePool

		else:

			## But if we are given a specific resource pool...
			## ...but we werent given a specific cluster, then just search for the resource pool name anywhere on the vCenter:
			if vm_cluster == None:
				rpool = self.vmware_get_obj(content, [vim.ResourcePool], vm_rpool)

			else:
				# ...but if we were given a specific cluster *and* a specific resource pool, then search for the resource pool within that cluster's resource pools:
				rpool = self.vmware_get_obj_within_parent(content, [vim.ResourcePool], vm_rpool, cluster.resourcePool)

			## If we didn't find a resource pool just use the default one for the cluster
			if rpool == None:
				rpool = cluster.resourcePool

		## Create the relocation specification
		relospec = vim.vm.RelocateSpec()
		relospec.datastore = datastore
		relospec.pool = rpool

		## Create the clone spec
		clonespec = vim.vm.CloneSpec()
		clonespec.powerOn  = vm_poweron
		clonespec.location = relospec

		## If the user wants to customise the VM after creation...
		if not custspec == False:
			clonespec.customization = custspec

		return template.Clone(folder=destfolder, name=vm_name, spec=clonespec)

	############################################################################
	
	def update_vm_cache(self, vm, tag):
		"""Updates the VMware cache data with the information about the VM."""

		# Get a cursor to the database
		cur = self.db.cursor(mysql.cursors.DictCursor)
		
		# Get the instance details of the vCenter given by tag
		instance = self.config['VMWARE'][tag]

		if vm.guest.hostName is not None:
			hostName = vm.guest.hostName
		else:
			hostName = ""

		if vm.guest.ipAddress is not None:
			ipAddress = vm.guest.ipAddress
		else:
			ipAddress = ""

		if vm.config.annotation is not None:
			annotation = vm.config.annotation
		else:
			annotation = ""

		# Put in the resource pool name rather than a Managed Object
		if vm.resourcePool is not None:
			cluster = vm.resourcePool.owner.name
		else:
			cluster = "None"

		# Put the VM in the database
		cur.execute("REPLACE INTO `vmware_cache_vm` (`id`, `vcenter`, `name`, `uuid`, `numCPU`, `memoryMB`, `powerState`, `guestFullName`, `guestId`, `hwVersion`, `hostname`, `ipaddr`, `annotation`, `cluster`, `toolsRunningStatus`, `toolsVersionStatus`) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", (vm._moId, instance['hostname'], vm.name, vm.config.uuid, vm.config.hardware.numCPU, vm.config.hardware.memoryMB, vm.runtime.powerState, vm.config.guestFullName, vm.config.guestId, vm.config.version, hostName, ipAddress, annotation, cluster, vm.guest.toolsRunningStatus, vm.guest.toolsVersionStatus2))

		# Commit
		self.db.commit()

	############################################################################
	
	def puppet_enc_register(self, system_id, certname, environment):
		"""
		"""

		# Get a cursor to the database
		curd = self.db.cursor(mysql.cursors.DictCursor)

		# Add environment if we've got it
		environments = dict((e['id'], e) for e in self.config['ENVIRONMENTS'] if e['puppet'])
		if environment is not None and environment in environments:
			puppet_environment = environments[environment]['puppet']

		# Insert the row
		curd.execute("INSERT INTO `puppet_nodes` (`id`, `certname`, `env`, `include_default`, `classes`, `variables`) VALUES (%s, %s, %s, %s, %s, %s)", (system_id, certname, puppet_environment, 1, "", ""))

		# Commit
		self.db.commit()

	############################################################################

	def vmware_vmreconfig_notes(self, vm, notes):
		"""Sets the notes annotation for the VM."""

		configSpec              = vim.VirtualMachineConfigSpec()
		configSpec.annotation   = notes
		return vm.ReconfigVM_Task(configSpec)

	############################################################################

	def vmware_vmreconfig_cpu(self, vm, cpus, cpus_per_socket, hotadd=True):
		"""Reconfigures the CPU count of a VM and enables/disabled CPU hot-add. 'vm' 
		is a PyVmomi managed object, 'cpus' is the TOTAL number of vCPUs to have, and
		'cpus_per_socket' is the number of cores per socket. The VM will end up having
		(cpus / cpus_per_socket) CPU sockets, each having cpus_per_socket. 'hotadd'
		is a boolean indicating whether or not to enable hot add or not.

		Returns a PyVmomi task object relating to the VMware task."""

		configSpec                   = vim.VirtualMachineConfigSpec()
		configSpec.cpuHotAddEnabled  = hotadd
		configSpec.numCPUs           = cpus
		configSpec.numCoresPerSocket = cpus_per_socket
		return vm.ReconfigVM_Task(configSpec)

	############################################################################

	def vmware_vmreconfig_ram(self, vm, megabytes=1024, hotadd=True):
		"""Reconfigures the amount of RAM a VM has, and whether memory can be hot-
		added to the system. 'vm' is a PyVmomi managed object, 'megabytes' is the 
		required amount of RAM in megabytes. 'hotadd' is a boolean indicating whether
		or not to enable hot add or not.

		Returns a PyVmomi task object relating to the VMware task."""

		configSpec                     = vim.VirtualMachineConfigSpec()
		configSpec.memoryHotAddEnabled = hotadd
		configSpec.memoryMB            = megabytes
		return vm.ReconfigVM_Task(configSpec)

	############################################################################

	def vmware_vm_add_disk(self, vm, size_in_bytes, thin=True):
		
		# find the last SCSI controller on the VM
		for device in vm.config.hardware.device:
			if isinstance(device, vim.vm.device.VirtualSCSIController):
				controller = device

			if hasattr(device.backing, 'fileName'):
				unit_number = int(device.unitNumber) + 1

				## unit_number 7 reserved scsi controller (cos of historical legacy stuff when LUN numbers were 0 to 7 and 7 was the highest priority hence the controller)
				if unit_number == 7:
					unit_number = 8

				## can't have more than 16 disks
				if unit_number >= 16:
					raise Exception("Too many disks on the SCSI controller")				

		if controller == None:
			raise Exception("No scsi controller found!")

		if unit_number == None:
			raise Exception("Unable to calculate logical unit number for SCSI device")

		newdev = vim.vm.device.VirtualDeviceSpec()		
		newdev.fileOperation = "create"
		newdev.operation = "add"
		newdev.device = vim.vm.device.VirtualDisk()

		newdev.device.backing = vim.vm.device.VirtualDisk.FlatVer2BackingInfo()
		newdev.device.backing.diskMode = 'persistent'
		if thin:
			newdev.device.backing.thinProvisioned = True


		newdev.device.capacityInBytes = size_in_bytes
		newdev.device.capacityInKB = size_in_bytes * 1024
		newdev.device.controllerKey = controller.key
		newdev.device.unitNumber = unit_number

		devices = []
		devices.append(newdev)

		configSpec = vim.vm.ConfigSpec()
		configSpec.deviceChange = devices
		return vm.ReconfigVM_Task(spec=configSpec)

	############################################################################

	def vmware_vm_poweron(self, vm):
		"""Powers on a virtual machine."""

		return vm.PowerOn()

	############################################################################

	def vmware_wait_for_poweron(self, vm, timeout=30):
		"""Waits for a virtual machine to be marked as powered up by VMware."""

		# Initialise our timer
		timer = 0

		# While the VM is not marked as powered on, and our timer has not hit our timeout
		while vm.runtime.powerState != vim.VirtualMachinePowerState.poweredOn and timer < timeout:
			# Wait
			time.sleep(1)
			timer = timer + 1

		# Return whether the VM is powered up or not
		return vm.runtime.powerState == vim.VirtualMachinePowerState.poweredOn

	############################################################################

	def vmware_collect_properties(self, service_instance, view_ref, obj_type, path_set=None, include_mors=False):
		"""
		Collect properties for managed objects from a view ref
		Check the vSphere API documentation for example on retrieving
		object properties:
			- http://goo.gl/erbFDz
		Args:
			si		(ServiceInstance): ServiceInstance connection
			view_ref (pyVmomi.vim.view.*): Starting point of inventory navigation
			obj_type	 (pyVmomi.vim.*): Type of managed object
			path_set			(list): List of properties to retrieve
			include_mors		 (bool): If True include the managed objects
									refs in the result
		Returns:
			A list of properties for the managed objects
		"""

		collector = service_instance.content.propertyCollector

		# Create object specification to define the starting point of
		# inventory navigation
		obj_spec = vmodl.query.PropertyCollector.ObjectSpec()
		obj_spec.obj = view_ref
		obj_spec.skip = True

		# Create a traversal specification to identify the path for collection
		traversal_spec = vmodl.query.PropertyCollector.TraversalSpec()
		traversal_spec.name = 'traverseEntities'
		traversal_spec.path = 'view'
		traversal_spec.skip = False
		traversal_spec.type = view_ref.__class__
		obj_spec.selectSet = [traversal_spec]

		# Identify the properties to the retrieved
		property_spec = vmodl.query.PropertyCollector.PropertySpec()
		property_spec.type = obj_type

		if not path_set:
			property_spec.all = True

		property_spec.pathSet = path_set

		# Add the object and property specification to the
		# property filter specification
		filter_spec = vmodl.query.PropertyCollector.FilterSpec()
		filter_spec.objectSet = [obj_spec]
		filter_spec.propSet = [property_spec]

		# Retrieve properties
		props = collector.RetrieveContents([filter_spec])

		data = []
		for obj in props:
			properties = {}
			for prop in obj.propSet:
				properties[prop.name] = prop.val

			if include_mors:
				properties['obj'] = obj.obj

			data.append(properties)

		return data

	############################################################################

	def vmware_get_container_view(self, service_instance, obj_type, container=None):
		"""
		Get a vSphere Container View reference to all objects of type 'obj_type'
		It is up to the caller to take care of destroying the View when no longer
		needed.
		Args:
		   obj_type (list): A list of managed object types
		Returns:
		   A container view ref to the discovered managed objects
		"""
		if not container:
			container = service_instance.content.rootFolder

		view_ref = service_instance.content.viewManager.CreateContainerView(container=container, type=obj_type, recursive=True)
		return view_ref

	############################################################################

	def vmware_get_objects(self, content, vimtype):
		"""
		Return an object by name, if name is None the
		first found object is returned
		"""
		obj = None
		container = content.viewManager.CreateContainerView(content.rootFolder, vimtype, True)
		return container.view

	############################################################################

	def set_link_ids(self, cortex_system_id, cmdb_id):
		"""
		Sets the identifiers that link a system from the Cortex `systems` 
		table to their relevant item in the CMDB.
		 - cortex_system_id: The id of the system in the table (not the name)
		 - cmdb_id: The value to store for the CMDB ID field.
		"""

		# Get a cursor to the database
		cur = self.db.cursor(mysql.cursors.DictCursor)

		# Update the database
		cur.execute("UPDATE `systems` SET `cmdb_id` = %s WHERE `id` = %s", (cmdb_id, cortex_system_id))

		# Commit
		self.db.commit()

	################################################################################

	def servicenow_link_task_to_ci(self, ci_sys_id, task_number):
		"""Links a ServiceNow 'task' (Incident Task, Project Task, etc.) to a CI so that it appears in the related records. 
		   Note that you should NOT use this function to link an incident to a CI (even though ServiceNow will kind of let
		   you do this...)
		     - ci_sys_id: The sys_id of the created configuration item, as returned by servicenow_create_ci
		     - task_number: The task number (e.g. INCTASK0123456, PRJTASK0123456) to link to. NOT the sys_id of the task."""

		# Request information about the task (incident task, project task, etc.) to get its sys_id
		r = requests.get('https://' + self.config['SN_HOST'] + '/api/now/v1/table/task?sysparm_fields=sys_id&sysparm_query=number=' + task_number, auth=(self.config['SN_USER'], self.config['SN_PASS']), headers={'Accept': 'application/json'})

		# Check we got a valid response
		if r is not None and r.status_code >= 200 and r.status_code <= 299:
			# Get the response
			response_json = r.json()
			
			# This returns something like this:
			# {"result": [{"sys_id": "f49bc4bb0fc3b500488ec453e2050ec3", "number": "PRJTASK0123456"}]}
			
			# Get the sys_id of the task
			try:
				task_sys_id = response_json['result'][0]['sys_id']
			except Exception as e:
				# Handle JSON not containing 'result', a first element, or a 'sys_id' parameter (not that this should happen, really...)
				raise Exception("Failed to query ServiceNow for task information. Invalid response from ServiceNow.")

			# Make a post request to link the given CI to the task
			r = requests.post('https://' + self.config['SN_HOST'] + '/api/now/v1/table/task_ci', auth=(self.config['SN_USER'], self.config['SN_PASS']), headers={'Accept': 'application/json', 'Content-Type': 'application/json'}, json={'ci_item': ci_sys_id, 'task': task_sys_id})

			# If we succeeded, return the sys_id of the link table entry
			if r is not None and r.status_code >= 200 and r.status_code <= 299:
				return response_json['result'][0]['sys_id']
			else:
				error = "Failed to link ServiceNow task and CI."
				if r is not None:
					error = error + " HTTP Response code: " + str(r.status_code)
				raise Exception(error)
		else:
			# Return error with appropriate information
			error = "Failed to query ServiceNow for task information."
			if r is not None:
				if r.status_code == 404:
					error = error + " Task '" + str(task_number) + "' does not exist"
				else:
					error = error + " HTTP Response code: " + str(r.status_code)
			raise Exception(error)


	################################################################################

	def servicenow_create_ci(self, ci_name, os_type, os_name, cpus='', ram_mb='', disk_gb='', ipaddr='', virtual=True, environment=None, short_description='', comments='', location=None):
		"""Creates a new CI within ServiceNow.
		     - ci_name: The name of the CI, e.g. srv01234
		     - os_type: The OS type as a number, see OS_TYPE_BY_NAME
		     - os_name: The name of the OS, as used by ServiceNow
		     - cpus: The total number of CPUs the CI has
		     - ram_mb: The amount of RAM of the CI in MeB
		     - disk_gb: The total amount of disk space in GiB
		     - ipaddr: The IP address of the CI
		     - virtual: Boolean indicating if the CI is a VM (True) or Physical (False). Defaults to True.
		     - environment: The id of the environment (see the application configuration) that the CI is in
		     - short_description: The value of the short_description (Description) field in ServiceNow. A purpose, or something.
		     - comments: The value of the comments field in ServiceNow. Any random information.
		     - location: The value of the location field in ServiceNow

		On success, returns the sys_id of the object created in ServiceNow.
		"""

		# Decide which ServiceNow table we need to put the CI in to, based on the OS
		if os_type == self.OS_TYPE_BY_NAME['Linux']:
			table_name = "cmdb_ci_linux_server"
			model_id = "Generic Linux Virtual Server"
		elif os_type == self.OS_TYPE_BY_NAME['Windows']:
			table_name = "cmdb_ci_windows_server"
			model_id = "Generic Windows Virtual Server"
		else:
			raise Exception('Unknown os_type passed to servicenow_create_ci')

		# Build the data for the CI
		vm_data = { 'name': str(ci_name), 'os': str(os_name), 'cpu_count': str(cpus), 'disk_space': str(disk_gb), 'virtual': str(virtual).lower(), 'ip_address': ipaddr, 'ram': str(ram_mb), 'operational_status': 'In Service', 'model_id': model_id, 'short_description': short_description, 'comments': comments }

		# Add location if we've got it
		if location is not None:
			vm_data['location'] = location

		# Add environment if we've got it
		environments = dict((e['id'], e) for e in self.config['ENVIRONMENTS'] if e['cmdb'])
		if environment is not None and environment in environments:
			vm_data['u_environment'] = environments[environment]['cmdb']

		# json= was only added in Requests 2.4.2, so might need to be data=json.dumps(vm_data)
		# Content-Type header may be superfluous as Requests might add it anyway, due to json=
		r = requests.post('https://' + self.config['SN_HOST'] + '/api/now/v1/table/' + table_name + "?sysparm_display_value=true", auth=(self.config['SN_USER'], self.config['SN_PASS']), headers={'Accept': 'application/json', 'Content-Type': 'application/json'}, json=vm_data)

		# Parse the response
		if r is not None and r.status_code >= 200 and r.status_code <= 299:
			# Parse the JSON and return the sys_id that ServiceNow gives us along with the CMDB ID (u_number)
			response_json = r.json()
			retval = (response_json['result']['sys_id'], response_json['result']['u_number'])
		else:
			error = "Failed to create ServiceNow object. API Request failed."
			if r is not None:
				error = error + " HTTP Response code: " + str(r.status_code)
			raise Exception(error)

		# Get a cursor to the database
		curd = self.db.cursor(mysql.cursors.DictCursor)

		# Update the cache row
		curd.execute("REPLACE INTO `sncache_cmdb_ci` (`sys_id`, `sys_class_name`, `name`, `operational_status`, `u_number`, `short_description`, `u_environment`, `virtual`) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", (retval[0], response_json['result']['sys_class_name'], vm_data['name'], 'In Service', retval[1], short_description, response_json['result']['u_environment'], 1))
		self.db.commit()

		return retval

		## puppet stuff?
		## let users logon??
		## windows ou?
