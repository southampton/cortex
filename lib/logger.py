#!/usr/bin/python
from flask import g, session
import MySQLdb as mysql

def log(source, desc, username=None):
	if username is None:
		username = session['username']
	try:
		cur = g.db.cursor()
		stmt = 'INSERT INTO `log` (`time`, `username`, `source`, `desc`) VALUES (NOW(), %s, %s, %s)'
		params = (username, source, desc)
		cur.execute(stmt, params)
		g.db.commit()
		return True
	except Exception as e:
		return False
