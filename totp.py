#!/usr/bin/python
#
# This file is part of Cortex.
#
# Cortex is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Cortex is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Cortex.  If not, see <http://www.gnu.org/licenses/>.

# pip install onetimepass
# pip install pyqrcode

from cortex import app
import cortex.core
import os
import base64
from redis import Redis
from flask import g, Flask, session, render_template, redirect, url_for, request, flash, abort
import onetimepass
import pyqrcode
import StringIO

def totp_generate_secret_key():
	return base64.b32encode(os.urandom(10)).decode('utf-8')

def totp_get_secret_key(userid):
	return g.redis.get('totp.%s.key' % userid)

def totp_get_uri(userid):
	## check the user has a key, if not generate it.
	otp_secret = totp_get_secret_key(userid)

	if otp_secret == None:
		otp_secret = totp_generate_secret_key()
		g.redis.set('totp.%s.key' % userid,otp_secret)

	return 'otpauth://totp/{0}?secret={1}&issuer={2}'.format(session['username'], otp_secret, app.config['TOTP_IDENT'])

def totp_verify_token(userid, token):
	otp_secret = totp_get_secret_key(userid)

	if otp_secret == None:
		return False
	else:
		return onetimepass.valid_totp(token, otp_secret)

def totp_return_qrcode(userid):
    url = pyqrcode.create(totp_get_uri(userid))
    stream = StringIO.StringIO()
    url.svg(stream, scale=5)
    return stream.getvalue().encode('utf-8'), 200, {
        'Content-Type': 'image/svg+xml',
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0'}

def totp_user_enabled(userid):
	totp_enable = g.redis.get('totp.%s.enabled' % userid)

	if totp_enable == None:
		return False
	else:
		return True

################################################################################

@app.route('/totp_qrcode_img')
@cortex.core.login_required
def totp_qrcode_view():
	if not totp_user_enabled(session['username']):
		return totp_return_qrcode(session['username'])
	else:
		abort(403)

@app.route('/2step', methods=['GET','POST'])
@cortex.core.login_required
def totp_user_view():
	if not totp_user_enabled(session['username']):
		if request.method == 'GET':
			return render_template('totp_enable.html',active="user")
		elif request.method == 'POST':
			## verify the token entered
			token = request.form['totp_token']

			if totp_verify_token(session['username'],token):
				flash("Two step logon has been enabled for your account","alert-success")
				g.redis.set('totp.%s.enabled' % session['username'],"True")
			else:
				flash("Invalid code! Two step logons could not be enabled","alert-danger")
	
			return redirect(url_for('totp_user_view'))
				
	else:
		if request.method == 'GET':
			return render_template('totp_disable.html',active="user")
		elif request.method == 'POST':

			## verify the token entered
			token = request.form['totp_token']

			if totp_verify_token(session['username'],token):
				g.redis.delete('totp.%s.enabled' % session['username'])
				g.redis.delete('totp.%s.key' % session['username'])
				flash("Two step logons have been disabled for your account","alert-warning")
			else:
				flash("Invalid code! Two step logons were not disabled","alert-danger")
	
			return redirect(url_for('totp_user_view'))

@app.route('/verify2step', methods=['GET','POST'])
def totp_logon_view():
	if request.method == 'GET':
		return render_template('totp_verify.html',active="user")
	elif request.method == 'POST':
		## verify the token entered
		token = request.form['totp_token']

		if totp_verify_token(session['username'],token):
			return cortex.core.logon_ok()
		else:
			flash("Invalid two step code!","alert-danger")
			return redirect(url_for('totp_logon_view'))
			
