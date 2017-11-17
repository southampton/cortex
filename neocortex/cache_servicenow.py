#!/usr/bin/python

import requests
import MySQLdb as mysql
import sys, copy, os

def run(helper, options):
	# Connect to the database
	db = helper.db_connect()
	curd = db.cursor(mysql.cursors.DictCursor)

	# Initialise data dictionary
	data = {}

	# Download each of the configured tables
	for table in helper.config['CMDB_CACHED_CLASSES']:
		# Start event
		helper.event('servicenow_download_ci', 'Downloading "' + helper.config['CMDB_CACHED_CLASSES'][table] + '" data from ServiceNow instance ' + helper.config['SN_HOST'])	

		# Make the request to download all CI data using the table API, which can
		# be limited to certain fields, and can resolve both choice value and
		# choice label
		r = requests.get('https://' + helper.config['SN_HOST'] + '/api/now/table/' + table + '?sysparm_fields=sys_id,sys_class_name,operational_status,u_number,name,short_description,u_environment,virtual,comments,os&sysparm_display_value=all', auth=(helper.config['SN_USER'], helper.config['SN_PASS']), headers={'Accept': 'application/json'})

		# Get the JSON returned from ServiceNow
		data[table] = r.json()

		# End event
		helper.end_event(description='Downloaded "' + helper.config['CMDB_CACHED_CLASSES'][table] + '" data from ServiceNow')

	helper.event('delete_cache', 'Deleting existing cache')

	# Delete all the server CIs from the table (we must do this before we delete 
	# from the choices tables as there is a foreign key constraint)
	curd.execute('DELETE FROM `sncache_cmdb_ci`;')

	helper.end_event(description="Deleted existing cache")

	helper.event('servicenow_cache_ci', 'Caching ServiceNow CMDB data')

	# Iterate over the results
	total_records = 0
	failed_records = 0
	for table in data:
		total_records = total_records + len(data[table]['result'])
		for row in data[table]['result']:
			virtual = False
			if 'virtual' in row and row['virtual'] is not None and 'value' in row['virtual']:
				if row['virtual']['value'] == 'true':
					virtual = True

			# Handle things that aren't common to everything
			if 'u_environment' not in row:
				row['u_environment'] = {'display_value': None, 'value': None}
			else:
				if 'display_value' not in row['u_environment']:
					row['u_environment']['display_value'] = None
			if 'os' not in row:
				row['os'] = {'display_value': None, 'value': None}
			else:
				if 'display_value' not in row['os']:
					row['os']['display_value'] = None

			# Insert the information in to the database
			try:
				curd.execute('INSERT INTO `sncache_cmdb_ci` (`sys_id`, `sys_class_name`, `name`, `operational_status`, `u_number`, `short_description`, `u_environment`, `virtual`, `comments`, `os`) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)', (row['sys_id']['display_value'], row['sys_class_name']['display_value'], row['name']['display_value'], row['operational_status']['display_value'], row['u_number']['display_value'], row['short_description']['display_value'], row['u_environment']['display_value'], virtual, row['comments']['display_value'], row['os']['display_value']))
			except Exception as e:
				failed_records = failed_records + 1
				pass

	if failed_records == 0:
		helper.end_event(description='Cached ' + str(total_records) + ' records')
	else:
		helper.end_event(description='Cached ' + str(total_records - failed_records) + ' out of ' + str(total_records) + ' records', success=False)

	# Commit to database
	helper.event('servicenow_cache_ci', 'Saving cache to disk')
	db.commit()
	helper.end_event(description='Saved cache to disk')


