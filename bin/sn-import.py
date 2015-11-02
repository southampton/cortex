#!/usr/bin/python

import requests
import MySQLdb as mysql
import sys, copy, os

print 'Reading config...'

# This is a minor safety net to prevent exec() from over-writing our 
# globals/locals (e.g. from replacing psycopg2 with something malicious)
g = copy.copy(globals())
l = copy.copy(locals())

# Try to load additional config from various paths (code adapted from Flask Config.from_pyfile)
for path in ['/etc/cortex.conf', '/etc/cortex/cortex.conf', '/data/cortex.conf', '/data/cortex/cortex.conf']:
        if os.path.isfile(path):
                with open(path) as file:
                        exec(file, g, l)

# Extract relevant details from exec'd code
SN_HOST    = l['SN_HOST']
SN_USER    = l['SN_USER']
SN_PASS    = l['SN_PASS']
MYSQL_HOST = l['MYSQL_HOST']
MYSQL_USER = l['MYSQL_USER']
MYSQL_PASS = l['MYSQL_PASS']
MYSQL_NAME = l['MYSQL_NAME']
MYSQL_PORT = l['MYSQL_PORT']

# A dictionary of CMDB hierarchy, mapping classes to their parent classes
PARENT_CLASSES={'cmdb_ci': None, 'cmdb_ci_server': 'cmdb_ci', 'cmdb_ci_win_server': 'cmdb_ci_server', 'cmdb_ci_linux_server': 'cmdb_ci_server', 'cmdb_ci_esx_server': 'cmdb_ci_server', 'cmdb_ci_solaris_server': 'cmdb_ci_server', 'cmdb_ci_osx_server': 'cmdb_ci_server'}

# Connect to the database
try:
	db = mysql.connect(host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER, passwd=MYSQL_PASS, db=MYSQL_NAME, charset='utf8')
except Exception as ex:
	sys.exit(1)

################################################################################

def download_choices(sn_element, sn_name):
	"""Downloads the choices for a given element (e.g. operational_status, 
	u_environment, etc.) for the given system class, sn_name."""

	# Make the request to the ServiceNow REST Table API
	r = requests.get('https://' + SN_HOST + '/api/now/v1/table/sys_choice?sysparm_query=element=' + sn_element + '^name=' + sn_name + '&sysparm_fields=value,label', auth=(SN_USER, SN_PASS), headers={'Accept': 'application/json'})

	# Get the JSON returned from ServiceNow
	data = r.json()

	# Iterate through the results, and create a dictionary mapping the 'values'
	# to their labels, e.g. 12 -> "In Service"
	return_value = {}
	if 'result' in data:
		for row in data['result']:
			if row['value'] not in return_value:
				return_value[row['value']] = row['label']

	return return_value

################################################################################

def resolve_choice(choices, value, sys_class_name):
	"""Resolves a choice by looking through the hierarchy of classes and locating 
	the first value."""

	# Start with no result
	result = None

	# Iterate until we find a result
	while result is None and sys_class_name is not None:
		# We've got this class name in our possible choices
		if sys_class_name in choices:
			# And we've got a result for this value in this class of choices
			if value in choices[sys_class_name]:
				# We've found the result
				result = choices[sys_class_name][value]
				break
			else:
				# Not found within the choices for this class, go to parent class
				if sys_class_name in PARENT_CLASSES:
					sys_class_name = PARENT_CLASSES[sys_class_name]
				else:
					# We don't have a parent, something has gone awry
					break
		else:
			# We don't have choices for this class, go to parent class
			if sys_class_name in PARENT_CLASSES:
				sys_class_name = PARENT_CLASSES[sys_class_name]
			else:
				# We don't have a parent, something has gone awry
				break

	# Return the result
	return result

################################################################################

def download_servers(cur, operational_statuses):
	"""Download information about the servers"""

	# Make the request 
	print "Downloading server data..."
	r = requests.get('https://' + SN_HOST + '/api/now/v1/table/cmdb_ci_server?sysparm_fields=sys_id,sys_class_name,operational_status,u_number,name,short_description', auth=(SN_USER, SN_PASS), headers={'Accept': 'application/json'})

	# Get the JSON returned from ServiceNow
	data = r.json()

	# Delete all the server CIs from the table (we must do this before we delete 
	# from the choices tables as there is a foreign key constraint)
	print "Clearing local ServiceNow CMDB Cache Table..."
	cur.execute('DELETE FROM `sncache_cmdb_ci`;')

	# Iterate over the results
	print "Creating database entries..."
	for row in data['result']:
		# Resolve the value of 'operational_status' to it's display label
		operational_status = resolve_choice(operational_statuses, row['operational_status'], row['sys_class_name'])

		print row
		# Insert the information in to the database
		cur.execute('INSERT INTO `sncache_cmdb_ci` (`sys_id`, `sys_class_name`, `name`, `operational_status`, `u_number`, `short_description`) VALUES (%s, %s, %s, %s, %s, %s)', (row['sys_id'], row['sys_class_name'], row['name'], operational_status, row['u_number'], row['short_description']))

	print "Imported " + str(len(data['result'])) + " records"

# Get a cursor to the database
cur = db.cursor(mysql.cursors.DictCursor)

# Download the choices for the operational_status parameter from ServiceNow
operational_statuses = {}
for sys_class_name in PARENT_CLASSES:
	print "Downloading operational_status choices for " + str(sys_class_name) + "..."
	operational_statuses[sys_class_name] = download_choices('operational_status', sys_class_name)

# Download the servers
download_servers(cur, operational_statuses)

# Commit our changes
print "Committing changes..."
db.commit()

