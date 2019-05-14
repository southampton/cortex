#!/usr/bin/python

from cortex import app
import cortex.lib.core
from cortex.lib.user import does_user_have_permission, does_user_have_system_permission
from cortex.lib.errors import stderr
from flask import Flask, request, session, redirect, url_for, flash, g, abort, make_response, render_template, jsonify
import os
import MySQLdb as mysql

################################################################################

@app.route('/ssl/certificates')
@cortex.lib.user.login_required
def ssl_certificates():
	"""Displays the certificates list."""

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
	
	return render_template('ssl/certificates.html', active='ssl', title='SSL Certificates', certificates=certificates)

@app.route('/ssl/certificate/<digest>', methods=['GET', 'POST'])
@cortex.lib.user.login_required
def ssl_certificate_edit(digest):
	"""Displays information about a certificate."""

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

		return render_template('ssl/certificate.html', active='ssl', title='SSL Certificates', certificate=certificate, sans=sans, scan_results=scan_results)
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

					# Notify user
					flash('Certificate deleted', category='alert-success')
				except Exception as e:
					flash('Failed to delete certificate: ' + str(e), category='alert-danger')

				return redirect(url_for('ssl_certificates'))
		else:
			return abort(400)
