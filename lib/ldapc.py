
from cortex import app
from flask import g, abort
import MySQLdb as mysql
import ldap, ldap.filter
import re

################################################################################

def connect():
	# Connect to LDAP and turn off referrals
	conn = ldap.initialize(app.config['LDAP_URI'])
	conn.set_option(ldap.OPT_REFERRALS, 0)

	 # Bind to the server either with anon or with a defined user/pass in the config
	try:
		if app.config['LDAP_ANON_BIND']:
			conn.simple_bind_s()
		else:
			conn.simple_bind_s( (app.config['LDAP_BIND_USER']), (app.config['LDAP_BIND_PW']) )
	except ldap.LDAPError as e:
		flash('Internal Error - Could not connect to LDAP directory: ' + str(e), 'alert-danger')
		app.logger.error("Could not bind to LDAP: " + str(e))
		abort(500)

	return conn

################################################################################

def auth(username,password):

	# Connect to the LDAP server
	l = connect()

	# Now search for the user object to bind as
	try:
		results = l.search_s(app.config['LDAP_USER_SEARCH_BASE'], ldap.SCOPE_SUBTREE, (app.config['LDAP_USER_ATTRIBUTE']) + "=" + ldap.filter.escape_filter_chars(username))
	except ldap.LDAPError as e:
		return False

	# Handle the search results
	for result in results:
		dn    = result[0]
		attrs = result[1]

		if dn == None:
			# No dn returned. Return false.
			return False
		else:
			# Found the DN. Yay! Now bind with that DN and the password the user supplied
			try:
				lauth = ldap.initialize(app.config['LDAP_URI'])
				lauth.set_option(ldap.OPT_REFERRALS, 0)
				lauth.simple_bind_s((dn), (password))
			except ldap.LDAPError as e:
				# Password was wrong
				return False

			# Return that LDAP auth succeeded
			return True

	return False

################################################################################

def get_users_groups_from_ldap(username):
	"""Talks to LDAP and gets the list of the given users groups. This
	information is then stored in Redis so that it can be accessed 
	quickly."""


	# Connect to the LDAP server
	l = connect()

	# Now search for the user object
	try:
		results = l.search_s(app.config['LDAP_USER_SEARCH_BASE'], ldap.SCOPE_SUBTREE, (app.config['LDAP_USER_ATTRIBUTE']) + "=" + username)
	except ldap.LDAPError as e:
		return None

	# Handle the search results
	for result in results:
		dn    = result[0]
		attrs = result[1]

		if dn == None:
			return None
		else:
			# Found the DN. Yay! Now bind with that DN and the password the user supplied
			if 'memberOf' in attrs:
				if len(attrs['memberOf']) > 0:

					app.logger.debug("Found groups for " + username)

					## Delete the existing cache
					curd = g.db.cursor(mysql.cursors.DictCursor)
					curd.execute('DELETE FROM `ldap_group_cache` WHERE `username` = %s', (username,))
					
					## Create the new cache
					groups = []
					for group in attrs['memberOf']:
						## We only want the group name, not the DN
						cn_regex = re.compile("^(cn|CN)=([^,;]+),")
						
						## Preprocssing into string
						group = group.decode('utf-8')
						matched = cn_regex.match(group)
						if matched:
							group_cn = matched.group(2)
						else:
							## didn't find the cn, so skip this 'group'
							continue

						curd.execute('INSERT INTO `ldap_group_cache` (`username`, `group_dn`, `group`) VALUES (%s, %s, %s)', (username, group.lower(), group_cn.lower()))
						groups.append(group_cn.lower())

					## Set the cache expiration
					curd.execute('REPLACE INTO `ldap_group_cache_expire` (`username`, `expiry_date`) VALUES (%s,NOW() + INTERVAL 15 MINUTE)', (username,))

					## Commit the transaction
					g.db.commit()

					# Return a sorted list so that it matches what we get from MySQL
					return sorted(groups)
				else:
					return None
			else:
				return None

	return None

##############################################################################

def get_user_realname_from_ldap(username):
	"""Talks to LDAP and retrieves the real name of the username passed."""

	if username is None or username == "":
		return ""

	# The name we've picked
	# Connect to LDAP
	l = connect()
	
	# Now search for the user object
	try:
		results = l.search_s(app.config['LDAP_USER_SEARCH_BASE'], ldap.SCOPE_SUBTREE, app.config['LDAP_USER_ATTRIBUTE'] + "=" + username)
	except ldap.LDAPError as e:
		app.logger.warning('Failed to execute real name LDAP search: ' + str(e))
		return username

	firstname = None
	lastname = None

	# Handle the search results
	for result in results:
		dn    = result[0]
		attrs = result[1]

		if dn == None:
			return None
		else:
			if 'givenName' in attrs:
				if len(attrs['givenName']) > 0:
					firstname = attrs['givenName'][0]
			if 'sn' in attrs:
				if len(attrs['sn']) > 0:
					lastname = attrs['sn'][0]

	# In Python 3, the ldap client returns bytes, so decode UTF-8
	if type(firstname) is bytes:
		firstname = firstname.decode('utf-8')
	if type(lastname) is bytes:
		lastname = lastname.decode('utf-8')

	try:
		if len(firstname) > 0 and len(lastname) > 0:
			name = firstname + ' ' + lastname
		elif len(firstname) > 0:
			name = firstname
		elif len(lastname) > 0:
			name = lastname
		else:
			name = username
	except Exception as ex:
		app.logger.warning('Failed to generate real name: ' + str(ex))
		name = username
	try:
		curd = g.db.cursor(mysql.cursors.DictCursor)
		curd.execute('REPLACE INTO `realname_cache` (`username`, `realname`) VALUES (%s,%s)', (username, name))
		g.db.commit()
	except Exception as ex:
		app.logger.warning('Failed to cache user name: ' + str(ex))
	return name

################################################################################

def does_group_exist(groupname):
	# Connect to the LDAP server
	l = connect()

	# Now search for the user object to bind as
	try:
		results = l.search_s(app.config['LDAP_GROUP_SEARCH_BASE'], ldap.SCOPE_SUBTREE, "cn" + "=" + ldap.filter.escape_filter_chars(groupname))
	except ldap.LDAPError as e:
		return False

	# Handle the search results
	for result in results:
		dn    = result[0]
		attrs = result[1]

		if dn == None:
			# No dn returned. Return false.
			return False
		else:
			if "member" in attrs:
				return True

	return False
