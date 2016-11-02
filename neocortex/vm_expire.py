#!/usr/bin/python

import MySQLdb as mysql
import sys, copy, os
from pyVmomi import vim

def run(helper, options):
	# Connect to the database
	db = helper.db_connect()
	curd = db.cursor(mysql.cursors.SSDictCursor)

	helper.event('check_expired', 'Checking for expired VMs')

	# Select all the systems which have expired
	curd.execute('SELECT * FROM `systems_info_view` WHERE `expiry_date` < NOW() `vmware_uuid` IS NOT NULL')
	systems = curd.fetchall()

	helper.end_event(description="Expiration checking complete - " + str(len(systems)) + " found expired")

	for row in systems:
		vm = helper.lib.vmware_get_vm_by_uuid(row['vmware_uuid'], row['vmware_vcenter'])
		if vm is not None:
			if vm.runtime.powerState == vim.VirtualMachine.PowerState.poweredOn:
				failed = False

				try:
					helper.lib.vmware_vm_shutdown_guest(vm)

				except vim.fault.ToolsUnavailable, e:

					try:
						helper.lib.vmware_vm_poweroff(vm)
					except Exception, e:
						failed = True
						pass

				except Exception, e:
					failed = True				
					pass

				if not failed:
					helper.event('check_expire_poweroff', 'The system ' + row['name'] + " (ID " + str(row['id']) + ") has been turned off",oneshot=True)
				else:
					helper.event('check_expire_poweroff', 'The system ' + row['name'] + " (ID " + str(row['id']) + ") failed to turn off",success=False,oneshot=True)

