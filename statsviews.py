#!/usr/bin/python
#

from cortex import app, NotFoundError, DisabledError
import cortex.core
from flask import Flask, request, session, redirect, url_for, flash, g, abort, make_response, render_template, jsonify
import os 
import time
import json
import re
import werkzeug
import MySQLdb as mysql

################################################################################

@app.route('/stats/os')
@cortex.core.login_required
def stats_os():
	"""Shows VM operating system statistics."""

	# Get a cursor to the databaseo
	cur = g.db.cursor(mysql.cursors.DictCursor)

	# Get OS statistics
	cur.execute('SELECT `guestFullname` FROM `vmware_cache_vm`')
	
	# Start dictionary for OS grouping
	stats_osgroup = {'Windows': 0, 'Linux': 0, 'FreeBSD': 0, 'Other': 0}

	# Iterate over stats
	row = cur.fetchone()
	while row:
		if 'Linux' in row['guestFullname']:
			stats_osgroup['Linux'] = stats_osgroup['Linux'] + 1
		elif 'Windows' in row['guestFullname']:
                        stats_osgroup['Windows'] = stats_osgroup['Windows'] + 1
		elif 'FreeBSD' in row['guestFullname']:
			stats_osgroup['FreeBSD'] = stats_osgroup['FreeBSD'] + 1
		else:
			stats_osgroup['Other'] = stats_osgroup['Other'] + 1

		row = cur.fetchone()

	# Get OS statistics
	cur.execute('SELECT REPLACE(REPLACE(REPLACE(`guestFullname`, " (32-bit)", ""), " (64-bit)", ""), "Microsoft ", "") AS `guestOS`, COUNT(*) AS `count` FROM `vmware_cache_vm` GROUP BY `guestOS` ORDER BY `guestOS`')
	results_full = cur.fetchall()

	# Render
	return render_template('stats-os.html', active='stats', stats_osgroup=stats_osgroup, stats_osfull=results_full)

################################################################################

@app.route('/stats/hardware')
@cortex.core.login_required
def stats_hw():
	"""Shows VM hardware version statistics."""

	# Get a cursor to the databaseo
	cur = g.db.cursor(mysql.cursors.DictCursor)

	# Get OS statistics
	cur.execute('SELECT `hwVersion`, COUNT(*) AS `count` FROM `vmware_cache_vm` GROUP BY `hwVersion` ORDER BY `hwVersion`')
	results = cur.fetchall()

	# Render
	return render_template('stats-hw.html', active='stats', stats_hw=results)

################################################################################

@app.route('/stats/power')
@cortex.core.login_required
def stats_power():
	"""Shows VM hardware power state statistics."""
	cur = g.db.cursor(mysql.cursors.DictCursor)
	cur.execute('SELECT `guestState`, COUNT(*) AS `count` FROM `vmware_cache_vm` GROUP BY `guestState` ORDER BY `guestState`')
	results = cur.fetchall()
	return render_template('stats-power.html', active='stats', stats_power=results)

@app.route('/stats/tools')
@cortex.core.login_required
def stats_tools():
	"""Shows VM tools statistics."""
	cur = g.db.cursor(mysql.cursors.DictCursor)
	cur.execute('SELECT `toolsRunningStatus`, COUNT(*) AS `count` FROM `vmware_cache_vm` GROUP BY `toolsRunningStatus` ORDER BY `toolsRunningStatus`')
	stats_status = cur.fetchall()
	cur.execute('SELECT `toolsVersionStatus`, COUNT(*) AS `count` FROM `vmware_cache_vm` GROUP BY `toolsVersionStatus` ORDER BY `toolsVersionStatus`')
	stats_version = cur.fetchall()
	return render_template('stats-tools.html', active='stats', stats_status=stats_status, stats_version=stats_version)

################################################################################

@app.route('/stats/specs')
@cortex.core.login_required
def stats_specs():
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
			
	return render_template('stats-specs.html', active='stats', stats_ram=data_ram, stats_cpu=data_cpu)
