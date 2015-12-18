#!/usr/bin/python
#

from cortex import app
import cortex.core
from flask import Flask, request, session, redirect, url_for, flash, g, abort, make_response, render_template, jsonify
import os 
import time
import json
import re
import werkzeug
import MySQLdb as mysql

################################################################################

@app.route('/vmware/os')
@cortex.core.login_required
def vmware_os():
	"""Shows VM operating system statistics."""

	# Get a cursor to the databaseo
	cur = g.db.cursor(mysql.cursors.DictCursor)

	# Get OS IDs for all virtual machines
	cur.execute('SELECT `guestId` FROM `vmware_cache_vm`')
	results = cur.fetchall()

	types = {}
	types['windows']   = 0
	types['linux'] = 0
	types['bsd'] = 0

	types['windows_desktop'] = 0
	types['windows_server']  = 0
	types['ws2003'] = 0
	types['ws2008'] = 0
	types['ws2012'] = 0
	types['ws2016'] = 0

	types['wdvista'] = 0
	types['wd7'] = 0
	types['wd8'] = 0
	types['wd10'] = 0

	types['ubuntu'] = 0
	types['debian'] = 0
	types['rhel'] = 0
	types['rhel3'] = 0
	types['rhel4'] = 0
	types['rhel5'] = 0
	types['rhel6'] = 0
	types['rhel7'] = 0
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

	# Render
	return render_template('vmware-os.html', active='vmware', types=types)

################################################################################

@app.route('/vmware/hardware')
@cortex.core.login_required
def vmware_hw():
	"""Shows VM hardware version statistics."""

	# Get a cursor to the databaseo
	cur = g.db.cursor(mysql.cursors.DictCursor)

	# Get OS statistics
	cur.execute('SELECT `hwVersion`, COUNT(*) AS `count` FROM `vmware_cache_vm` GROUP BY `hwVersion` ORDER BY `hwVersion`')
	results = cur.fetchall()

	# Render
	return render_template('vmware-hw.html', active='vmware', stats_hw=results)

################################################################################

@app.route('/vmware/power')
@cortex.core.login_required
def vmware_power():
	"""Shows VM hardware power state statistics."""
	cur = g.db.cursor(mysql.cursors.DictCursor)
	cur.execute('SELECT `powerState`, COUNT(*) AS `count` FROM `vmware_cache_vm` GROUP BY `powerState` ORDER BY `powerState`')
	results = cur.fetchall()
	return render_template('vmware-power.html', active='vmware', stats_power=results)

################################################################################

@app.route('/vmware/tools')
@cortex.core.login_required
def vmware_tools():
	"""Shows VM tools statistics."""
	cur = g.db.cursor(mysql.cursors.DictCursor)
	cur.execute('SELECT `toolsRunningStatus`, COUNT(*) AS `count` FROM `vmware_cache_vm` WHERE `powerState` = "poweredOn" GROUP BY `toolsRunningStatus` ORDER BY `toolsRunningStatus`')
	stats_status = cur.fetchall()
	cur.execute('SELECT `toolsVersionStatus`, COUNT(*) AS `count` FROM `vmware_cache_vm` WHERE `powerState` = "poweredOn" GROUP BY `toolsVersionStatus` ORDER BY `toolsVersionStatus`')
	stats_version = cur.fetchall()
	return render_template('vmware-tools.html', active='vmware', stats_status=stats_status, stats_version=stats_version)

################################################################################

@app.route('/vmware/specs')
@cortex.core.login_required
def vmware_specs():
	"""Shows VM hardware spec statistics."""

	# Get a cursor to the databaseo
	cur = g.db.cursor(mysql.cursors.DictCursor)

	# Get OS statistics
	cur.execute('SELECT `memoryMB`, `numCPU` FROM `vmware_cache_vm`')
	results = cur.fetchall()

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

		try:
			data_cpu[int(vm['numCPU'])] += 1
		except KeyError as ex:
			data_cpu['Other'] += 1
			
	return render_template('vmware-specs.html', active='vmware', stats_ram=data_ram, stats_cpu=data_cpu)

################################################################################

@app.route('/vmware/data')
@cortex.core.login_required
def vmware_data():
	# Get a cursor to the databaseo
	cur = g.db.cursor(mysql.cursors.DictCursor)

	# Get OS statistics
	cur.execute('SELECT * FROM `vmware_cache_vm` ORDER BY `name`')
	results = cur.fetchall()

	return render_template('vmware-data.html', active='vmware', data=results)
