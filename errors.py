#!/usr/bin/python
#

from cortex import app
import cortex.core
from flask import Flask, request, session, g, redirect, url_for, abort, flash, render_template
import traceback

def debugError(msg):
	return output_error("Debug Message",msg)

#### Output error handler
## outputs a template error page, or if redirect is set, redirects with a popup
## error set on the users' session so it pops up a modal dialog after redirect
def output_error(title,message,redirect_to=None):
	"""This function is called by other error functions to show the error to the
	end user. It takes a title, message and a further error type. If redirect
	is set then rather than show an error it will return the 'redirect' after
	setting the popup error flags so that after the redirect a popup error is 
	shown to the user. Redirect should be a string returned from flask redirect().
	"""
	
	debug = ''
	
	if app.debug:
		if app.config['DEBUG_FULL_ERRORS']:
			debug = traceback.format_exc()
			redirect_to = None
			
	if redirect_to == None:
		## Render an error page
		return render_template('error.html',title=title,message=message,debug=debug), 200
	else:
		## Set error popup and return
		cortex.core.poperr_set(title,message)
		return redirect_to

################################################################################
#### Flask error handlers - captures "abort" calls from within flask and our code

def fatal(title="Fatal Error",message="Default Message"):
	g.fault_title = title
	g.fault_message = message
	abort(500)

@app.errorhandler(500)
def error500(error):
	"""Handles abort(500) calls in code.
	"""
	
	# Default error title/msg
	err_title  = "Internal Error"
	err_msg    = "An internal error has occured and has been forwarded to our support team."
	
	# Take title/msg from global object if set
	if hasattr(g, 'fault_title'):
		err_title = g.fault_title
	if hasattr(g, 'fault_message'):
		err_msg = g.fault_message

	# Handle errors when nobody is logged in
	if 'username' in session:
		usr = session['username']
	else:
		usr = 'Not logged in'
		
	# Get exception traceback
	if app.debug:
		debug = traceback.format_exc()
	else:
		debug = None

	## send a log about this
	app.logger.error("""
Title:                %s
Message:              %s
Exception Type:       %s
Exception Message:    %s
HTTP Path:            %s
HTTP Method:          %s
Client IP Address:    %s
User Agent:           %s
User Platform:        %s
User Browser:         %s
User Browser Version: %s
Username:             %s

Traceback:

%s

""" % (
			err_title,
			err_msg,
			str(type(error)),
			error.__str__(),
			request.path,
			request.method,
			request.remote_addr,
			request.user_agent.string,
			request.user_agent.platform,
			request.user_agent.browser,
			request.user_agent.version,
			usr,
			debug,	
		))
		
	return render_template('error.html',title=err_title,message=err_msg,debug=debug), 500

@app.errorhandler(400)
def error400(error):
	"""Handles abort(400) calls in code.
	"""
	if app.debug:
		debug = traceback.format_exc()
	else:
		debug = None
		
	app.logger.info('abort400 was called! ' + str(debug))
		
	return render_template('error.html',title="Bad Request",message='Your request was invalid, please try again.',debug=debug), 400

@app.errorhandler(403)
def error403(error):
	"""Handles abort(403) calls in code.
	"""
	
	if app.debug:
		debug = traceback.format_exc()
	else:
		debug = None
		
	app.logger.info('abort403 was called!')
	
	return render_template('error.html',title="Permission Denied",message='You do not have permission to access this resource.',debug=debug), 403

@app.errorhandler(404)
def error404(error):
	"""Handles abort(404) calls in code.
	"""

	if app.debug:
		debug = traceback.format_exc()
	else:
		debug = None

	return render_template('error.html',title="Not found",message="Sorry, I couldn't find what you requested.",debug=debug), 404

@app.errorhandler(405)
def error405(error):
	"""Handles abort(405) calls in code.
	"""
	
	if app.debug:
		debug = traceback.format_exc()
	else:
		debug = None
	
	return render_template('error.html',title="Not allowed",message="Method not allowed. This usually happens when your browser sent a POST rather than a GET, or vice versa.",debug=debug), 405

################################################################################
#### TEST ERROR PAGES

@app.route('/err/<int:number>')
def error_test(number):
	if app.debug:
		abort(number)
	else:
		return redirect(url_for('login'))
