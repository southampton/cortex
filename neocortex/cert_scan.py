#!/usr/bin/python

import MySQLdb as mysql
import sys, copy, os, re
import OpenSSL as openssl
import socket, datetime, sys, select, signal, ipaddress
from multiprocessing import Pool
from corpus import x509utils

################################################################################

class InterruptException(Exception):
	"""Raised when a worker is interrupted."""
	pass

################################################################################

def do_starttls_smtp(sock):
	"""Performs STARTTLS setup for SMTP."""

	# SMTP: Read banner
	res1 = select.select([sock], [], [], 3.0)
	if len(res1[0]) == 0:
		raise socket.timeout()
	sock.recv(2048)

	# SMTP: Write EHLO
	res2 = select.select([], [sock], [], 3.0)
	sock.send("EHLO sslscan.client.net\r\n")

	# SMTP: Read EHLO response
	res1 = select.select([sock], [], [], 3.0)
	if len(res1[0]) == 0:
		raise socket.timeout()
	sock.recv(2048)

	# SMTP: Write STARTTLS
	res2 = select.select([], [sock], [], 3.0)
	sock.send("STARTTLS\r\n")

	# SMTP: Read "Ready for STARTTLS"
	res1 = select.select([sock], [], [], 3.0)
	if len(res1[0]) == 0:
		raise socket.timeout()
	sock.recv(2048)

################################################################################

def do_starttls_imap(sock):
	"""Performs STARTTLS setup for IMAP."""

	# IMAP: Read banner
	res1 = select.select([sock], [], [], 3.0)
	if len(res1[0]) == 0:
		raise socket.timeout()
	sock.recv(2048)

	# IMAP: Write CAPABILITY
	res2 = select.select([], [sock], [], 3.0)
	sock.send("a001 CAPABILITY\r\n")

	# SMTP: Read CAPABILITY response
	res1 = select.select([sock], [], [], 3.0)
	if len(res1[0]) == 0:
		raise socket.timeout()
	sock.recv(2048)

	# IMAP: Write STARTTLS
	res2 = select.select([], [sock], [], 3.0)
	sock.send("a002 STARTTLS\r\n")

	# IMAP: Read "Ready for STARTTLS"
	res1 = select.select([sock], [], [], 3.0)
	if len(res1[0]) == 0:
		raise socket.timeout()
	sock.recv(2048)

################################################################################

def do_starttls_ldap(sock):
	"""Performs STARTTLS setup for LDAP."""

	# Structure of the LDAP STARTTLS message:
	#          |LDAPMessage                                                                                                               |
	#          |-------DATA---------------------------------------------------------------------------------------------------------------|
	#                  |MessageID ||ExtendedRequest (CHOICE)                                                                              |
	#                  |-------DAT||-------DATA-------------------------------------------------------------------------------------------|
	#                                      |requestName (LDAPString)                                                                      |
	#                                      |-------DATA-----------------------------------------------------------------------------------|
	message = "\x30\x1d\x02\x01\x01\x77\x18\x80\x16\x31\x2e\x33\x2e\x36\x2e\x31\x2e\x34\x2e\x31\x2e\x31\x34\x36\x36\x2e\x32\x30\x30\x33\x37"

	# LDAP: Send STARTTLS LDAPMessage
	res2 = select.select([], [sock], [], 3.0)
	sock.send(message)

	# SMTP: Read STARTTLS Response
	res1 = select.select([sock], [], [], 3.0)
	if len(res1[0]) == 0:
		raise socket.timeout()
	sock.recv(2048)

################################################################################

def raise_interrupt(signum, frame):
	"""Signal handler that just raises an InterruptException."""

	raise InterruptException()

################################################################################

def scan_ip(host, port, timeout, starttls=None):
	"""Scans a IP:Port for an SSL certificate."""

	# Set signal handlers inherited from parent that log a NeoCortex shutdown
	signal.signal(signal.SIGTERM, raise_interrupt)
	signal.signal(signal.SIGINT, raise_interrupt)

	result = {'host': str(host), 'port': port}
	try:
		# Set an alarm to raise an exception if something takes too long
		signal.signal(signal.SIGALRM, raise_interrupt)
		signal.alarm(timeout)

		# Set up the socket
		sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		sock.settimeout(3)

		# Set up the context and SSL socket
		context = openssl.SSL.Context(openssl.SSL.SSLv23_METHOD)
		context.set_timeout(3)

		if starttls is not None:
			sock.connect((host.exploded, port))
			sock.setblocking(1)

			if starttls == 'smtp':
				do_starttls_smtp(sock)
			elif starttls == 'imap':
				do_starttls_imap(sock)
			elif starttls == 'ldap':
				do_starttls_ldap(sock)
			else:
				pass

		sock = openssl.SSL.Connection(context, sock)
		sock.settimeout(3)

		if starttls is None:
			# Connect and do the handshake
			sock.connect((host.exploded, port))
			sock.setblocking(1)
			sock.do_handshake()
		else:
			# Let OpenSSL know we're a client
			sock.set_connect_state()

			# For reasons that are not clear to me, this doesn't work the first time,
			# nor the second, and often nor the third. Hence this ridiculous loop
			done = False
			while not done:
				try:
					sock.do_handshake()
					done = True
				except openssl.SSL.WantReadError:
					# Wait for the socket to become readable
					select.select([sock], [], [], 1.0)
				except Exception as e:
					raise e

		# Disable the alarm
		signal.alarm(0)

		# Get certificate details: Subject DN + CN
		peer_cert = sock.get_peer_certificate()
		peer_cert_name = ""
		peer_cert_dn = ""
		if type(peer_cert) is openssl.crypto.X509:
			peer_cert_subject = peer_cert.get_subject()
		elif type(peer_cert) is opeenssl.crypto.X509Name:
			peer_cert_subject = peer_cert
		if type(peer_cert_subject) is openssl.crypto.X509Name:
			peer_cert_name = peer_cert_subject.CN
			peer_cert_dn = repr(peer_cert_subject)
			if peer_cert_dn is not None:
				peer_cert_dn = peer_cert_dn[19:-2]

		# Get certificate details: Issuer DN + CN
		issuer_cert = peer_cert.get_issuer()
		issuer_cert_name = ""
		issuer_cert_dn = ""
		if type(issuer_cert) is openssl.crypto.X509:
			issuer_cert_subject = issuer_cert.get_subject()
		elif type(issuer_cert) is openssl.crypto.X509Name:
			issuer_cert_subject = issuer_cert
		if type(issuer_cert_subject) is openssl.crypto.X509Name:
			issuer_cert_name = issuer_cert_subject.CN
			issuer_cert_dn = repr(issuer_cert_subject)
			if issuer_cert_dn is not None:
				issuer_cert_dn = issuer_cert_dn[19:-2]

		# Get certificate details: Validity period
		notafter_time = x509utils.parse_zulu_time(peer_cert.get_notAfter())
		notbefore_time = x509utils.parse_zulu_time(peer_cert.get_notBefore())

		# Get certificate details: key size
		key_size = peer_cert.get_pubkey().bits()

		# Get list of subjectAltNames
		sans = x509utils.get_subject_alt_names(peer_cert)

		peer_cert_chain = sock.get_peer_cert_chain()
		if peer_cert_chain is None or len(peer_cert_chain) <= 1:
			first_chain_cert = None
		else:
			first_chain_cert = peer_cert_chain[1]
			if type(peer_cert_chain[1].get_subject()) is openssl.crypto.X509Name:
				first_chain_cert = peer_cert_chain[1].get_subject().CN
			else:
				first_chain_cert = ""

		result.update({'discovered': 1, 'protocol': sock.get_protocol_version_name(), 'cipher': sock.get_cipher_name(), 'notAfter': notafter_time, 'notBefore': notbefore_time, 'subject_cn': peer_cert_name, 'subject_dn': peer_cert_dn, 'issuer_cn': issuer_cert_name, 'issuer_dn': issuer_cert_dn, 'serial': peer_cert.get_serial_number(), 'subject_hash': peer_cert.subject_name_hash(), 'digest': peer_cert.digest('SHA1').replace(':', '').lower(), 'sans': sans, 'first_chain_cert': first_chain_cert, 'key_size': key_size})
		return result

	except socket.timeout as e1:
		signal.alarm(0)
		result.update({'discovered': 0, 'exception': str(type(e1)) + ": " + str(e1)})
	except socket.error as e2:
		signal.alarm(0)
		if e2.args[0] in [111, 113]:
			# No route to host / connection refused
			result.update({'discovered': 0, 'exception': str(type(e2)) + ": " + str(e2.args)})
		else:
			result.update({'discovered': -1, 'exception': str(type(e2)) + ": " + str(e2.args)})
	except InterruptException as e3:
		signal.alarm(0)
		result.update({'discovered': -1, 'exception': str(type(e3)) + ": " + str(e3)})
	except Exception as e4:
		signal.alarm(0)
		result.update({'discovered': -1, 'exception': str(type(e4)) + ": " + str(e4)})

	return result

################################################################################

total_results = 0
total_searches = 0
last_percentage = ""
g_helper = None

def callback_func(arg):
	"""Callback function when a worker finishes to update statistics."""

	global total_results, total_searches, last_percentage, g_helper
	total_results = total_results + 1

	if g_helper is not None:
		try:
			new_percentage = "{0:.1%}".format(float(total_results) / float(total_searches))

			if new_percentage != last_percentage:
				last_percentage = new_percentage
				g_helper.update_event("Scanning network for certificates: scanned {0}/{1} ({2})".format(total_results, total_searches, new_percentage))
		except Exception as e:
			# Catch all exceptions so we don't break the pool
			pass

def run(helper, options):
	"""Run the certificate scan."""

	global total_results, total_searches, g_helper

	# Start all the scans
	helper.event('cert_start_scan', 'Initialising certificate scan')
	ip_pool = Pool(helper.config['CERT_SCAN_WORKERS'])
	results = []
	for ip_range in helper.config['CERT_SCAN_IP_RANGES']:
		# Make sure this is a unicode object
		ip_range = unicode(ip_range)

		# If this is a subnet
		if '/' in ip_range:
			ip_range_data = ipaddress.ip_network(ip_range).hosts()
		else:
			ip_range_data = [ipaddress.ip_address(ip_range)]

		for host in ip_range_data:
			for port in helper.config['CERT_SCAN_PORTS']:
				starttls = None
				if port in helper.config['CERT_SCAN_PORTS_STARTTLS']:
					starttls = helper.config['CERT_SCAN_PORTS_STARTTLS'][port]
				total_searches = total_searches + 1
				results.append(ip_pool.apply_async(scan_ip, (host, port, helper.config['CERT_SCAN_THREAD_TIMEOUT'], starttls), callback=callback_func))
	helper.end_event(description='Initialised scanning of ' + str(total_searches) + ' ports')

	# Wait for the scan to finish
	helper.event('cert_run_scan', 'Scanning network for certificates')
	g_helper = helper
	ip_pool.close()
	ip_pool.join()
	helper.end_event(description='Scan completed')

	# Connect to the database
	helper.event('cert_save_to_db', 'Writing to database...')
	db = helper.db_connect()
	cur = db.cursor(mysql.cursors.DictCursor)
	cur._defer_warnings = True

	# Get the current timestamp and use this for all the inserts in to the database
	# so that all the records for this scan appear as the same timestamp as opposed
	# to possibly over a couple of seconds
	now = datetime.datetime.now()

	# Iterate over the results, saving to the database
	add_digests = set()
	exception_count = 0
	new_certs = 0
	total_hits = 0
	for result in results:
		try:
			entry = result.get()
		except Exception as e:
			# Skip past things where an exception has somehow fallen through
			exception_count = exception_count + 1
			continue

		# For simple "there's nothing listening here" errors, skip them
		if entry['discovered'] != 0:
			if 'exception' in entry:
				exception_count = exception_count + 1
				continue
			else:
				# Default to valid chain
				chain_check = 0
				if entry['first_chain_cert'] is None:
					# No certificate chain (also appears for self-signed)
					chain_check = 1
				else:
					if entry['first_chain_cert'] != entry['issuer_cn']:
						# Bad certificate chain
						chain_check = 2

				# If it's a cert we've not seen yet in this current scan
				if entry['digest'] not in add_digests:
					# Note that we've seen it
					add_digests.add(entry['digest'])

					# Stick it in the database
					new_certs = 0
					cur.execute("INSERT IGNORE INTO `certificate` (`digest`, `subjectHash`, `subjectCN`, `subjectDN`, `notBefore`, `notAfter`, `issuerCN`, `issuerDN`, `notes`, `keySize`) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", (entry['digest'], entry['subject_hash'], entry['subject_cn'], entry['subject_dn'], entry['notBefore'], entry['notAfter'], entry['issuer_cn'], entry['issuer_dn'], "", entry['key_size']))

					# Stick the SANs in the database
					for san in entry['sans']:
						cur.execute("INSERT IGNORE INTO `certificate_sans` (`cert_digest`, `san`) VALUES (%s, %s)", (entry['digest'], san))

				cur.execute("INSERT INTO `scan_result` (`host`, `port`, `cert_digest`, `when`, `chain_state`) VALUES (%s, %s, %s, %s, %s)", (entry['host'], entry['port'], entry['digest'], now, chain_check))
				total_hits = total_hits + 1

	db.commit()
	helper.end_event(description='Database updated: ' + str(total_hits) + ' hit(s), ' + str(new_certs) + ' new certificate(s), and ' + str(exception_count) + ' exception(s)')

	## Remove certificates not seen in a scan in a configurable amount of time from the database
	helper.event('cert_expire_unseen', 'Expiring certificates not seen in ' + str(helper.config['CERT_SCAN_EXPIRE_NOT_SEEN']) + ' days')

	# Note that we join on a nested select rather than doing a "`key` IN (nested select)" as this is significantly faster.
	cur.execute('DELETE `certificate` FROM `certificate` INNER JOIN (SELECT `cert_digest` FROM `scan_result` GROUP BY `scan_result`.`cert_digest` HAVING MAX(`when`) < DATE_SUB(NOW(), INTERVAL ' + str(int(helper.config['CERT_SCAN_EXPIRE_NOT_SEEN'])) + ' DAY)) `inner_scan_result` ON `certificate`.`digest` = `inner_scan_result`.`cert_digest`')
	certs_removed = cur.rowcount
	db.commit()

	helper.end_event(description='Expired ' + str(certs_removed) + ' certificates not seen in ' + str(helper.config['CERT_SCAN_EXPIRE_NOT_SEEN']) + ' days')

	## Remove scan results not seen in a configurable amount of time from the database
	helper.event('cert_expire_results', 'Expiring scan results older than ' + str(helper.config['CERT_SCAN_EXPIRE_RESULTS']) + ' days')
	cur.execute('DELETE FROM `scan_result` WHERE `when` < DATE_SUB(NOW(), INTERVAL ' + str(int(helper.config['CERT_SCAN_EXPIRE_RESULTS'])) + ' DAY)')
	results_removed = cur.rowcount
	db.commit()
	helper.end_event(description='Expired ' + str(results_removed) + ' results older than ' + str(helper.config['CERT_SCAN_EXPIRE_RESULTS']) + ' days')
