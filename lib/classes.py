#!/usr/bin/python

from flask import g
import MySQLdb as mysql

################################################################################

def get(name):
	"""Tries to return the class data from a given name/prefix"""

	cur = g.db.cursor(mysql.cursors.DictCursor)
	cur.execute("SELECT `name`, `digits`, `comment`, `disabled`, `lastid`, `link_vmware`, `cmdb_type` FROM `classes` WHERE `name` = %s", (name,))
	return cur.fetchone()

################################################################################

def list(hide_disabled = False):
	"""Returns the list of system classes in the database"""

	# Build the query
	query = "SELECT `name`, `digits`, `comment`, `disabled`, `lastid`, `link_vmware`, `cmdb_type` FROM `classes`";
	if hide_disabled:
		query = query + " WHERE `disabled` = False";

	query = query + " ORDER BY `lastid` DESC"

	# Query the database
	cur = g.db.cursor(mysql.cursors.DictCursor)
	cur.execute(query)

	# Return the results
	return cur.fetchall()

################################################################################
