#!/usr/bin/python

from urllib.parse import urljoin
import requests
import time
import MySQLdb as mysql
from datetime import datetime
import json

def run(helper, options):

	user = helper.username
	time = datetime.now().time()

	# Set up cursor to access the DB
	curd = helper.db.cursor(mysql.cursors.DictCursor)

	# lock the table in read mode
	helper.event('get_current_status', 'Getting the current status of workflows')
	curd.execute('LOCK TABLES `kv_settings` READ;')
	curd.execute('SELECT `value` FROM `kv_settings` WHERE `key`=%s;',('workflow_lock_status',))
	current_value = curd.fetchone()

	# unlock the table once run
	curd.execute('UNLOCK TABLES;')
	
	if current_value is None:
		current_status = 'Unlocked'
	else:
		try:
			jsonobj = json.loads(current_value['value'])
			if 'status' not in jsonobj:
				current_status = 'Unlocked'
			else:
				current_status = jsonobj['status']
		except Exception as e:
			current_status = 'Locked'

	# get the new value to set the table to
	helper.end_event(description="Status is " + current_status)
	key = 'workflow_lock_status'

	newValue = 'Locked' if current_status == 'Unlocked' else 'Unlocked'
	value = json.dumps({'username': helper.username, 'time': str(time), 'status': newValue})

	# setting new status 
	helper.event('set_new_status', 'Setting new status')
	query = 'INSERT INTO `kv_settings` (`key`, `value`) VALUES (%s, %s)'
	params = (key, value,)
	query = query + 'ON DUPLICATE KEY UPDATE `value` = %s'
	params = params + (value,)

	# lock table in read mode
	curd.execute('LOCK TABLES `kv_settings` WRITE;')
	curd.execute(query, params)
	curd.execute('UNLOCK TABLES ;')

	# commit changes
	helper.event('commit_changes', 'Committing changes')
	helper.db.commit()	
	helper.end_event(description="Commiting Changes")
