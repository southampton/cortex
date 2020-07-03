# -*- coding: utf-8 -*-

import traceback

from flask import g

from cortex import app
from cortex.lib.errors import fatalerr, logerr, stderr

################################################################################

@app.errorhandler(500)
@app.route('/err500')
def error500(error=None):
	
	# Record the error in the log
	logerr()	

	# Return a standard error page		
	return stderr("Internal Error", "An internal server error occured", 500)

################################################################################

@app.errorhandler(400)
def error400(error=None):
	return stderr("Bad Request", "Your request was invalid", 400)

@app.errorhandler(403)
def error403(error=None):
	return stderr("Permission Denied", "You do not have permission to access that page or perform that action.", 403, template="no.html")

@app.errorhandler(404)
def error404(error=None):
	return stderr("Not found", "I could not find what you requested", 404)

@app.errorhandler(405)
def error405(error=None):
	return stderr("Not allowed", "Your web browser sent the wrong HTTP method", 405, template="no.html")

################################################################################

@app.errorhandler(Exception)
def error_handler(error):
	"""Handles generic exceptions within the application, displaying the
	traceback if the application is running in debug mode."""

	# Record the error in the log
	logerr()

	## If we're handling a workflow view handler we don't need to show the fatal
	## error screen, instead we'll use a standard error screen. the fatal error
	## screen exists in case a flaw occurs which prevents rendering of the 
	## layout - but that can't happen with a workflow.
	if 'workflow' in g:
		if g.workflow:
			app.logger.warn("Workflow error occured")
			return stderr("Workflow error","An error occured in the workflow function - " + type(error).__name__ + ": " + str(error))

	# Get the traceback
	if app.debug:
		debug = traceback.format_exc()
	else:
		debug = "Ask your system administrator to consult the error log for this application."

	# Output a fatal error
	return fatalerr(debug=debug)

################################################################################
