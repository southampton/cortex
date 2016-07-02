#!/usr/bin/python

from flask import g
import MySQLdb as mysql

################################################################################

def get_os_stats():
	# Get a cursor to the database
	curd = g.db.cursor(mysql.cursors.DictCursor)

	# Get OS IDs for all virtual machines
	curd.execute('SELECT `guestId` FROM `vmware_cache_vm` WHERE `template` = 0')
	results = curd.fetchall()

	types = {}
	types['windows'] = 0
	types['linux']   = 0
	types['bsd']     = 0
	types['other']   = 0

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

		else:
			types['other'] += 1

	return types

