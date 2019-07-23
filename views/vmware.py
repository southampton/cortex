#!/usr/bin/python
from cortex import app
from cortex.lib.user import does_user_have_permission
import cortex.lib.vmware
import cortex.lib.core
from flask import Flask, request, session, redirect, url_for, flash, g, render_template, jsonify, Response, abort
import os
import time
import json
import re
import werkzeug
import csv
import io
import MySQLdb as mysql
from collections import OrderedDict

################################################################################

@app.route('/vmware/os')
@cortex.lib.user.login_required
def vmware_os():
	"""Shows VM operating system statistics."""

	# Check user permissions
	if not does_user_have_permission("vmware.view"):
		abort(403)

	types = cortex.lib.vmware.get_os_stats()

	# Render
	return render_template('vmware/os.html', active='vmware', types=types, title="Statistics - Operating Systems")

################################################################################

@app.route('/vmware/hw-tools')
@cortex.lib.user.login_required
def vmware_hwtools():
	"""Shows VM related graphs"""

	# Check user permissions
	if not does_user_have_permission("vmware.view"):
		abort(403)

	# Get a cursor to the database
	curd = g.db.cursor(mysql.cursors.DictCursor)

	# Get OS statistics
	curd.execute('SELECT `hwVersion`, COUNT(*) AS `count` FROM `vmware_cache_vm` GROUP BY `hwVersion` ORDER BY `hwVersion`')
	stats_hw = curd.fetchall()

	# Shows VM hardware power state statistics.

	# Get a cursor to the database
	curd = g.db.cursor(mysql.cursors.DictCursor)

	# Get the power statistics
	curd.execute('SELECT `powerState`, COUNT(*) AS `count` FROM `vmware_cache_vm` GROUP BY `powerState` ORDER BY `powerState`')
	stats_power = curd.fetchall()

	#Shows VM tools statistics.

	# Get a cursor to the database
	curd = g.db.cursor(mysql.cursors.DictCursor)

	# Get tools statistics
	curd.execute('SELECT `toolsRunningStatus`, COUNT(*) AS `count` FROM `vmware_cache_vm` WHERE `powerState` = "poweredOn" GROUP BY `toolsRunningStatus` ORDER BY `toolsRunningStatus`')
	stats_status = curd.fetchall()
	curd.execute('SELECT `toolsVersionStatus`, COUNT(*) AS `count` FROM `vmware_cache_vm` WHERE `powerState` = "poweredOn" GROUP BY `toolsVersionStatus` ORDER BY `toolsVersionStatus`')
	stats_version = curd.fetchall()

	# Render
	return render_template('vmware/hwtools.html', active='vmware', stats_hw=stats_hw, stats_power=stats_power,stats_status=stats_status, stats_version=stats_version, title="Statistics")

################################################################################

@app.route('/vmware/specs')
@cortex.lib.user.login_required
def vmware_specs():
	"""Shows VM hardware spec statistics."""

	# Check user permissions
	if not does_user_have_permission("vmware.view"):
		abort(403)

	# Get a cursor to the database
	curd = g.db.cursor(mysql.cursors.DictCursor)

	# Get CPU and RAM statistics
	curd.execute('SELECT `memoryMB`, `numCPU` FROM `vmware_cache_vm`')
	results = curd.fetchall()

	# The list of entries for our RAM histogram
	data_ram = OrderedDict([
		('Less than 1GB', 0),
		('1GB', 0),
		('2GB', 0),
		('3GB', 0),
		('4GB', 0),
		('6GB', 0),
		('8GB', 0),
		('12GB', 0),
		('16GB', 0),
		('24GB', 0),
		('32GB', 0),
		('48GB', 0),
		('64GB', 0),
		('Other', 0),
	])

	# The list of entries for our CPU histogram
	data_cpu = {
		1: 0,
		2: 0,
		4: 0,
		8: 0,
		16: 0,
		'Other': 0,
	}

	for vm in results:
		vm['memoryMB'] = int(vm['memoryMB'])

		# Add the VM to the memory histogram
		if vm['memoryMB'] < 1024:
			data_ram['Less than 1GB'] += 1
		elif vm['memoryMB'] == 1024:
			data_ram['1GB'] += 1
		elif vm['memoryMB'] == 2048:
			data_ram['2GB'] += 1
		elif vm['memoryMB'] == 3072:
			data_ram['3GB'] += 1
		elif vm['memoryMB'] == 4096:
			data_ram['4GB'] += 1
		elif vm['memoryMB'] == 6144:
			data_ram['6GB'] += 1
		elif vm['memoryMB'] == 8192:
			data_ram['8GB'] += 1
		elif vm['memoryMB'] == 12288:
			data_ram['12GB'] += 1
		elif vm['memoryMB'] == 16384:
			data_ram['16GB'] += 1
		elif vm['memoryMB'] == 24576:
			data_ram['24GB'] += 1
		elif vm['memoryMB'] == 32768:
			data_ram['32GB'] += 1
		elif vm['memoryMB'] == 49152:
			data_ram['48GB'] += 1
		elif vm['memoryMB'] == 65536:
			data_ram['64GB'] += 1
		else:
			data_ram['Other'] += 1

		# Add the VM to the CPU histogram
		try:
			data_cpu[int(vm['numCPU'])] += 1
		except KeyError as ex:
			data_cpu['Other'] += 1

	return render_template('vmware/specs.html', active='vmware', stats_ram=data_ram, stats_cpu=data_cpu, title="Statistics - VM Specs")

################################################################################

@app.route('/vmware/data')
@cortex.lib.user.login_required
def vmware_data():
	"""Displays page containing a giant table of information of everything
	we know about all the VMs."""

	# Check user permissions
	if not does_user_have_permission("vmware.view"):
		abort(403)

	# Get a cursor to the database
	curd = g.db.cursor(mysql.cursors.DictCursor)

	# Get all the information about every VM
	curd.execute('SELECT * FROM `vmware_cache_vm` WHERE `template` = 0 ORDER BY `name`')
	results = curd.fetchall()

	# Render
	return render_template('vmware/data.html', active='vmware', data=results, title="VMware Data")

################################################################################

@app.route('/vmware/clusters')
@cortex.lib.user.login_required
def vmware_clusters():
	# Check user permissions
	if not does_user_have_permission("vmware.view"):
		abort(403)

	# Get a cursor to the database
	curd = g.db.cursor(mysql.cursors.DictCursor)

	# Generate statistics about the clusters
	curd.execute('SELECT `b`.`name`, `b`.`vcenter`, `b`.`hosts`, `a`.`vm_count`, (`b`.`ram_usage` * 1048576) AS `ram_usage`, (`a`.`assigned_ram` * 1048576) AS `assigned_ram`, `b`.`ram` AS `total_ram`, `a`.`assigned_cores`, `b`.`cores` AS `total_cores`, `b`.`cpu_usage` AS `cpu_usage_mhz`, ROUND(`b`.`cpuhz` / 1000) AS `total_mhz` FROM (SELECT `cluster`, `vcenter`, COUNT(*) AS `vm_count`, SUM(`numCPU`) AS `assigned_cores`, SUM(`memoryMB`) AS `assigned_ram` FROM `vmware_cache_vm` WHERE `cluster` != "None" group by `cluster`) `a` RIGHT JOIN `vmware_cache_clusters` `b` ON `a`.`cluster` = `b`.`name`')

	# Take the above query and group it by vCenter
	vcenters = {}
	row = curd.fetchone()
	while row is not None:
		# If this is the first time we've seen a vCenter, create a new array
		if row['vcenter'] not in vcenters:
			vcenters[row['vcenter']] = []

		# Deal with Nones (which can appear if there are no hosts or VMs on a cluster)
		for key in ['ram_usage', 'assigned_ram', 'total_ram', 'assigned_cores', 'total_cores', 'cpu_usage_mhz', 'total_mhz', 'vm_count']:
			if row[key] is None:
				row[key] = 0

		# Add a row to the array
		vcenters[row['vcenter']].append(row)

		# Iterate to next cluster
		row = curd.fetchone()

	# Render
	return render_template('vmware/clusters.html', active='vmware', vcenters=vcenters, title="VMware Clusters")

################################################################################

@app.route('/vmware/history')
@cortex.lib.user.login_required
def vmware_history():
	# Check user permissions
	if not does_user_have_permission("vmware.view"):
		abort(403)

	# Get a cursor to the database
	curd = g.db.cursor(mysql.cursors.DictCursor)

	# Figure out how many days to show
	if 'd' in request.args:
		d = int(request.args['d'])
	else:
		d = 14

	# Get VM count history
	curd.execute('SELECT `timestamp`, `value` FROM `stats_vm_count` WHERE `timestamp` > DATE_SUB(NOW(), INTERVAL ' + str(d) + ' DAY) ORDER BY `timestamp` DESC')
	stats_vms = curd.fetchall()

	# Get Linux VM count history
	curd.execute('SELECT `timestamp`, `value` FROM `stats_linux_vm_count` WHERE `timestamp` > DATE_SUB(NOW(), INTERVAL ' + str(d) + ' DAY) ORDER BY `timestamp` DESC')
	stats_linux_vms = curd.fetchall()

	# Get Windows VM count history
	curd.execute('SELECT `timestamp`, `value` FROM `stats_windows_vm_count` WHERE `timestamp` > DATE_SUB(NOW(), INTERVAL ' + str(d) + ' DAY) ORDER BY `timestamp` DESC')
	stats_windows_vms = curd.fetchall()

	# Get Desktop VM count history
	curd.execute('SELECT `timestamp`, `value` FROM `stats_desktop_vm_count` WHERE `timestamp` > DATE_SUB(NOW(), INTERVAL ' + str(d) + ' DAY) ORDER BY `timestamp` DESC')
	stats_desktop_vms = curd.fetchall()

	# Render
	return render_template('vmware/history.html', active='vmware', stats_vms=stats_vms, stats_linux_vms=stats_linux_vms, stats_windows_vms=stats_windows_vms, stats_desktop_vms=stats_desktop_vms, title='VMware History', d=d)

################################################################################

def vmware_csv_stream(cursor):
	"""Streams data from each row in the cursor as a line of CSV."""

	# Get the first row
	row = cursor.fetchone()

	# Write CSV header
	output = io.StringIO()
	writer = csv.writer(output)
	writer.writerow(['Name', 'Cluster/Host', 'Annotation', 'Power State', 'IP Address', 'Operating System', 'vCPUs', 'RAM (MeB)', 'H/W Version', 'Tools State', 'Tools Version'])
	yield output.getvalue()

	# Write data
	while row is not None:
		# There's no way to flush (and empty) a CSV writer, so we create
		# a new one each time
		output = io.StringIO()
		writer = csv.writer(output)

		# Generate output row
		outrow = [row['name'], row['cluster'], row['annotation'], row['powerState'], row['ipaddr'], row['guestFullName'], row['numCPU'], row['memoryMB'], row['hwVersion'], row['toolsRunningStatus'], row['toolsVersionStatus']]

		# Write the output row to the stream
		writer.writerow(outrow)
		yield output.getvalue()

		# Iterate
		row = cursor.fetchone()

################################################################################

@app.route('/vmware/download/csv')
@cortex.lib.user.login_required
def vmware_download_csv():
	"""Downloads the VMware data as a CSV file."""

	# Check user permissions
	if not does_user_have_permission("vmware.view"):
		abort(403)

	# Get the list of systems
	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute('SELECT * FROM `vmware_cache_vm` ORDER BY `name`')

	cortex.lib.core.log(__name__, "vmware.csv.download", "CSV of vmware data downloaded")
	# Return the response
	return Response(vmware_csv_stream(curd), mimetype="text/csv", headers={'Content-Disposition': 'attachment; filename="vmware.csv"'})

################################################################################

@app.route('/vmware/unlinked')
@cortex.lib.user.login_required
def vmware_data_unlinked():
	"""Displays page containing a giant table of information of everything
	we know about VMs which are not linked to Cortex system records. It is 
	currently hard coded to exclude virtual machines on the ECS cluster."""

	# Check user permissions
	if not does_user_have_permission("vmware.view"):
		abort(403)

	# Get a cursor to the database
	curd = g.db.cursor(mysql.cursors.DictCursor)

	# Get all the information about every VM
	curd.execute('SELECT * FROM `vmware_cache_vm` WHERE `template` = 0 AND `cluster` != "ORANGE_ECS_TIDT" AND `uuid` NOT IN (SELECT `vmware_uuid` FROM `systems` WHERE `vmware_uuid` IS NOT NULL) ORDER BY `name`')
	results = curd.fetchall()

	# Render
	return render_template('vmware/unlinked.html', active='vmware', data=results, title="Unlinked VMs")
