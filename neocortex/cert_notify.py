#!/usr/bin/python

import MySQLdb as mysql
import sys, copy, os, re
import socket, datetime, sys, select, signal, ipaddress

class EmailNotifier(object):
	"""Notifies about certificate expiry via email."""

	def __init__(self, helper, to_address):
		self.helper = helper
		self.to_address = to_address

	def notify(self, digest, subject_cn, subject_dn, issuer_cn, issuer_dn, not_before, not_after, days, sans, where):
		subject = 'Certificate expiry notification'
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

		self.helper.lib.send_email(self.to_address, subject, contents)

class TicketNotifier(object):
	"""Creates a ticket about certificate expiry."""

	def __init__(self, helper, ticket_type, team_name, opener_sys_id):
		self.helper = helper
		self.ticket_type = ticket_type
		self.team_name = team_name
		self.opener_sys_id = opener_sys_id

	def notify(self, digest, subject_cn, subject_dn, issuer_cn, issuer_dn, not_before, not_after, days, sans, where):
		pass

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
			notifier = TicketNotifier(helper, notifyee['type'], notifyee['team_name'], notifyee['opener_sys_id'])
		else:
			helper.end_event(description='Unknown notification type "' + str(notifyee['type']) + '" for notifyee ' + str(notifyee_num), success=False)
			continue

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
