
import MySQLdb as mysql
from flask import g

################################################################################

# pylint: disable=too-many-branches,too-many-statements
def get_os_stats():
	# Get a cursor to the database
	curd = g.db.cursor(mysql.cursors.DictCursor)

	# Get OS IDs for all virtual machines
	curd.execute('SELECT `guestId` FROM `vmware_cache_vm` WHERE `template` = 0')
	results = curd.fetchall()

	types = {
		"windows":
		0,
		"linux": 0,
		"bsd": 0,
		"other": 0,

		"windows_desktop": 0,
		"windows_server": 0,
		"ws2003": 0,
		"ws2008": 0,
		"ws2008r2": 0,
		"ws2012": 0,
		"ws2016": 0,

		"wd7": 0,
		"wd8": 0,
		"wd10": 0,

		"ubuntu": 0,
		"debian": 0,
		"rhel": 0,
		"rhel3": 0,
		"rhel4": 0,
		"rhel5": 0,
		"rhel6": 0,
		"rhel7": 0,
		"linux_other": 0,
	}

	for result in results:
		ostr = result['guestId']

		if 'win' in ostr:
			types['windows'] += 1

			if 'windows7Guest' in ostr or 'windows7_64Guest' in ostr:
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

				elif 'winLonghornGuest' in ostr or 'winLonghorn64Guest' in ostr:
					types['ws2008'] += 1

				elif 'windows7Server' in ostr:
					types['ws2008r2'] += 1

				elif 'windows8Server' in ostr:
					types['ws2012'] += 1

				elif 'windows9Server' in ostr:
					types['ws2016'] += 1

		elif any(k in ostr.lower() for k in ["linux", "rhel", "sles", "ubuntu", "centos", "debian"]):
			types['linux'] += 1

			if 'ubuntu' in ostr:
				types['ubuntu'] += 1
			elif 'debian' in ostr:
				types['debian'] += 1
			elif 'rhel' in ostr:
				types['rhel'] += 1

				if 'rhel3' in ostr:
					types['rhel3'] += 1
				elif 'rhel4' in ostr:
					types['rhel4'] += 1
				elif 'rhel5' in ostr:
					types['rhel5'] += 1
				elif 'rhel6' in ostr:
					types['rhel6'] += 1
				elif 'rhel7' in ostr:
					types['rhel7'] += 1
				elif 'rhel8' in ostr:
					types['rhel8'] += 1

			else:
				types['linux_other'] += 1

		elif "freebsd" in ostr:
			types['bsd'] += 1

		else:
			types['other'] += 1

	return types
