
from cortex import app
from flask import g, abort, flash
import MySQLdb as mysql
import ldap3
import re

################################################################################

def connect():
	# Connect to LDAP and turn off referrals
	server =  ldap3.Server(app.config['LDAP_URI'])
	conn = ldap3.Connection(server, app.config['LDAP_BIND_USER'], app.config['LDAP_BIND_PW'], auto_bind=False, auto_referrals=False)

	# Bind to the server either with a defined user/pass in the config
	try:
		assert conn.bind() # Ensure the bind is successful
	except (AssertionError, ldap3.core.exceptions.LDAPException) as ex:
		flash('Internal Error - Could not connect to LDAP directory: ' + str(ex), 'alert-danger')
		app.logger.error("Could not bind to LDAP: " + str(ex))
		abort(500)

	return conn

################################################################################

def ldap_search(ldap_connection, username, attributes=[]):
	return ldap_connection.search(
		search_base=app.config['LDAP_USER_SEARCH_BASE'],
		search_scope=ldap3.SUBTREE,
		search_filter="(&(objectClass=user)({user_attr}={username}))".format(
			user_attr=app.config['LDAP_USER_ATTRIBUTE'],
			username=ldap3.utils.conv.escape_filter_chars(username)
		),
		attributes=attributes,
	)

################################################################################

def auth(username,password):

	# Connect to the LDAP server
	l = connect()

	# Now search for the user object to bind as
	try:
		search = ldap_search(l, username)
	except ldap3.core.exceptions.LDAPException:
		return False

	# Ensure we got a result
	if not search or not l.response:
		return False

	# Handle the search results
	for result in l.response:
		dn = result.get('dn')
		if not dn:
			# No dn returned. Return false.
			return False
		else:
			# Found the DN. Yay! Now bind with that DN and the password the user supplied
			try:
				assert l.rebind(user=dn, password=password)
			except (AssertionError, ldap3.core.exceptions.LDAPException):
				# Password was wrong
				return False
			else:
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
		search = ldap_search(l, username, attributes=['memberOf'])
	except ldap3.core.exceptions.LDAPException:
		return None

	# Ensure we got a result
	if not search or not l.response:
		return False

	# Handle the search results
	for result in l.response:
		dn    = result.get('dn')
		attrs = result['attributes']

		if not dn:
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

	# Connect to LDAP
	l = connect()
	
	# Now search for the user object
	try:
		search = ldap_search(l, username, attributes=['givenName', 'sn'])
	except ldap3.core.exceptions.LDAPException as ex:
		app.logger.warning('Failed to execute real name LDAP search: ' + str(ex))
		return username

	# Ensure we got a result
	if not search or not l.response:
		name = username
	else:
		firstname = ""
		lastname = ""

		# Handle the search results
		for result in l.response:
			dn    = result.get('dn')
			attrs = result.get('attributes')

			if dn is None or attrs is None:
				return None

			if 'givenName' in attrs:
				if type(attrs['givenName']) is list and len(attrs['givenName']) > 0:
					firstname = attrs['givenName'][0]
				else:
					firstname = attrs['givenName']
			if 'sn' in attrs:
				if type(attrs['sn']) is list and len(attrs['sn']) > 0:
					lastname = attrs['sn'][0]
				else:
					lastname = attrs['sn']

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

	# Log the value to the database
	try:
		curd = g.db.cursor(mysql.cursors.DictCursor)
		curd.execute('REPLACE INTO `realname_cache` (`username`, `realname`) VALUES (%s, %s)', (username, name))
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
		search = l.search(
			search_base=app.config['LDAP_GROUP_SEARCH_BASE'],
			search_scope=ldap3.SUBTREE,
			search_filter="(&(objectClass=group)(cn={groupname}))".format(
				groupname=ldap3.utils.conv.escape_filter_chars(groupname)
			),
			attributes=['member'],
		)
	except ldap3.core.exceptions.LDAPException as e:
		return False

	# Ensure we got a result
	if not search or not l.response:
		return False

	# Handle the search results
	for result in l.response:
		if not all(k in result for k in ['dn', 'attributes']):
			return False

		if result.get('dn') and result.get('attributes'):
			if result['attributes'].get('member'):
				return True
	return False
