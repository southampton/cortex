"""
Views for the Cortex Tenable.io / Nessus Integration
"""

from flask import Blueprint, jsonify, render_template, request

import cortex.lib.errors
import cortex.lib.systems
import cortex.lib.tenable
import cortex.lib.user
from cortex.views.systems import _systems_extract_datatables

tenable = Blueprint("tenable", __name__, url_prefix="/tenable")

## Error Handlers

@tenable.app_errorhandler(cortex.lib.tenable.TenableIOHttpError)
def error_TenableIOHttpError(error=None):

	status_code = error.response.status_code if error and error.response and error.response.status_code else 400
	message = str(error) if error else "Your request was invalid"
	return cortex.lib.errors.stderr("Tenable.io HTTP Request Error", message, status_code)

## Views

@tenable.route("/api/<path:api_path>", methods=["GET", "POST"])
@cortex.lib.user.login_required
def tenable_api(api_path):
	"""Route for proxying API requests to Tenable.io"""

	# Check user permissions
	if not cortex.lib.user.does_user_have_permission("tenable.view"):
		abort(403)

	# Extract the request data and remove the CSRF token before proxying
	request_data = request.form.to_dict()
	request_data.pop("_csrf_token", None)

	# Ensure the request is valid and whitelisted!
	tio = cortex.lib.tenable.tio_connect()
	tio.validate_api_path(api_path)

	# Make a request to the Tenable.io API
	return jsonify(tio.api(
		api_path,
		method = request.method,
		params = request.args,
		data = request_data,
	))

@tenable.route("/assets")
@cortex.lib.user.login_required
def tenable_assets():
	"""Tenable.io Assets"""

	# Check user permissions
	if not cortex.lib.user.does_user_have_permission("tenable.view"):
		abort(403)

	return render_template("tenable/assets.html")

@tenable.route("/assets/<string:asset_id>")
@cortex.lib.user.login_required
def tenable_asset(asset_id):
	"""Tenable.io Asset Information"""

	# Check user permissions
	if not cortex.lib.user.does_user_have_permission("tenable.view"):
		abort(403)

	return render_template("tenable/asset.html", title="Asset Information", asset_id=asset_id)

@tenable.route("/systems/<int:system_id>/view")
@cortex.lib.user.login_required
def system_view(system_id):
	"""Tenable.io Asset Information - from node/system tab"""

	# Check user permissions
	if not (cortex.lib.user.does_user_have_system_permission(system_id, "view.detail", "systems.all.view") and cortex.lib.user.does_user_have_permission("tenable.view")):
		abort(403)

	# Get the system
	system = cortex.lib.systems.get_system_by_id(system_id)

	# Ensure that the system actually exists, and return a 404 if it doesn't
	if system is None:
		abort(404)

	return render_template("tenable/system_view.html", title=system["name"], system=system)

@tenable.route("/agents")
@cortex.lib.user.login_required
def tenable_agents():
	"""Registered Nessus agents on Tenable.io"""

	# Check user permissions
	if not cortex.lib.user.does_user_have_permission("tenable.view"):
		abort(403)

	return render_template("tenable/agents.html")

@tenable.route("/agents/json", methods=["POST"])
@cortex.lib.user.login_required
def tenable_agents_json():
	"""Datatables API for Nessus agents on Tenable.io"""

	# Check user permissions
	if not cortex.lib.user.does_user_have_permission("tenable.view"):
		abort(403)

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
