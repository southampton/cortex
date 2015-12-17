from cortex import app
import cortex.core
from flask import Flask, request, session, redirect, url_for, flash, g, abort, make_response, jsonify
import os 
import re
import MySQLdb as mysql
import yaml

@app.route('/api/puppet/enc/<certname>')
def api_puppet_enc(certname):
	"""Returns the YAML associated with the given node."""

	# Make a response
	r = make_response(cortex.puppet.puppet_generate_config(certname))
	r.headers['Content-Type'] = "application/x-yaml"

	return r
