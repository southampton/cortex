import cortex.lib.core
from cortex.lib.workflow import CortexWorkflow
from cortex.lib.systems import get_systems
from cortex.lib.user import does_user_have_workflow_permission, does_user_have_system_permission, does_user_have_any_system_permission
from flask import request, session, redirect, url_for, abort, flash, g
from datetime import datetime
import json

workflow = CortexWorkflow(__name__, check_config={})
workflow.add_permission("adddisk.add", "Add a virtual disk in VMware")

@workflow.route("add", title="Add a virtual disk in VMware", order=50, permission="adddisk.add", methods=["GET", "POST"])
def adddisk_add():

	return workflow.render_template("add.html")
