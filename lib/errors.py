#!/usr/bin/python
# -*- coding: utf-8 -*-

from cortex import app
from flask import g, render_template, make_response, session, request
import traceback

################################################################################

## standard error (uses render_template and thus standard page layout)
def stderr(title,message,code=200,template="error.html"):
	"""This function is called by other error functions to show the error to the
	end user. It takes an error title and an error message.
	"""

	# Should we show a traceback?	
	if app.debug:
		debug = traceback.format_exc()
	else:
		debug = ""

	return render_template(template,title=title,message=message,debug=debug), code

################################################################################

## fatal error (returns HTML from python code - which is more likely to work)
def fatalerr(title="Totes not an error ;)",message="While processing your request an unexpected error occured which the application could not recover from",debug=None):

	# Should we show a traceback?	
	if debug is None:
		if app.debug:
			debug = traceback.format_exc()
		else:
			debug = "Please ask your administrator to consult the error log for more information."

	# Build the response. Not using a template here to prevent any Jinja 
	# issues from causing this to fail.
	html = """
<!doctype html>
<html>
<head>
	<title>Fatal Error</title>
	<meta charset="utf-8" />
	<meta http-equiv="Content-type" content="text/html; charset=utf-8" />
	<meta name="viewport" content="width=device-width, initial-scale=1" />
	<style type="text/css">
	body {
		background-color: #188B20;
		color: #FFFFFF;
		margin: 0;
		padding: 0;
		font-family: "Open Sans", "Helvetica Neue", Helvetica, Arial, sans-serif;
	}
	h1 {
		font-size: 4em;
		font-weight: normal;
		margin: 0px;
	}
	div {
		width: 80%%;
		margin: 5em auto;
		padding: 50px;
		border-radius: 0.5em;
	}
	@media (max-width: 900px) {
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
	<h1>%s</h1>
	<p>%s</p>
	<pre>%s</pre>
</div>
</body>
</html>
""" % (title,message,debug)

	return make_response(html, 500)

################################################################################

## log a full error to the python logger
def logerr():

	# Get the username
	if 'username' in session:
		username = session['username']
	else:
		username = 'Not logged in'

	## Log the critical error (so that it goes to e-mail)
	app.logger.error("""Request details:
HTTP Host:            %s
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
			request.host,
			request.path,
			request.method,
			request.remote_addr,
			request.user_agent.string,
			request.user_agent.platform,
			request.user_agent.browser,
			request.user_agent.version,
			username,
			traceback.format_exc(),	
		))
