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
	curd.execute('SELECT `vmware_cache_vm`.`vcenter`, `vmware_cache_vm`.`name`, `vmware_cache_vm`.`uuid`, `systems`.`expiry_date` from `systems` LEFT JOIN `vmware_cache_vm` ON `systems`.`vmware_uuid` = `vmware_cache_vm`.`uuid` WHERE `systems`.`expiry_date` < NOW()')

	helper.end_event(description="Expiration checking complete - " + str(shutdowncount) + " VM(s) shutdown")

	shutdowncount = 0

	for row in curd:
		vm=helper.lib.vmware_get_vm_by_uuid(row['uuid'], row['vcenter'])
		if vm.runtime.powerState == vim.VirtualMachine.PowerState.poweredOn:
			try:
				helper.lib.vmware_vm_shutdown_guest(vm)
			except vim.fault.ToolsUnavailable, e:
				try:
					helper.lib.vmware_vm_poweroff(vm)
				except Exception, e:
					pass
			except vim.fault.InvalidPowerState, e:
				pass
			except Exception, e:
				pass

			print('Shutdown ' + vm.config.name)
			shutdowncount += 1

	helper.end_event(description="Expiration checking complete - " + str(shutdowncount) + " VM(s) shutdown")
