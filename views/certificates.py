
import csv
import datetime
import io
import socket

import MySQLdb as mysql
import OpenSSL as openssl
from flask import (Response, abort, flash, g, jsonify, redirect,
                   render_template, request, url_for)

import cortex.lib.core
from cortex import app
from cortex.corpus import x509utils
from cortex.lib.user import does_user_have_permission

################################################################################

@app.route('/certificates')
@cortex.lib.user.login_required
def certificates():
	"""Displays the certificates list."""

	# Check user permissions
	if not does_user_have_permission("certificates.view"):
		abort(403)

	# Get arguments with default
	self_signed = request.args.get('self_signed', 'any')
	validity = request.args.get('validity', 'any')
	last_seen = request.args.get('last_seen', None)

	# Build query parts
	query_parts = []
	if self_signed == 'only':
		query_parts.append('`certificate`.`subjectCN` = `certificate`.`issuerCN`')
	elif self_signed == 'not':
		query_parts.append('`certificate`.`subjectCN` != `certificate`.`issuerCN`')
	if validity == 'expired':
		query_parts.append('`certificate`.`notAfter` < NOW()')
	elif validity == 'current':
		query_parts.append('`certificate`.`notAfter` >= NOW()')
	if last_seen is not None:
		if last_seen >= 0:
			query_parts.append('`scan_result`.`when` >= DATE_SUB(NOW(), INTERVAL ' + str(int(last_seen)) + ' DAY)')
		else:
			query_parts.append('`scan_result`.`when` < DATE_SUB(NOW(), INTERVAL ' + str(-int(last_seen)) + ' DAY)')

	# Build where clause from query parts
	where_clause = ''
	if len(query_parts) > 0:
		where_clause = ' WHERE ' + (' AND '.join(query_parts))

	# Build query
	query = 'SELECT `certificate`.`digest` AS `digest`, `certificate`.`subjectCN` AS `subjectCN`, `certificate`.`subjectDN` AS `subjectDN`, `certificate`.`notBefore` AS `notBefore`, `certificate`.`notAfter` AS `notAfter`, `certificate`.`issuerCN` AS `issuerCN`, `certificate`.`issuerDN` AS `issuerDN`, MAX(`scan_result`.`when`) AS `lastSeen`, COUNT(DISTINCT `scan_result`.`host`) AS `numHosts`, `certificate`.`keySize` AS `keySize` FROM `certificate` LEFT JOIN `scan_result` ON `certificate`.`digest` = `scan_result`.`cert_digest`' + where_clause + ' GROUP BY `certificate`.`digest`'

	# Get the list of certificates
	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute(query)
	certs = curd.fetchall()

	return render_template('certificates/certificates.html', active='certificates', title='Certificates', certificates=certs, self_signed=self_signed, validity=validity)

################################################################################

def add_openssl_certificate(cert):
	# pylint: disable=invalid-name
	digest = cert.digest('SHA1').decode('utf-8').replace(':', '').lower()
	subject = cert.get_subject()
	subjectHash = cert.subject_name_hash()
	issuer = cert.get_issuer()
	notAfter = x509utils.parse_zulu_time(cert.get_notAfter())
	notBefore = x509utils.parse_zulu_time(cert.get_notBefore())
	sans = x509utils.get_subject_alt_names(cert)
	keySize = cert.get_pubkey().bits()

	# Extract CN and DNs
	if isinstance(subject, openssl.crypto.X509Name):
		subjectCN = subject.CN
		subjectDN = str(subject)[19:-2]
	else:
		subjectCN = None
		subjectDN = None
	if isinstance(issuer, openssl.crypto.X509Name):
		issuerCN = issuer.CN
		issuerDN = str(issuer)[19:-2]
	else:
		issuerCN = None
		issuerDN = None

	# Write the certificate to the database
	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute('INSERT INTO `certificate` (`digest`, `subjectHash`, `subjectCN`, `subjectDN`, `notBefore`, `notAfter`, `issuerCN`, `issuerDN`, `notify`, `notes`, `keySize`) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "%s")', (digest, subjectHash, subjectCN, subjectDN, notBefore, notAfter, issuerCN, issuerDN, 1, "", keySize))
	for san in sans:
		curd.execute('INSERT INTO `certificate_sans` (`cert_digest`, `san`) VALUES (%s, %s)', (digest, san))
	g.db.commit()

	return digest

################################################################################

@app.route('/certificates/add', methods=['GET', 'POST'])
@cortex.lib.user.login_required
def certificates_add():
	"""Adds a certificate to the list of tracked certificates."""

	if not does_user_have_permission("certificates.add"):
		abort(403)

	if request.method == 'POST':
		# Extract the certificate from the request
		if 'uploaded_cert' in request.files:
			# Read the contents (maximum 1MB so we don't DoS ourselves with large files)
			cert_data = request.files['uploaded_cert'].read(1048576)
		elif 'pasted_cert' in request.form:
			cert_data = request.form['pasted_cert']
		else:
			abort(400)

		last_exception = None
		openssl_cert = None

		# Try loading the certificate as PEM-encoded X509
		try:
			openssl_cert = openssl.crypto.load_certificate(openssl.crypto.FILETYPE_PEM, cert_data)
		except Exception as ex:
			last_exception = ex

		# If that failed and a cert was uploaded rather than pasted,
		# then try PKCS12 instead
		if 'uploaded_cert' in request.files and openssl_cert is None:
			try:
				openssl_p12_cert = openssl.crypto.load_pkcs12(cert_data)
				openssl_cert = openssl_p12_cert.get_certificate()
				if openssl_cert is None:
					openssl_cert = openssl_p12_cert.get_ca_certificates()[0]
					if openssl_cert is None:
						raise Exception("No certificates found in PKCS12 file")
			except Exception as ex:
				last_exception = ex

		# If we failed to read the certificate, return an error
		if openssl_cert is None:
			flash('Error reading certificate: ' + str(last_exception), 'alert-danger')
			return render_template('certificates/add.html', active='certificates', title='Add Certificate')

		try:
			cert_digest = add_openssl_certificate(openssl_cert)
		except Exception as e:
			flash('Error adding certificate: ' + str(e), 'alert-danger')
			return render_template('certificates/add.html', active='certificates', title='Add Certificate')

		# Log which certificate was deleted
		cortex.lib.core.log(__name__, "certificate.delete", "Certificate " + str(cert_digest) + " added")

		flash('Certificate added', category='alert-success')
		return redirect(url_for('certificate_edit', digest=cert_digest))

	# Just show the form
	return render_template('certificates/add.html', active='certificates', title='Add Certificate')

################################################################################

def certificates_download_csv_stream(cursor):
	# Get the first row
	row = cursor.fetchone()

	# Write CSV header
	output = io.StringIO()
	writer = csv.writer(output)
	writer.writerow(['Digest', 'Subject CN', 'Subject DN', 'Issuer CN', 'Issuer DN', 'Not Valid Before', 'Not Valid After', 'Last Seen', 'Host Count', 'SANs', 'Notes', 'Key Size'])
	yield output.getvalue()

	# Write data
	while row is not None:
		# There's no way to flush (and empty) a CSV writer, so we create
		# a new one each time
		output = io.StringIO()
		writer = csv.writer(output)

		# Write a row to the CSV output
		outrow = [row['digest'], row['subjectCN'], row['subjectDN'], row['issuerCN'], row['issuerDN'], row['notBefore'], row['notAfter'], row['lastSeen'], row['numHosts'], row['sans'], row['notes'], row['keySize']]

		# Write the output row to the stream
		writer.writerow(outrow)
		yield output.getvalue()

		# Iterate
		row = cursor.fetchone()

################################################################################

@app.route('/certificates/download/csv')
@cortex.lib.user.login_required
def certificates_download_csv():
	"""Downloads the list of certificates as a CSV file."""

	# Check user permissions
	if not does_user_have_permission("certificates.view"):
		abort(403)

	# Get the list of systems
	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute('SELECT `certificate`.`digest` AS `digest`, `certificate`.`subjectCN` AS `subjectCN`, `certificate`.`subjectDN` AS `subjectDN`, `certificate`.`issuerCN` AS `issuerCN`, `certificate`.`issuerDN` AS `issuerDN`, `certificate`.`notBefore` AS `notBefore`, `certificate`.`notAfter` AS `notAfter`, MAX(`scan_result`.`when`) AS `lastSeen`, COUNT(DISTINCT `scan_result`.`host`) AS `numHosts`, (SELECT GROUP_CONCAT(`san`) FROM `certificate_sans` WHERE `cert_digest` = `certificate`.`digest`) AS `sans`, `certificate`.`notes` AS `notes`, `certificate`.`keySize` AS `keySize` FROM `certificate` LEFT JOIN `scan_result` ON `certificate`.`digest` = `scan_result`.`cert_digest` GROUP BY `certificate`.`digest`;')

	cortex.lib.core.log(__name__, "certificates.csv.download", "CSV of certificates downloaded")

	# Return the response
	return Response(certificates_download_csv_stream(curd), mimetype="text/csv", headers={'Content-Disposition': 'attachment; filename="certificates.csv"'})

################################################################################

@app.route('/certificate/<digest>', methods=['GET', 'POST'])
@cortex.lib.user.login_required
def certificate_edit(digest):
	"""Displays information about a certificate."""

	# Check user permissions
	if not does_user_have_permission("certificates.view"):
		abort(403)

	if request.method == 'POST':
		# Check for an action
		if 'action' not in request.form or request.form.get("action") not in ["delete", "toggle_notify", "save_notes"]:
			abort(400)
		# Delete Certificate action
		if request.form['action'] == 'delete':
			try:
				# Get the certificate
				curd = g.db.cursor(mysql.cursors.DictCursor)
				curd.execute('SELECT `subjectDN` FROM `certificate` WHERE `digest` = %s', (digest,))
				certificate = curd.fetchone()

				# If the certificate was not found then notify the user
				if certificate is None:
					raise Exception('Certificate does not exist')

				# Delete the certificate
				curd = g.db.cursor(mysql.cursors.DictCursor)
				curd.execute('DELETE FROM `certificate` WHERE `digest` = %s', (digest,))
				g.db.commit()

				# Log which certificate was deleted
				cortex.lib.core.log(__name__, "certificate.delete", "Certificate " + str(digest) + " (" + str(certificate['subjectDN']) + ") deleted")

				# Notify user
				flash('Certificate deleted', category='alert-success')
			except Exception as e:
				flash('Failed to delete certificate: ' + str(e), category='alert-danger')

			return redirect(url_for('certificates'))
		# Toggle notifications action
		if request.form['action'] == 'toggle_notify':
			try:
				# Get the certificate
				curd = g.db.cursor(mysql.cursors.DictCursor)
				curd.execute('SELECT `subjectDN` FROM `certificate` WHERE `digest` = %s', (digest,))
				certificate = curd.fetchone()

				# If the certificate was not found then notify the user
				if certificate is None:
					raise Exception('Certificate does not exist')

				# Update the certificate notify parameter
				curd = g.db.cursor(mysql.cursors.DictCursor)
				curd.execute('UPDATE `certificate` SET `notify` = NOT(`notify`) WHERE `digest` = %s', (digest,))
				g.db.commit()

				# Log
				cortex.lib.core.log(__name__, "certificate.notify", "Certificate " + str(digest) + " (" + str(certificate['subjectDN']) + ") notification changed")
			except Exception as e:
				flash('Failed to change certificate notification: ' + str(e), category='alert-danger')

			return redirect(url_for('certificate_edit', digest=digest))
		if request.form['action'] == 'save_notes':
			# Get the certificate
			curd = g.db.cursor(mysql.cursors.DictCursor)
			curd.execute('SELECT `subjectDN` FROM `certificate` WHERE `digest` = %s', (digest,))
			certificate = curd.fetchone()

			# If the certificate was not found then return appropriate response
			if certificate is None:
				abort(404)

			# Update the certificate notify parameter
			curd = g.db.cursor(mysql.cursors.DictCursor)
			curd.execute('UPDATE `certificate` SET `notes` = %s WHERE `digest` = %s', (request.form['notes'], digest,))
			g.db.commit()

			# Log
			cortex.lib.core.log(__name__, "certificate.notes", "Certificate " + str(digest) + " (" + str(certificate['subjectDN']) + ") notes updated")

			# Return empty 200 response
			return ""

	# Get the list of certificates
	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute('SELECT `certificate`.`digest` AS `digest`, `certificate`.`subjectCN` AS `subjectCN`, `certificate`.`subjectDN` as `subjectDN`, `certificate`.`notBefore` AS `notBefore`, `certificate`.`notAfter` AS `notAfter`, `certificate`.`issuerCN` AS `issuerCN`, `certificate`.`issuerDN` as `issuerDN`, `certificate`.`notify`, MAX(`scan_result`.`when`) AS `lastSeen`, `certificate`.`notes` AS `notes`, `certificate`.`keySize` AS `keySize` FROM `certificate` LEFT JOIN `scan_result` ON `certificate`.`digest` = `scan_result`.`cert_digest` WHERE `certificate`.`digest` = %s GROUP BY `certificate`.`digest`', (digest,))
	certificate = curd.fetchone()

	if certificate is None:
		abort(404)

	curd.execute('SELECT `san` FROM `certificate_sans` WHERE `cert_digest` = %s', (digest,))
	sans = curd.fetchall()

	curd.execute('SELECT `host`, `port`, `when`, `chain_state` FROM `scan_result` WHERE `cert_digest` = %s', (digest,))
	scan_results = curd.fetchall()

	return render_template('certificates/certificate.html', active='certificates', title='Certificates', certificate=certificate, sans=sans, scan_results=scan_results)

################################################################################

@app.route('/certificates/statistics')
@cortex.lib.user.login_required
def certificate_statistics():
	"""Displays some statistics about discovered certificates."""

	# Check user permissions
	if not does_user_have_permission("certificates.stats"):
		abort(403)

	if 'days' in request.args:
		days = int(request.args['days'])
	else:
		days = 30

	# Get a cursor
	curd = g.db.cursor(mysql.cursors.DictCursor)

	# Get the total number of discovered certificates
	curd.execute('SELECT COUNT(*) AS `count` FROM `certificate`')
	result = curd.fetchone()
	total_certs = result['count']

	# Get the top 10 certificate issuers
	curd.execute('SELECT `issuerCN`, COUNT(*) AS `count` FROM `certificate` GROUP BY `issuerDN` ORDER BY `count` DESC LIMIT 10')
	result = curd.fetchall()
	cert_provider_stats = {}
	for row in result:
		cert_provider_stats[row['issuerCN']] = row['count']
	cert_provider_stats['Other'] = total_certs - sum([cert_provider_stats[p] for p in cert_provider_stats])

	# Get the number of certificates expiring per day for the next 30 days
	cert_expiry_stats = []
	date_start = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
	for day in range(0, days):
		day_start = (date_start + datetime.timedelta(days=day)).strftime("%Y-%m-%d")
		day_end = (date_start + datetime.timedelta(days=day+1)).strftime("%Y-%m-%d")
		curd.execute('SELECT COUNT(*) AS `count` FROM `certificate` WHERE DATE(`notAfter`) >= %s AND DATE(`notAfter`) < %s;', (day_start, day_end))
		result = curd.fetchone()
		cert_expiry_stats.append({'date': day_start, 'count': result['count']})

	# Get the number of unique certificates seen per day
	curd.execute('SELECT `when_date`, COUNT(*) AS `count` FROM (SELECT DATE(`when`) AS `when_date`, `cert_digest`, COUNT(*) FROM `scan_result` GROUP BY `when_date`, `cert_digest`) `inner` GROUP BY `when_date` ORDER BY `when_date`;')
	result = curd.fetchall()
	cert_seen_stats = {}
	for row in result:
		cert_seen_stats[row['when_date']] = row['count']

	return render_template('certificates/statistics.html', active='certificates', title='Certificate Statistics', total_certs=total_certs, cert_provider_stats=cert_provider_stats, cert_expiry_stats=cert_expiry_stats, cert_seen_stats=cert_seen_stats, days=days)

################################################################################

@app.route('/certificates/ajax/iplookup')
@cortex.lib.user.login_required
def certificate_ip_lookup():
	ip = request.args['ip']

	result = {'success': 0}
	try:
		result['ip'] = ip
		result['hostname'] = socket.gethostbyaddr(ip)[0]
		result['success'] = 1
	except Exception:
		pass

	return jsonify(result)
