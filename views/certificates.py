#!/usr/bin/python

from cortex import app
import cortex.lib.core
from cortex.lib.user import does_user_have_permission
from flask import Flask, request, redirect, url_for, flash, g, abort, render_template, Response
import datetime, csv, io
import MySQLdb as mysql

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
	query = 'SELECT `certificate`.`digest` AS `digest`, `certificate`.`subjectCN` AS `subjectCN`, `certificate`.`notBefore` AS `notBefore`, `certificate`.`notAfter` AS `notAfter`, `certificate`.`issuerCN` AS `issuerCN`, MAX(`scan_result`.`when`) AS `lastSeen`, COUNT(DISTINCT `scan_result`.`host`) AS `numHosts` FROM `certificate` JOIN `scan_result` ON `certificate`.`digest` = `scan_result`.`cert_digest`' + where_clause + ' GROUP BY `certificate`.`digest`'

	# Get the list of certificates
	curd = g.db.cursor(mysql.cursors.DictCursor)
	curd.execute(query)
	certificates = curd.fetchall()
	
	return render_template('certificates/certificates.html', active='certificates', title='Certificates', certificates=certificates)

################################################################################

def certificates_download_csv_stream(cursor):
	# Get the first row
	row = cursor.fetchone()

	# Write CSV header
	output = io.BytesIO()
	writer = csv.writer(output)
	print str(['Digest', 'Subject CN', 'Subject DN', 'Issuer CN', 'Issuer DN', 'Not Valid Before', 'Not Valid After', 'Last Seen', 'Host Count', 'SANs'])
	writer.writerow(['Digest', 'Subject CN', 'Subject DN', 'Issuer CN', 'Issuer DN', 'Not Valid Before', 'Not Valid After', 'Last Seen', 'Host Count', 'SANs'])
	yield output.getvalue()

	# Write data
	while row is not None:
		# There's no way to flush (and empty) a CSV writer, so we create
		# a new one each time
		output = io.BytesIO()
		writer = csv.writer(output)

		# Write a row to the CSV output
		outrow = [row['digest'], row['subjectCN'], row['subjectDN'], row['issuerCN'], row['issuerDN'], row['notBefore'], row['notAfter'], row['lastSeen'], row['numHosts'], row['sans']]
		print str(outrow)

		# For each element in the output row...
		for i in range(0, len(outrow)):
			# ...if it's not None...
			if outrow[i]:
				# ...if the element is unicode...
				if type(outrow[i]) == unicode:
					# ...decode from utf-8 into a ASCII-compatible byte string
					outrow[i] = outrow[i].encode('utf-8')
				else:
					# ...otherwise just chuck it out as a string
					outrow[i] = str(outrow[i])

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
	curd.execute('SELECT `certificate`.`digest` AS `digest`, `certificate`.`subjectCN` AS `subjectCN`, `certificate`.`subjectDN` AS `subjectDN`, `certificate`.`issuerCN` AS `issuerCN`, `certificate`.`issuerDN` AS `issuerDN`, `certificate`.`notBefore` AS `notBefore`, `certificate`.`notAfter` AS `notAfter`, MAX(`scan_result`.`when`) AS `lastSeen`, COUNT(DISTINCT `scan_result`.`host`) AS `numHosts`, (SELECT GROUP_CONCAT(`san`) FROM `certificate_sans` WHERE `cert_digest` = `certificate`.`digest`) AS `sans` FROM `certificate` LEFT JOIN `scan_result` ON `certificate`.`digest` = `scan_result`.`cert_digest` GROUP BY `certificate`.`digest`;')

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

	if request.method == 'GET':
		# Get the list of certificates
		curd = g.db.cursor(mysql.cursors.DictCursor)
		curd.execute('SELECT `certificate`.`digest` AS `digest`, `certificate`.`subjectCN` AS `subjectCN`, `certificate`.`subjectDN` as `subjectDN`, `certificate`.`notBefore` AS `notBefore`, `certificate`.`notAfter` AS `notAfter`, `certificate`.`issuerCN` AS `issuerCN`, `certificate`.`issuerDN` as `issuerDN`, `certificate`.`notify`, MAX(`scan_result`.`when`) AS `lastSeen` FROM `certificate` JOIN `scan_result` ON `certificate`.`digest` = `scan_result`.`cert_digest` WHERE `certificate`.`digest` = %s GROUP BY `certificate`.`digest`', (digest,))
		certificate = curd.fetchone()

		if certificate is None:
			abort(404)

		curd.execute('SELECT `san` FROM `certificate_sans` WHERE `cert_digest` = %s', (digest,));
		sans = curd.fetchall()

		curd.execute('SELECT `host`, `port`, `when`, `chain_state` FROM `scan_result` WHERE `cert_digest` = %s', (digest,))
		scan_results = curd.fetchall()

		return render_template('certificates/certificate.html', active='certificates', title='Certificates', certificate=certificate, sans=sans, scan_results=scan_results)
	elif request.method == 'POST':
		# Check for an action
		if 'action' in request.form:
			# Delete Certificate action
			if request.form['action'] == 'delete':
				try:
					# Delete the certificate
					curd = g.db.cursor(mysql.cursors.DictCursor)
					curd.execute('DELETE FROM `certificate` WHERE `digest` = %s', (digest,))
					g.db.commit()

					# Log
					cortex.lib.core.log(__name__, "certificate.delete", "Certificate " + str(digest) + " deleted")

					# Notify user
					flash('Certificate deleted', category='alert-success')
				except Exception as e:
					flash('Failed to delete certificate: ' + str(e), category='alert-danger')

				return redirect(url_for('certificates'))
			# Toggle notifications action
			elif request.form['action'] == 'toggle_notify':
				try:
					# Update the certificate notify parameter
					curd = g.db.cursor(mysql.cursors.DictCursor)
					curd.execute('UPDATE `certificate` SET `notify` = NOT(`notify`) WHERE `digest` = %s', (digest,))
					g.db.commit()

					# Log
					cortex.lib.core.log(__name__, "certificate.notify", "Certificate " + str(digest) + " notification changed")
				except Exception as e:
					flash('Failed to change certificate notification: ' + str(e), category='alert-danger')

				return redirect(url_for('certificate_edit', digest=digest))
			else:
				return abort(400)
		else:
			return abort(400)

@app.route('/certificates/statistics')
@cortex.lib.user.login_required
def certificate_statistics():
	"""Displays some statistics about discovered certificates."""

	# Check user permissions
	if not does_user_have_permission("certificates.stats"):
		abort(403)

	# Get a cursor
	curd = g.db.cursor(mysql.cursors.DictCursor)

	# Get the total number of discovered certificates
	curd.execute('SELECT COUNT(*) AS `count` FROM `certificate`')
	result = curd.fetchone()
	total_certs = result['count']

	# Get the top 10 certificate issuers
	curd.execute('SELECT `issuerCN`, COUNT(*) AS `count` FROM `certificate` GROUP BY `issuerDN` ORDER BY `count` DESC LIMIT 10');
	result = curd.fetchall()
	cert_provider_stats = {}
	for row in result:
		cert_provider_stats[row['issuerCN']] = row['count']
	cert_provider_stats['Other'] = total_certs - sum([cert_provider_stats[p] for p in cert_provider_stats])

	# Get the number of certificates expiring per day for the next 30 days
	cert_expiry_stats = []
	date_start = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
	for day in range(0, 30):
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

	return render_template('certificates/statistics.html', active='certificates', title='Certificate Statistics', total_certs=total_certs, cert_provider_stats=cert_provider_stats, cert_expiry_stats=cert_expiry_stats, cert_seen_stats=cert_seen_stats)
