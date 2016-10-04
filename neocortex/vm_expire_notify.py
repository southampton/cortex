#!/usr/bin/python

import MySQLdb as mysql
import sys, copy, os
from pyVmomi import vim

def run(helper, options):
	# Connect to the database
	db = helper.db_connect()
	curd = db.cursor(mysql.cursors.DictCursor)

	helper.event('check_expire_count', 'Checking for systems due to expire in the next week')
	curd.execute('SELECT * FROM `systems_info_view` WHERE `expiry_date` > NOW() AND `expiry_date` < NOW() + INTERVAL 7 DAY')
	systems = curd.fetchall()
	helper.end_event(description="Found " + str(len(systems)) + " system(s) which will expire in the next seven days")

	## If no systems are due to expire
	if len(systems) == 0:
		helper.event('check_expire_none', 'No systems will expire within the next seven days, not sending notification e-mail',oneshot=True)	
		return

	message = "The following systems will expire in the next seven days. When they expire Cortex will turn the virtual machines off and ensure they remain switched off. The virtual machines will not be deleted.\n\n"

	## Check the power status of all the VMs
	for system in systems:
		## Determine if the VM is currently powered on, we directly ask vCenter
		## rather than rely on the cache so we're 100% accurate at the time of
		## sending the summary e-mail
		vm = helper.lib.vmware_get_vm_by_uuid(system['vmware_uuid'], system['vmware_vcenter'])
		system_status = "off"
		if vm.runtime.powerState == vim.VirtualMachine.PowerState.poweredOn:
			system_status = "on"
			helper.event('check_expire_found', 'The system ' + system['name'] + " (ID " + str(system['id']) + ") will expire in the next seven days",oneshot=True)

		system_link = 'https://' + helper.config['CORTEX_DOMAIN'] + '/systems/edit/' + str(system['id'])

		message = message + """%s - %s
Expires on:    %s
Status:        Powered %s
OS:            %s
Comment:       %s 
CMDB Comment:  %s
CMDB Status:   %s
CMDB ID:       %s

""" % (system['name'],system_link,system['expiry_date'], system_status,system['vmware_os'],system['allocation_comment'],system['cmdb_description'],system['cmdb_environment'],system['cmdb_u_number'])

	helper.event('check_expire_mail', 'Sending warning e-mail for expired systems ')
	helper.lib.send_email("db2z07@soton.ac.uk", 'Systems expiration warning: ' + str(len(systems)) + ' system(s) will expire in the next 7 days', message)
	helper.end_event(description="Sent warning e-mail for expired systems")
