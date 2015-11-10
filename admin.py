#!/usr/bin/python
#

from cortex import app
import cortex.core
from flask import Flask, request, session, redirect, url_for, flash, g, abort, render_template
import re
import MySQLdb as mysql

################################################################################

def get_class(name):
	"""Tries to return the class data from a given name/prefix"""
	cur = g.db.cursor(mysql.cursors.DictCursor)
	cur.execute("SELECT * FROM `classes` WHERE `name` = %s",(name))
	return cur.fetchone()

################################################################################

def get_classes(hide_disabled = False):
	"""Returns the list of system classes in the database"""

	# Build the query
	query = "SELECT `name`, `digits`, `comment`, `disabled`, `lastid` FROM `classes`";
	if hide_disabled:
		query = query + " WHERE `disabled` = False";

	query = query + " ORDER BY `lastid` DESC"

	# Query the database
	cur = g.db.cursor(mysql.cursors.DictCursor)
	cur.execute(query)

	# Return the results
	return cur.fetchall()

################################################################################

@app.route('/admin/tasks')
def admin_tasks():
	"""Displays the list of tasks to the user."""

	# Get all the tasks from the database
	cur = g.db.cursor(mysql.cursors.DictCursor)
	cur.execute("SELECT `id`, `module`, `username`, `start`, `end`, `status` FROM `tasks`")
	tasks = cur.fetchall()

	# Render the page
	return render_template('admin-tasks.html', tasks=tasks)

################################################################################

@app.route('/admin/classes', methods=['GET', 'POST'])
def admin_classes():
	"""Handles the content of the Admin -> Classes page"""

	# On a GET request, display the list of classes page
	if request.method == 'GET':
		classes = get_classes(hide_disabled=False)
		return render_template('admin-classes.html', classes=classes)

	elif request.method == 'POST':
		action = request.form['action']
		cur    = g.db.cursor()

		if action in ['add_class','edit_class']:		
			# Validate class name/prefix
			class_name   = request.form['class_name']
			if not re.match(r'^[a-z]{1,16}$',class_name):
				flash("The class prefix you sent was invalid. It can only contain lowercase letters and be at least 1 character long and at most 16","alert-danger")
				return redirect(url_for('admin_classes'))

			# Validate number of digits in hostname/server name
			try:
				class_digits = int(request.form['class_digits'])
			except ValueError:
				flash("The class digits you sent was invalid (it was not a number)." + str(type(class_digits)),"alert-danger")
				return redirect(url_for('admin_classes'))

			if class_digits < 1 or class_digits > 10:
				flash("The class digits you sent was invalid. It must be between 1 and 10.","alert-danger")
				return redirect(url_for('admin_classes'))

			# Extract whether the new class is active
			if "class_active" in request.form:
				class_disabled = 0
			else:
				class_disabled = 1

			# Validate the comment for the class
			class_comment = request.form['class_comment']
			if not re.match(r'^.{3,512}$',class_comment):
				flash("The class comment you sent was invalid. It must be between 3 and 512 characters long.","alert-danger")
				return redirect(url_for('admin_classes'))

			## Check if the class already exists
			cur.execute('SELECT 1 FROM `classes` WHERE `name` = %s;', (class_name))
			if cur.fetchone() is None:
				class_exists = False
			else:
				class_exists = True

			if action == 'add_class':
				if class_exists:
					flash('A system class already exists with that prefix', 'alert-danger')
					return redirect(url_for('admin_classes'))

				## sql insert
				cur.execute('''INSERT INTO `classes` (`name`, `digits`, `comment`, `disabled`) VALUES (%s, %s, %s)''', (class_name, class_digits, class_comment, class_disabled))
				g.db.commit()

				flash("System class created","alert-success")
				return redirect(url_for('admin_classes'))							
			

			elif action == 'edit_class':
				if not class_exists:
					flash('No system class matching that name/prefix could be found', 'alert-danger')
					return redirect(url_for('admin_classes'))

				cur.execute('''UPDATE `classes` SET `digits` = %s, disabled = %s, comment = %s WHERE `name` = %s''', (class_digits, class_disabled, class_comment, class_name))
				g.db.commit()

				flash("System class updated","alert-success")
				return redirect(url_for('admin_classes'))

				## Save changes to an existing class
				return
