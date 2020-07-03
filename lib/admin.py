
import json

import MySQLdb as mysql
from flask import g


def get_kv_setting(key, load_as_json=False):
	"""
	Selects a kv_setting row from the kv_setting table.
	"""

	# Create a cursor.
	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute('SELECT `value` FROM `kv_settings` WHERE `key`=%s;',(key,))
	res = curd.fetchone()

	# Do we want to load the value as JSON data.
	if load_as_json:
		if res is not None:
			return json.loads(res['value'])
		else:
			return {}
	else:
		return res['value']

def set_kv_setting(key, value, on_duplicate_update=True, with_commit=True):
	"""
	Inserts a key and value pair into the DB.
	Will update the value if on_duplicate_update is set to True.
	Will commit after the insert statement if with_commit is set to True.
	"""

	# Create a cursor.
	curd = g.db.cursor(mysql.cursors.DictCursor)

	query = 'INSERT INTO `kv_settings` (`key`, `value`) VALUES (%s, %s)'
	params = (key, value,)
	if on_duplicate_update:
		query = query + 'ON DUPLICATE KEY UPDATE `value`=%s'
		params = params + (value,)

	curd.execute(query, params)

	if with_commit:
		g.db.commit()
