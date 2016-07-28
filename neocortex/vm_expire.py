#!/usr/bin/python

import requests
import MySQLdb as mysql
import sys, copy, os
from pyVmomi import vim

def run(helper, options):
	# Connect to the database
	db = helper.db_connect()
	curd = db.cursor(mysql.cursors.SSDictCursor)

	helper.event('check_expired', 'Checking for expired VMs')

	# Delete all the server CIs from the table (we must do this before we delete 
	# from the choices tables as there is a foreign key constraint)
	curd.execute('SELECT `vmware_cache_vm`.`vcenter`, `vmware_cache_vm`.`name`, `vmware_cache_vm`.`uuid`, `systems`.`expiry_date` from `systems` LEFT JOIN `vmware_cache_vm` ON `systems`.`vmware_uuid` = `vmware_cache_vm`.`uuid` WHERE `systems`.`expiry_date` < NOW()')
	

	shutdowncount = 0

	for row in curd:
		vm=helper.lib.get_by_uuid(row['uuid'], row['vcenter'])
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
