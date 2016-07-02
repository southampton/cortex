#!/usr/bin/python
#

from cortex import app
from flask import Flask, request, session, g, redirect, url_for, abort, flash, render_template, make_response
import traceback

################################################################################

@app.errorhandler(500)
def error500(error):
	"""Handles abort(500) calls in code."""
	
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

	# Send a log about this
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
		
	return render_template('error.html', title=err_title, message=err_msg, debug=debug), 500

################################################################################

@app.errorhandler(400)
def error400(error):
	"""Handles abort(400) calls in code."""

	if app.debug:
		debug = traceback.format_exc()
	else:
		debug = None
		
	app.logger.info('abort400 was called! ' + str(debug))
		
	return render_template('error.html', title="Bad Request", message='Your request was invalid, please try again.', debug=debug), 400

################################################################################

@app.errorhandler(403)
def error403(error):
	"""Handles abort(403) calls in code."""
	
	if app.debug:
		debug = traceback.format_exc()
	else:
		debug = None
		
	app.logger.info('abort403 was called!')
	
	return render_template('error.html', title="Permission Denied", message='You do not have permission to access this resource.', debug=debug), 403

################################################################################

@app.errorhandler(404)
def error404(error):
	"""Handles abort(404) calls in code."""

	if app.debug:
		debug = traceback.format_exc()
	else:
		debug = None

	return render_template('error.html', title="Not found", message="Sorry, I couldn't find what you requested.", debug=debug), 404

################################################################################

@app.errorhandler(405)
def error405(error):
	"""Handles abort(405) calls in code."""
	
	if app.debug:
		debug = traceback.format_exc()
	else:
		debug = None
	
	return render_template('error.html', title="Not allowed", message="Method not allowed. This usually happens when your browser sent a POST rather than a GET, or vice versa.", debug=debug), 405

################################################################################

@app.errorhandler(Exception)
def error_handler(error):
	"""Handles generic exceptions within the application, displaying the
	traceback if the application is running in debug mode."""

	# Get the traceback
	trace = str(traceback.format_exc())
	if app.debug:
		debug = trace
	else:
		debug = "Debug output disabled. Ask your system administrator to consult the error log for more information"

	# Build the response. Not using a template here to prevent any Jinja 
	# issues from causing this to fail.
	error_resp = """
<!doctype html>
<html>
<head>
    <title>Cortex - Critical Error</title>
    <meta charset="utf-8" />
    <meta http-equiv="Content-type" content="text/html; charset=utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <style type="text/css">
    body {
        background-color: #f0f0f2;
        margin: 0;
        padding: 0;
        font-family: "Open Sans", "Helvetica Neue", Helvetica, Arial, sans-serif;
    }
    div {
        width: 800px;
        margin: 5em auto;
        padding: 50px;
        background-color: #fff;
        border-radius: 1em;
    }
    @media (max-width: 900px) {
        body {
            background-color: #fff;
        }
        div {
            width: auto;
            margin: 0 auto;
            border-radius: 0;
            padding: 1em;
        }
    }
    </style>    
</head>
<body>
<div>
    <h1>Cortex critical error</h1>
    <p>Whilst processing your request an error occured that could not be interpreted.</p>
	<pre>%s</pre>
</div>
</body>
</html>
""" % (debug)

	if 'username' in session:
		usr = session['username']
	else:
		usr = 'Not logged in'

	app.logger.error("""Critical Error!
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

			request.path,
			request.method,
			request.remote_addr,
			request.user_agent.string,
			request.user_agent.platform,
			request.user_agent.browser,
			request.user_agent.version,
			usr,
			trace,			
		))

	return make_response(error_resp, 500)
