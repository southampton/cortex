import re
import string

from flask import g, flash, request, session, redirect, url_for

import cortex.lib.core
from cortex import app
from cortex.lib.user import does_user_have_workflow_permission
from cortex.lib.workflow import CortexWorkflow

workflow = CortexWorkflow(__name__)
workflow.add_permission("puppet.environment.admin", "Administer Puppet environments (create/delete all environments)")
workflow.add_permission("puppet.environment.user", "Use Puppet environments (create/delete service and dynamic environments)")

ENVIRONMENT_NAME_REGEX = re.compile(r"\A[a-z0-9_]+\Z")
ENVIRONMENT_TYPES = {
	0: "Infrastrucutre", # Common / Legacy environments (static)
	1: "Service",        # Per-Service Puppet environment
	2: "Dynamic"         # Dynamic environment for testing
}

def puppet_environment_permission_callback():
	"""Check if the User has either puppet.environment.admin
	or puppet.environment.admin"""
	return does_user_have_workflow_permission("puppet.environment.admin") or does_user_have_workflow_permission("puppet.environment.admin")

@workflow.route("environment/create", title="Create Puppet Environment", order=50, permission=puppet_environment_permission_callback, methods=["GET", "POST"])
def puppet_environment_create():
	"""Create a new Puppet environment"""

	environment_admin = True
	environment_types = dict(ENVIRONMENT_TYPES)
	if not does_user_have_workflow_permission("puppet.environment.admin"):
		environment_admin = False
		environment_types.pop(0, None)

	# Create the values dict, and set default environment type to Dynamic
	values = { "environment_type": 2}
	if request.method == "POST":
		values["environment_type"] = request.form.get("environment_type", 2)
		values["environment_short_name"] = request.form.get("environment_short_name", "")
		values["environment_name"] = request.form.get("environment_name", "")

		# Validate
		error = False
		try:
			values["environment_type"] = int(values["environment_type"])
		except ValueError:
			error = True
			flash("The environment type is not an integer type", "alert-danger")

		# Enforce a naming scheme for Service and Dynamic environments
		if values["environment_type"] == 1:
			values["environment_name"]  = "svc_" + values["environment_name"].lower()
		elif values["environment_type"] == 2:
			values["environment_name"] = "dyn_" + app.pwgen(alphabet=string.ascii_lowercase + string.digits, length=16)

		if (values["environment_type"] not in ENVIRONMENT_TYPES) or (not environment_admin and values["environment_type"] == 0):
			error = True
			flash("Invalid environment type", "alert-danger")
		if values["environment_type"] != 2 and not ENVIRONMENT_NAME_REGEX.match(values["environment_name"]):
			error = True
			flash("The environment name '{}' does not match the pattern '\\A[a-z0-9_]+\\Z'".format(values["environment_name"]), "alert-danger")
		if not values["environment_short_name"]:
			values["environment_short_name"] = values["environment_name"]

		# Get the database cursor
		curd = g.db.cursor()
		curd.execute("SELECT `id` FROM `puppet_environments` WHERE `environment_name`=%s", (values["environment_name"],))
		if curd.fetchone():
			error = True
			flash("The environment name '{}' already exists".format(values["environment_name"]), "alert-danger")

		if not error:
			# Task Options
			options = {
				"wfconfig": workflow.config,
				"actions": [{"id":"environment.create", "desc": "Create a Puppet Environment"}],
				"values": values,
			}

			# Everything should be good - start a task.
			neocortex = cortex.lib.core.neocortex_connect()
			task_id = neocortex.create_task(__name__, session["username"], options, description="Create Puppet Environment")

			# Redirect to the status page for the task
			return redirect(url_for("task_status", id=task_id))

	return workflow.render_template("create.html", environment_types=environment_types, values=values)
