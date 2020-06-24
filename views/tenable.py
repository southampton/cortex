"""
Views for the Cortex Tenable.io / Nessus Integration
"""

from flask import Blueprint, current_app, jsonify, render_template, request

import cortex.lib.tenable
import cortex.lib.user
from cortex.views.systems import _systems_extract_datatables

tenable = Blueprint("tenable", __name__, url_prefix="/tenable")

@tenable.route("/api/<path:api_path>", methods=["GET", "POST"])
@cortex.lib.user.login_required
def tenable_api(api_path):

	# Extract the request data and remove the CSRF token before proxying
	request_data = request.form.to_dict()
	request_data.pop("_csrf_token", None)

	# Make a request to the Tenable.io API
	tio = cortex.lib.tenable.tio_connect()
	return jsonify(tio.api(
		api_path,
		method = request.method,
		params = request.args,
		data = request_data,
	))

@tenable.route("/agents")
@cortex.lib.user.login_required
def tenable_assets():
	return render_template("tenable/agents.html")

@tenable.route("/agents/json", methods=["POST"])
@cortex.lib.user.login_required
def tenable_agents_json():
	tio = cortex.lib.tenable.tio_connect()

	# Extract information from DataTables
	# TODO: Move this extract function to a general lib
	(draw, start, length, order_column, order_asc, search) = _systems_extract_datatables()

	# Define order and direction for sorting.
	sort_col = {
		0: "name",
		1: "status",
		2: "ip",
		3: "platform",
		4: "distro",
		5: "core_version",
		6: "last_scanned",
	}.get(order_column, "name")
	sort_dir = "asc" if order_asc else "desc"

	# Build Params
	params = {
			"limit":  length,
			"offset": start,
			"sort": "{sort_col}:{sort_dir}".format(sort_col=sort_col, sort_dir=sort_dir)
	}

	# Add Search
	if search:
		params["w"] = search,
		params["wf"] = ",".join(["name", "ip", "platform", "distro"]),

	# Make a request to the Tenable.io API and GET agents
	tio = cortex.lib.tenable.tio_connect()
	data = tio.api(
		"scanners/1/agents",
		params = params,
	)

	return jsonify(draw=draw, recordsTotal=data["pagination"]["total"], recordsFiltered=data["pagination"]["total"], data=data["agents"])
