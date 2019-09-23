
import MySQLdb as mysql
import sys, copy, os, re
from pyVmomi import vim
from datetime import datetime

# The days of the week as they can appear in the config
DAYS_OF_WEEK = ['MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY', 'SUNDAY']

# Quick helper function to return a default if a given string is None
def ordefault(s, default=""):
	return str(s) if s is not None and len(str(s).strip()) > 0 else str(default)

def uniqify(l, k):
	seen = set()
	return [d for d in l if d[k] not in seen and not seen.add(d[k])]

def run(helper, options):
	if 'SYSTEM_EXPIRE_NOTIFY_CONFIG' not in helper.config:
		helper.event('expire_notify_unconfigured', success=False, description='Missing configuration for VM expiry notification', oneshot=True)
		return

	# Connect to the database
	db = helper.db_connect()
	curd = db.cursor(mysql.cursors.DictCursor)

	# Get a list of all system names that expire in the future
	curd.execute('SELECT * FROM `systems_info_view` WHERE `expiry_date` > NOW() AND `vmware_vcenter` IS NOT NULL AND `vmware_uuid` IS NOT NULL')
	expiring_systems = curd.fetchall()

	# Iterate over the types of reports
	for report_id in helper.config['SYSTEM_EXPIRE_NOTIFY_CONFIG']:
		report_config = helper.config['SYSTEM_EXPIRE_NOTIFY_CONFIG'][report_id]
		helper.event('check_expire_count', 'Checking for systems due to expire for report ' + report_config['description'])

		# Compile the regex
		try:
			vm_re = re.compile(report_config['regex'])
		except Exception as e:
			helper.end_event(success=False, description='Invalid regex for report ' + str(report_id))
			continue

		# This maps e-mail address to system name
		email_system_map = {}

		# Iterate over all the systems
		system_count = 0
		email_count = 0
		for system in expiring_systems:
			# If the name matches the regex for the report
			if vm_re.match(system['name']) is not None:
				# Calculate in how many days the system expires
				expiry_days = (system['expiry_date'] - datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)).days

				# Config validation
				if type(report_config['when_days']) is not list:
					when_days = [report_config['when_days']]
				else:
					when_days = report_config['when_days']

				# Iterate over the when_days option to see if we should e-mail
				notify = False
				for days in when_days:
					# For positive integers of days, we notify if there are exactly that many days left
					# For negative integers of days, we notify if there are /less/ than that many days left
					if (days >= 0 and days == expiry_days) or (days < 0 and expiry_days <= -days):
						system_count = system_count + 1
						notify = True

				# If the weekly_days config option is specified, iterate over that to see if we
				# should be e-mailing on this day of the week. If we shouldn't, we override the
				# notify flag (as set above) to prevent the e-mail
				if 'weekly_on' in report_config:
					if type(report_config['weekly_on']) is not list:
						weekly_on = [report_config['weekly_on']]
					else:
						weekly_on = report_config['weekly_on']

					# Get the name of today as it would appear in the config
					today = DAYS_OF_WEEK[datetime.now().weekday()]

					# If the name of today doesn't appear in the config, then we shouldn't
					# be e-mailing today, so override notify
					if today not in weekly_on:
						notify = False

				# If we've decided that we should notify the user
				if notify:
					# Config validation
					if type(report_config['who']) is not list:
						recipients = [report_config['who']]
					else:
						recipients = report_config['who']

					# Figure out who it is that we actually need to e-mail
					for recipient in recipients:
						email = None
						if recipient == '@PRIMARY':
							# These could potentially be e-mails or usernames...
							if system['primary_owner_who'] is not None and len(system['primary_owner_who'].strip()) > 0:
								if '@' not in system['primary_owner_who']:
									email = system['primary_owner_who'].strip() + '@' + helper.config['EMAIL_DOMAIN']
								else:
									email = system['primary_owner_who'].strip()
						elif recipient == '@SECONDARY':
							# These could potentially be e-mails or usernames...
							if system['secondary_owner_who'] is not None and len(system['secondary_owner_who'].strip()) > 0:
								if '@' not in system['secondary_owner_who']:
									email = system['secondary_owner_who'].strip() + '@' + helper.config['EMAIL_DOMAIN']
								else:
									email = system['secondary_owner_who'].strip()
						elif recipient == '@ALLOCATOR':
							# This has to be username
							if system['allocation_who'] is not None and len(system['allocation_who'].strip()) > 0:
								email = system['allocation_who'].strip() + '@' + helper.config['EMAIL_DOMAIN']
						elif not recipient.startswith('@') and '@' in recipient:
							# Assume an e-mail address
							email = recipient

						# If we found an e-mail address, keep note of the system 
						if email is not None:
							if email in email_system_map:
								email_system_map[email].append(system)
							else:
								email_system_map[email] = [system]
							
		## We've determined what e-mails need to be sent notifications about which systems
		for email in email_system_map:
			email_count = email_count + 1

			if 'message_start' in report_config:
				message = report_config['message_start']
			else:
				message = ''

			# For each system that needs to be reported
			# (Sorting uniquely by ID)
			for system in uniqify(email_system_map[email], 'id'):
				# Get the live power status (rather than cached, so that we're 100% accurate)
				vm = helper.lib.vmware_get_vm_by_uuid(system['vmware_uuid'], system['vmware_vcenter'])
				system_status = "off"
				if vm.runtime.powerState == vim.VirtualMachine.PowerState.poweredOn:
					system_status = "on"

				expiry_days = (system['expiry_date'] - datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)).days
				system_link = 'https://' + helper.config['CORTEX_DOMAIN'] + '/systems/edit/' + str(system['id'])
				if system['cmdb_id'] is not None and len(system['cmdb_id'].strip()) > 0:
					cmdb_link = helper.config['CMDB_URL_FORMAT'] % system['cmdb_id']
				else:
					cmdb_link = "Not linked to ServiceNow"

				message = message + report_config['message_system'].format(allocator=ordefault(system['allocation_who']), primary_owner=ordefault(system['primary_owner_who']), secondary_owner=ordefault(system['secondary_owner_who']), name=ordefault(system['name']), description=ordefault(system['allocation_comment']), days_left=expiry_days, allocation_date=ordefault(system['allocation_date'].date(), 'Unknown'), expiry_date=system['expiry_date'].date(), os=ordefault(system['vmware_os'], 'Unknown OS'), link=system_link, power_status=ordefault(system_status), cmdb_description=ordefault(system['cmdb_description'], 'Not linked to ServiceNow'), cmdb_environment=ordefault(system['cmdb_environment'], 'Not linked to ServiceNow'), cmdb_operational_status=ordefault(system['cmdb_operational_status'], 'Not linked to ServiceNow'), cmdb_u_number=ordefault(system['cmdb_u_number'], 'Not linked to ServiceNow'), cmdb_link=cmdb_link)

			if 'message_end' in report_config:
				message = message + report_config['message_end']

			# Send the e-mail
			helper.lib.send_email(email, 'Systems expiration warning: ' + str(len(email_system_map[email])) + ' system(s) expiring soon', message)
				
		# End this report task
		helper.end_event(description='Report ' + report_config['description'] + ' found ' + str(system_count) + ' expiring system(s), generating ' + str(email_count) + ' e-mail(s)')

