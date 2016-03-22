#!/usr/bin/python
#

from cortex import app
import cortex.lib.user
from flask import Flask, request, session, redirect, url_for, flash, g, render_template, jsonify, Response
import os 
import time
import json
import re
import werkzeug
import csv
import io
import MySQLdb as mysql

################################################################################

def get_os_stats():
	# Get a cursor to the database
	curd = g.db.cursor(mysql.cursors.DictCursor)

	# Get OS IDs for all virtual machines
	curd.execute('SELECT `guestId` FROM `vmware_cache_vm`')
	results = curd.fetchall()

	types = {}
	types['windows'] = 0
	types['linux']   = 0
	types['bsd']     = 0

	types['windows_desktop'] = 0
	types['windows_server']  = 0
	types['ws2003']          = 0
	types['ws2008']          = 0
	types['ws2012']          = 0
	types['ws2016']          = 0

	types['wdvista'] = 0
	types['wd7']     = 0
	types['wd8']     = 0
	types['wd10']    = 0

	types['ubuntu']      = 0
	types['debian']      = 0
	types['rhel']        = 0
	types['rhel3']       = 0
	types['rhel4']       = 0
	types['rhel5']       = 0
	types['rhel6']       = 0
	types['rhel7']       = 0
	types['linux_other'] = 0

	for result in results:
		ostr = result['guestId']

		if 'win' in ostr:
			types['windows'] += 1

			if 'winLonghornGuest' in ostr or 'winLonghorn64Guest' in ostr:
				types['windows_desktop'] += 1
				types['wdvista'] += 1

			elif 'windows7Guest' in ostr or 'windows7_64Guest' in ostr:
				types['windows_desktop'] += 1
				types['wd7'] += 1

			elif 'windows8Guest' in ostr or 'windows8_64Guest' in ostr:
				types['windows_desktop'] += 1
				types['wd8'] += 1

			elif 'windows9Guest' in ostr or 'windows9_64Guest' in ostr:
				types['windows_desktop'] += 1
				types['wd10'] += 1

			else:
				types['windows_server'] += 1

				if 'winNet' in ostr:
					types['ws2003'] += 1

				elif 'windows7Server' in ostr:        
					types['ws2008'] += 1

				elif 'windows8Server' in ostr:
					types['ws2012'] += 1

				elif 'windows9Server' in ostr:
					types['ws2016'] += 1

		elif "Linux" in ostr or 'linux' in ostr or 'rhel' in ostr or 'sles' in ostr or 'ubuntu' in ostr or 'centos' in ostr or 'debian' in ostr:
			types['linux'] += 1

			if 'ubuntu'   in ostr: types['ubuntu'] += 1
			elif 'debian' in ostr: types['debian'] += 1
			elif 'rhel' in ostr:
				types['rhel'] += 1
				
				if 'rhel3'   in ostr: types['rhel3'] += 1
				elif 'rhel4' in ostr: types['rhel4'] += 1
				elif 'rhel5' in ostr: types['rhel5'] += 1
				elif 'rhel6' in ostr: types['rhel6'] += 1
				elif 'rhel7' in ostr: types['rhel7'] += 1
				elif 'rhel8' in ostr: types['rhel8'] += 1

			else:
				types['linux_other'] += 1	

		elif "freebsd" in ostr:
			types['bsd'] += 1

	return types

################################################################################

@app.route('/vmware/os')
@cortex.lib.user.login_required
def vmware_os():
	"""Shows VM operating system statistics."""
	types = get_os_stats()

	# Render
	return render_template('vmware-os.html', active='vmware', types=types, title="Statistics - Operating Systems")

################################################################################

@app.route('/vmware/hardware')
@cortex.lib.user.login_required
def vmware_hw():
	"""Shows VM hardware version statistics."""

	# Get a cursor to the database
	curd = g.db.cursor(mysql.cursors.DictCursor)

	# Get OS statistics
	curd.execute('SELECT `hwVersion`, COUNT(*) AS `count` FROM `vmware_cache_vm` GROUP BY `hwVersion` ORDER BY `hwVersion`')
	results = curd.fetchall()

	# Render
	return render_template('vmware-hw.html', active='vmware', stats_hw=results, title="Statistics - Hardware Version")

################################################################################

@app.route('/vmware/power')
@cortex.lib.user.login_required
def vmware_power():
	"""Shows VM hardware power state statistics."""

	# Get a cursor to the database
	curd = g.db.cursor(mysql.cursors.DictCursor)

	# Get the power statistics
	curd.execute('SELECT `powerState`, COUNT(*) AS `count` FROM `vmware_cache_vm` GROUP BY `powerState` ORDER BY `powerState`')
	results = curd.fetchall()

	# Render
	return render_template('vmware-power.html', active='vmware', stats_power=results, title="Statistics - VM Power State")

################################################################################

@app.route('/vmware/tools')
@cortex.lib.user.login_required
def vmware_tools():
	"""Shows VM tools statistics."""

	# Get a cursor to the database
	curd = g.db.cursor(mysql.cursors.DictCursor)

	# Get tools statistics
	curd.execute('SELECT `toolsRunningStatus`, COUNT(*) AS `count` FROM `vmware_cache_vm` WHERE `powerState` = "poweredOn" GROUP BY `toolsRunningStatus` ORDER BY `toolsRunningStatus`')
	stats_status = curd.fetchall()
	curd.execute('SELECT `toolsVersionStatus`, COUNT(*) AS `count` FROM `vmware_cache_vm` WHERE `powerState` = "poweredOn" GROUP BY `toolsVersionStatus` ORDER BY `toolsVersionStatus`')
	stats_version = curd.fetchall()

	# Render
	return render_template('vmware-tools.html', active='vmware', stats_status=stats_status, stats_version=stats_version, title="Statistics - VMware Tools")

################################################################################

@app.route('/vmware/specs')
@cortex.lib.user.login_required
def vmware_specs():
	"""Shows VM hardware spec statistics."""

	# Get a cursor to the database
	curd = g.db.cursor(mysql.cursors.DictCursor)

	# Get CPU and RAM statistics
	curd.execute('SELECT `memoryMB`, `numCPU` FROM `vmware_cache_vm`')
	results = curd.fetchall()

	# The list of entries for our RAM histogram
	data_ram = {
		'Less than 1GB': 0,
		'1GB': 0,
		'2GB': 0,
		'3GB': 0,
		'4GB': 0,
		'6GB': 0,
		'8GB': 0,
		'12GB': 0,
		'16GB': 0,
		'24GB': 0,
		'32GB': 0,
		'48GB': 0,
		'64GB': 0,
		'Other': 0,
	}

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
			
	return render_template('vmware-specs.html', active='vmware', stats_ram=data_ram, stats_cpu=data_cpu, title="Statistics - VM Specs")

################################################################################

@app.route('/vmware/data')
@cortex.lib.user.login_required
def vmware_data():
	"""Displays page containing a giant table of information of everything
	we know about all the VMs."""

	# Get a cursor to the database
	curd = g.db.cursor(mysql.cursors.DictCursor)

	# Get all the information about every VM
	curd.execute('SELECT * FROM `vmware_cache_vm` WHERE `template` = 0 ORDER BY `name`')
	results = curd.fetchall()

	# Render
	return render_template('vmware-data.html', active='vmware', data=results, title="VMware Data")

################################################################################

@app.route('/vmware/clusters')
@cortex.lib.user.login_required
def vmware_clusters():
	# Get a cursor to the database
	curd = g.db.cursor(mysql.cursors.DictCursor)

	# Generate statistics about the clusters
	curd.execute('SELECT `a`.`cluster`, `a`.`vcenter`, `b`.`hosts`, `a`.`vm_count`, (`b`.`ram_usage` * 1048576) AS `ram_usage`, (`a`.`assigned_ram` * 1048576) AS `assigned_ram`, `b`.`ram` AS `total_ram`, `a`.`assigned_cores`, `b`.`cores` AS `total_cores`, `b`.`cpu_usage` AS `cpu_usage_mhz`, ROUND(`b`.`cpuhz` / 1000) AS `total_mhz` FROM (SELECT `cluster`, `vcenter`, COUNT(*) AS `vm_count`, SUM(`numCPU`) AS `assigned_cores`, SUM(`memoryMB`) AS `assigned_ram` FROM `vmware_cache_vm` WHERE `cluster` != "None" group by `cluster`) `a` JOIN `vmware_cache_clusters` `b` ON `a`.`cluster` = `b`.`name`;')

	# Take the above query and group it by vCenter
	vcenters = {}
	row = curd.fetchone()
	while row is not None:
		# If this is the first time we've seen a vCenter, create a new array
		if row['vcenter'] not in vcenters:
			vcenters[row['vcenter']] = []

		# Add a row to the array
		vcenters[row['vcenter']].append(row)

		# Iterate to next cluster
		row = curd.fetchone()

	# Render
	return render_template('vmware-clusters.html', active='vmware', vcenters=vcenters, title="VMware Clusters")

################################################################################

def vmware_csv_stream(cursor):
	"""Streams data from each row in the cursor as a line of CSV."""

	# Get the first row
	row = cursor.fetchone()

	# Write CSV header
	output = io.BytesIO()
	writer = csv.writer(output)
	writer.writerow(['Name', 'Cluster/Host', 'Annotation', 'Power State', 'IP Address', 'Operating System', 'vCPUs', 'RAM (MeB)', 'H/W Version', 'Tools State', 'Tools Version'])
	yield output.getvalue()

	# Write data
	while row is not None:
		# There's no way to flush (and empty) a CSV writer, so we create
		# a new one each time
		output = io.BytesIO()
		writer = csv.writer(output)

		# Write a row to the CSV output
		writer.writerow([row['name'], row['cluster'], row['annotation'], row['powerState'], row['ipaddr'], row['guestFullName'], row['numCPU'], row['memoryMB'], row['hwVersion'], row['toolsRunningStatus'], row['toolsVersionStatus']])
		yield output.getvalue()

		# Iterate
		row = cursor.fetchone()

################################################################################

@app.route('/vmware/download/csv')
@cortex.lib.user.login_required
def vmware_download_csv():
	"""Downloads the VMware data as a CSV file."""

	# Get the list of systems
	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute('SELECT * FROM `vmware_cache_vm` ORDER BY `name`')

	# Return the response
	return Response(vmware_csv_stream(curd), mimetype="text/csv", headers={'Content-Disposition': 'attachment; filename="vmware.csv"'})

