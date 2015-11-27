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

# Connect to the database
try:
	db = mysql.connect(host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER, passwd=MYSQL_PASS, db=MYSQL_NAME, charset='utf8')
except Exception as ex:
	sys.exit(1)

# Get a cursor to the database
cur = db.cursor(mysql.cursors.DictCursor)

# Make the request to download all CI data using the JSONv2 API (which allows
# the resolving of choice value to choice label using the displayvalue=true
# parameter)
print "Downloading server data..."
r = requests.get('https://' + SN_HOST + '/cmdb_ci_server.do?JSONv2&sysparm_fields=sys_id,sys_class_name,operational_status,u_number,name,short_description&displayvalue=true', auth=(SN_USER, SN_PASS), headers={'Accept': 'application/json'})

# Get the JSON returned from ServiceNow
data = r.json()

# Delete all the server CIs from the table (we must do this before we delete 
# from the choices tables as there is a foreign key constraint)
print "Clearing local ServiceNow CMDB Cache Table..."
cur.execute('DELETE FROM `sncache_cmdb_ci`;')

# Iterate over the results
print "Creating database entries..."
for row in data['records']:
	# Insert the information in to the database
	cur.execute('INSERT INTO `sncache_cmdb_ci` (`sys_id`, `sys_class_name`, `name`, `operational_status`, `u_number`, `short_description`) VALUES (%s, %s, %s, %s, %s, %s)', (row['sys_id'], row['sys_class_name'], row['name'], row['operational_status'], row['u_number'], row['short_description']))

print "Imported " + str(len(data['records'])) + " records"

# Commit our changes
print "Committing changes..."
db.commit()

