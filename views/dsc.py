from cortex import app
import cortex.lib.core
import cortex.lib.systems
import cortex.lib.cmdb
import cortex.lib.classes
from cortex.lib.user import does_user_have_permission, does_user_have_system_permission, does_user_have_any_system_permission
from cortex.corpus import Corpus
from flask import Flask, request, session, redirect, url_for, flash, g, abort, make_response, render_template, jsonify, Response
import os
import time
import datetime
import json
import re
import werkzeug
import MySQLdb as mysql
import yaml
import csv
import io
import requests
import cortex.lib.rubrik
from flask.views import MethodView
from pyVmomi import vim

@app.route('/dsc/classify/<id>', methods=['GET', 'POST'])
@cortex.lib.user.login_required
def dsc_classify_machine(id):

	system = cortex.lib.systems.get_system_by_id(id)
	# return jsonify(system)

	if system == None:
		abort(404)


	if request.method == 'GET':
		# TODO: Add in permissions
		return render_template('dsc/classify.html', title="DSC", system=system, active='dsc')




	return render_template('dsc/classify.html')