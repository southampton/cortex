#!/usr/bin/python

import MySQLdb as mysql
import sys, copy, os, re
import socket, datetime, sys, select, signal, ipaddress

class Notifier(object):
	"""Base class for notifiers. Just generates the default message content."""

	def __init__(self, helper):
		self.helper = helper

	def generate_message_content(self, digest, subject_cn, subject_dn, issuer_cn, issuer_dn, not_before, not_after, days, sans, where):
		contents =            "The following certificate will expire soon. Please see the details below to see if it is required, and renew it if necessary.\n"
		contents = contents + "\n"
		contents = contents + "Subject CN: " + str(subject_cn) + "\n"
		contents = contents + "Subject DN: " + str(subject_dn) + "\n"
		contents = contents + "Subject Alternate Names: " + ', '.join(sans) + "\n"
		contents = contents + "Valid From: " + str(not_before) + "\n"
		contents = contents + "Valid Until: " + str(not_after) + " - will expire in " + str(days) + " day(s)\n"
		contents = contents + "Issuer CN: " + str(issuer_cn) + "\n"
		contents = contents + "Issuer DN: " + str(issuer_dn) + "\n"
		contents = contents + "Digest: " + str(digest) + "\n"
		contents = contents + "\n"
		contents = contents + "The certificate was discovered in the following locations:\n"
		contents = contents + '\n'.join(where) + "\n"
		contents = contents + "\n"
		contents = contents + "Certificate information available at https://" + self.helper.config['CORTEX_DOMAIN'] + "/certificate/" + digest

		return contents

	def generate_short_description(self, digest, subject_cn, subject_dn, issuer_cn, issuer_dn, not_before, not_after, days, sans, where):
		if subject_cn is None:
			subject_cn = 'Unknown CN'
		else:
			subject_cn = str(subject_cn)

		result = 'Certificate expiry notification: ' + subject_cn + ' during ' + not_after.strftime('%Y-%m-%d')
		return result

class EmailNotifier(Notifier):
	"""Notifies about certificate expiry via email."""

	def __init__(self, helper, to_address):
		super(EmailNotifier, self).__init__(helper)
		self.to_address = to_address

	def notify(self, digest, subject_cn, subject_dn, issuer_cn, issuer_dn, not_before, not_after, days, sans, where):
		subject = self.generate_short_description(digest, subject_cn, subject_dn, issuer_cn, issuer_dn, not_before, not_after, days, sans, where)
		contents = self.generate_message_content(digest, subject_cn, subject_dn, issuer_cn, issuer_dn, not_before, not_after, days, sans, where)
		self.helper.lib.send_email(self.to_address, subject, contents)

class TicketNotifier(Notifier):
	"""Creates a ticket about certificate expiry."""

	def __init__(self, helper, ticket_type, team_name, opener_sys_id, request_type=None):
		super(TicketNotifier, self).__init__(helper)
		self.ticket_type = ticket_type
		self.team_name = team_name
		self.opener_sys_id = opener_sys_id
		self.request_type = request_type

	def notify(self, digest, subject_cn, subject_dn, issuer_cn, issuer_dn, not_before, not_after, days, sans, where):
		short_description = self.generate_short_description(digest, subject_cn, subject_dn, issuer_cn, issuer_dn, not_before, not_after, days, sans, where)
		description = self.generate_message_content(digest, subject_cn, subject_dn, issuer_cn, issuer_dn, not_before, not_after, days, sans, where)
		if self.ticket_type == 'incident':
			self.helper.lib.servicenow_create_ticket(short_description, description, self.opener_sys_id, self.team_name)
		elif self.ticket_type == 'request':
			self.helper.lib.servicenow_create_request(short_description, description, self.opener_sys_id, self.team_name, self.request_type, self.opener_sys_id)

def run(helper, options):
	"""Iterates over the certificates stored in the database and notifies of ones soon to expire."""

	# Ensure we have some configuration
	if 'CERT_SCAN_NOTIFY' not in helper.config or helper.config['CERT_SCAN_NOTIFY'] is None:
		helper.event('cert_notify_noconfig', 'No certificate notifications configured', oneshot=True)
		return

	# Get the configuration
	if type(helper.config['CERT_SCAN_NOTIFY']) is dict:
		# If we have a single dictionary, convert it to a list containing a single 
		# dictionary for easier looping later
		cert_scan_notify = [helper.config['CERT_SCAN_NOTIFY']]
	elif type(helper.config['CERT_SCAN_NOTIFY']) is list:
		cert_scan_notify = helper.config['CERT_SCAN_NOTIFY']
	else:
		raise helper.lib.TaskFatalError('Incorrect configuration for certificate notification')

	db = helper.db_connect()
	cur = db.cursor(mysql.cursors.DictCursor)
	num_notifyees = len(cert_scan_notify)
	notifyee_num = 0
	for notifyee in cert_scan_notify:
		notifyee_cert_count = 0
		notifyee_num = notifyee_num + 1

		helper.event('cert_notify_calc', 'Performing notification instruction ' + str(notifyee_num) + '/' + str(num_notifyees))

		# Ensure we have required configuration
		if 'days_left' not in notifyee or 'type' not in notifyee:
			helper.end_event(description='Missing required configuration for notifyee ' + str(notifyee_num) + '/' + str(num_notifyees), success=False)
			continue

		# Build relevant notifier
		if notifyee['type'] == 'email':
			notifier = EmailNotifier(helper, notifyee['to'])
		elif notifyee['type'] in ('incident', 'request'):
			if notifyee['type'] == 'request':
				request_type = notifyee['request_type']
			else:
				request_type = None
			notifier = TicketNotifier(helper, notifyee['type'], notifyee['team_name'], notifyee['opener_sys_id'], request_type)
		else:
			helper.end_event(description='Unknown notification type "' + str(notifyee['type']) + '" for notifyee ' + str(notifyee_num), success=False)
			continue

		# If we have an ignore_issuer_dn option, compile a regex for it
		if 'ignore_issuer_dn' in notifyee:
			# We can't have both of these options
			if 'require_issuer_dn' in notifyee:
				helper.end_event(description='Option require_issuer_dn conflicts with ignore_issuer_dn regex for notifyee ' + str(notifyee_num), success=False)
				continue
			try:
				ignore_issuer_dn = re.compile(notifyee['ignore_issuer_dn'])
			except Exception as e:
				helper.end_event(description='Invalid ignore_issuer_dn regex for notifyee ' + str(notifyee_num), success=False)
				continue
		else:
			ignore_issuer_dn = None

		# If we have an require_issuer_dn option, compile a regex for it
		if 'require_issuer_dn' in notifyee:
			try:
				require_issuer_dn = re.compile(notifyee['require_issuer_dn'])
			except Exception as e:
				helper.end_event(description='Invalid require_issuer_dn regex for notifyee ' + str(notifyee_num), success=False)
				continue
		else:
			require_issuer_dn = None

		# Get the notification times
		days_left = notifyee['days_left']
		if type(days_left) is not list:
			days_left = [days_left]

		# For each number in the days_left array for this notifyee
		for days in days_left:
			# Get the number of certs expiring on this day. Note that we convert the 
			# certificate expiry date, which is in UTC into local timezone for calculating 
			# the number of days remaining on a certificate.
			cur.execute('SELECT `digest`, `subjectCN`, `subjectDN`, `issuerCN`, `issuerDN`, `notBefore`, `notAfter`, `notify` FROM `certificate` WHERE DATE(CONVERT_TZ(`notAfter`, "+00:00", @@session.time_zone)) = DATE_ADD(DATE(NOW()), INTERVAL ' + str(days) + ' DAY)')
			row = cur.fetchone()
			while row is not None:
				# If we're supposed to be notifying on this certificate
				if row['notify'] != 0:
					# If we've not got a ignore_issuer_dn option, or if we do have one and this issuer DN doesn't match
					# Additionally, if we've got a require_issuer_dn option, only match on rows where the issuer DN matches
					if (ignore_issuer_dn is None or ignore_issuer_dn.search(row['issuerDN']) is None) and (require_issuer_dn is None or require_issuer_dn.search(row['issuerDN'])):
						# Keep a count of how many notifications we've sent to this notifyee
						notifyee_cert_count = notifyee_cert_count + 1

						# Get the SANs for this certificate
						cert_cur = db.cursor(mysql.cursors.DictCursor)
						cert_cur.execute('SELECT `san` FROM `certificate_sans` WHERE `cert_digest` = %s', (row['digest'],))
						sans = [cert_san['san'] for cert_san in cert_cur.fetchall()]

						cert_cur.execute('SELECT `host`, `port` FROM `scan_result` WHERE `cert_digest`= %s AND `when` = (SELECT MAX(`when`) FROM `scan_result` WHERE `cert_digest` = %s)', (row['digest'], row['digest']))
						where = [cert_where['host'] + ':' + str(cert_where['port']) for cert_where in cert_cur.fetchall()]

						notifier.notify(row['digest'], row['subjectCN'], row['subjectDN'], row['issuerCN'], row['issuerDN'], row['notBefore'], row['notAfter'], days, sans, where)
				
				row = cur.fetchone()

		helper.end_event(description='Notified on expiry of ' + str(notifyee_cert_count) + ' certificates for notifyee ' + str(notifyee_num) + '/' + str(num_notifyees))
