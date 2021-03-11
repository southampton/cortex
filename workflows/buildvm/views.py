#!/usr/bin/env python

import datetime

from flask import abort, flash, redirect, request, session, url_for

import cortex.lib.admin
import cortex.lib.core
import cortex.lib.dsc

from cortex import app
from cortex.lib.user import get_user_list_from_cache
from cortex.lib.workflow import CortexWorkflow

workflow = CortexWorkflow(__name__)
workflow.add_permission("buildvm.sandbox", "Create Sandbox VM")
workflow.add_permission("buildvm.standard", "Create Standard VM")

################################################################################
## Common data validation / form extraction

def validate_data(r, templates, envs):

	# Get the VM Specs Config from the DB.
	try:
		vm_spec_config_json = cortex.lib.admin.get_kv_setting("vm.specs.config", load_as_json=True)
	except ValueError:
		flash("Could not parse JSON from the database.", "alert-danger")
		vm_spec_config_json = {}


	# Pull data out of request
	sockets = r.form["sockets"]
	cores = r.form["cores"]
	ram = r.form["ram"]
	disk = r.form["disk"]
	template = r.form["template"]
	env = r.form["environment"]
	swap_enabled = bool(r.form["swap-enabled"].lower() == "enable") if "swap-enabled" in r.form else False
	swap = r.form["swap"] if "swap" in r.form else 0

	sockets = int(sockets)
	if vm_spec_config_json is not None and "slider-sockets" in vm_spec_config_json and vm_spec_config_json["slider-sockets"].get("min", None) is not None and vm_spec_config_json["slider-sockets"].get("max", None) is not None:
		if not int(vm_spec_config_json["slider-sockets"]["min"]) <= sockets <= int(vm_spec_config_json["slider-sockets"]["max"]):
			raise ValueError("Invalid number of sockets selected")
	elif not 1 <= sockets <= 16:
		raise ValueError("Invalid number of sockets selected")

	cores = int(cores)
	if vm_spec_config_json is not None and "slider-cores" in vm_spec_config_json and vm_spec_config_json["slider-cores"].get("min", None) is not None and vm_spec_config_json["slider-cores"].get("max", None) is not None:
		if not int(vm_spec_config_json["slider-cores"]["min"]) <= cores <= int(vm_spec_config_json["slider-cores"]["max"]):
			raise ValueError("Invalid number of cores per socket selected")
	elif not 1 <= cores <= 16:
		raise ValueError("Invalid number of cores per socket selected")

	ram = int(ram)
	if vm_spec_config_json is not None and "slider-ram" in vm_spec_config_json and vm_spec_config_json["slider-ram"].get("min", None) is not None and vm_spec_config_json["slider-ram"].get("max", None) is not None:
		if not int(vm_spec_config_json["slider-ram"]["min"]) <= ram <= int(vm_spec_config_json["slider-ram"]["max"]):
			raise ValueError("Invalid amount of RAM selected")
	elif not 2 <= ram <= 32:
		raise ValueError("Invalid amount of RAM selected")

	disk = int(disk)
	if vm_spec_config_json is not None and "slider-disk" in vm_spec_config_json and vm_spec_config_json["slider-disk"].get("min", None) is not None and vm_spec_config_json["slider-disk"].get("max", None) is not None:
		if not int(vm_spec_config_json["slider-disk"]["min"]) <= disk <= int(vm_spec_config_json["slider-disk"]["max"]):
			raise ValueError("Invalid disk capacity selected")
	elif not 100 <= disk <= 2000:
		raise ValueError("Invalid disk capacity selected")

	if swap_enabled:
		swap = int(swap)
		if vm_spec_config_json is not None and "slider-swap" in vm_spec_config_json and vm_spec_config_json["slider-swap"].get("min", None) is not None and vm_spec_config_json["slider-swap"].get("max", None) is not None:
			if not int(vm_spec_config_json["slider-swap"]["min"]) <= swap <= int(vm_spec_config_json["slider-swap"]["max"]):
				raise ValueError("Invalid swap capacity selected")
		elif not 2 <= swap <= 16:
			raise ValueError("Invalid swap capacity selected")
	else:
		swap = 0

	if template not in templates:
		raise ValueError("Invalid template selected")

	if env not in envs:
		raise ValueError("Invalid environment selected")

	if "expiry" in r.form and r.form["expiry"] is not None and len(r.form["expiry"].strip()) > 0:
		expiry = r.form["expiry"]
		try:
			expiry = datetime.datetime.strptime(expiry, "%Y-%m-%d")
		except Exception:
			raise ValueError("Expiry date must be specified in YYYY-MM-DD format")
	else:
		expiry = None

	return (sockets, cores, ram, disk, swap, template, env, expiry)
"""
		if 'WINRPC' in app.config:
			options['dsc_config'] = app.config['WINRPC']
		else:
			options['dsc_config'] = app.config['WINRPC']

		if 'WINRPC' in app.config:
			options['dsc_config'] = app.config['WINRPC']
		else:
			options['dsc_config'] = app.config['WINRPC']

		# Connect to NeoCortex and start the task
		neocortex = cortex.lib.core.neocortex_connect()
		task_id = neocortex.create_task(__name__, session['username'], options, description="Creates and sets up a virtual machine (sandbox VMware environment)")
"""
def get_build_config(build_type, config_key, *args):
	"""Helper function to return per-build_type config values"""
	prefix = {
		"standard": "",
		"sandbox": "SB_",
	}.get(build_type, "")

	if args:
		return workflow.config.get(prefix + config_key, *args)
	return workflow.config[prefix + config_key]

################################################################################
## Generic Build VM View Handler

def build(build_type):

	# Ensure build_type is always standard or sandbox
	if build_type not in ["standard", "sandbox"]:
		abort(400)

	# Build title
	title = {
		"standard": "Create Standard Virtual Machine",
		"sandbox": "Create Sandbox Virtual Machine",
	}.get(build_type, "Create Virtual Machine")

	# Get the list of clusters
	all_clusters = cortex.lib.core.vmware_list_clusters(get_build_config(build_type, "VCENTER_TAG"))

	# Limit to the configured clusters
	clusters = []
	for cluster in all_clusters:
		if cluster["name"] in get_build_config(build_type, "CLUSTERS"):
			clusters.append(cluster)

	# Get a list of folders for the standard build
	folders = []
	if build_type == "standard":
		for folder in cortex.lib.core.vmware_list_folders(get_build_config(build_type, "VCENTER_TAG")):
			if folder["name"] not in get_build_config(build_type, "HIDE_FOLDERS", []):
				folders.append(folder)
		folders.sort(key=lambda x: x["fully_qualified_path"])

	# Get the list of environments
	environments = cortex.lib.core.get_cmdb_environments()

	if request.method == "POST":
		# Ensure we have all parameters that we require
		if not all(field in request.form for field in ["sockets", "cores", "ram", "disk", "template", "cluster", "environment", "network"]):
			flash("You must select options for all questions before creating", "alert-danger")
			return redirect(url_for(build_type))

		# Form validation
		try:
			# Extract all the common parameters
			cluster = request.form["cluster"]
			purpose = request.form["purpose"]
			comments = request.form["comments"]
			sendmail = "send_mail" in request.form
			network = request.form["network"]
			primary_owner_who = request.form.get("primary_owner_who", None)
			primary_owner_role = request.form.get("primary_owner_role", None)
			secondary_owner_who = request.form.get("secondary_owner_who", None)
			secondary_owner_role = request.form.get("secondary_owner_role", None)

			# Extract standard build / optional parameters
			task = None
			if build_type == "standard":
				task = request.form["task"]

			dns_aliases = request.form.get("dns_aliases", None)
			vm_folder_moid = request.form.get("vm_folder_moid", None)

			if dns_aliases is not None and len(dns_aliases) > 0:
				dns_aliases = dns_aliases.split(",")
			else:
				dns_aliases = []

			if vm_folder_moid is not None and len(vm_folder_moid) <= 0:
				vm_folder_moid = None

			if dsc_role is not None:
				try:
					proxy = cortex.lib.dsc.dsc_connect()
					cortex.lib.dsc.enroll_new(__name__, dsc_role)
				except Exception as e:
					flash("Unable to enroll machine in DSC:" + str(e), "alert-danger")
			# Validate the data (common between standard / sandbox)
			(sockets, cores, ram, disk, swap, template, env, expiry) = validate_data(request, get_build_config(build_type, "OS_ORDER"), [e["id"] for e in environments])

			# Validate cluster against the list we've got
			if cluster not in [c["name"] for c in clusters]:
				raise ValueError("Invalid cluster selected (" + str(cluster) + ")")

			# Validate network against the list we've got
			if network not in get_build_config(build_type, "NETWORK_NAMES"):
				raise ValueError("Invalid network selected")

		except ValueError as e:
			flash(str(e), "alert-danger")
			return redirect(url_for(build_type))

		except Exception as e:
			flash("Submitted data invalid " + str(e), "alert-danger")
			return redirect(url_for(build_type))

		# Build options to pass to the task
		options = {}
		options["build_type"] = build_type
		options["sockets"] = sockets
		options["cores"] = cores
		options["ram"] = ram
		options["disk_swap"] = swap
		options["disk"] = disk
		options["template"] = template
		options["cluster"] = cluster
		options["env"] = env
		options["task"] = task
		options["purpose"] = purpose
		options["comments"] = comments
		options["sendmail"] = sendmail
		options["wfconfig"] = workflow.config
		options["expiry"] = expiry
		options["network"] = network
		options["primary_owner_who"] = primary_owner_who
		options["primary_owner_role"] = primary_owner_role
		options["secondary_owner_who"] = secondary_owner_who
		options["secondary_owner_role"] = secondary_owner_role
		options["dns_aliases"] = dns_aliases
		options["vm_folder_moid"] = vm_folder_moid

		# Additional task options for the standard build
		if build_type == "standard" and "NOTIFY_EMAILS" in app.config:
			options["notify_emails"] = app.config["NOTIFY_EMAILS"]
			options['workflow'] = 'standard'
			options['sockets'] = sockets
			options['cores'] = cores
			options['ram'] = ram
			options['disk'] = disk
			options['template'] = template
			options['cluster'] = cluster
			options['env'] = env
			options['task'] = task
			options['purpose'] = purpose
			options['comments'] = comments
			options['sendmail'] = sendmail
			options['wfconfig'] = workflow.config
			options['expiry'] = expiry
			options['network'] = network
			options['primary_owner_who'] = primary_owner_who
			options['primary_owner_role'] = primary_owner_role
			options['secondary_owner_who'] = secondary_owner_who
			options['secondary_owner_role'] = secondary_owner_role
			options['dns_aliases'] = dns_aliases
			options['vm_folder_moid'] = vm_folder_moid


		if 'NOTIFY_EMAILS' in app.config:
			options['notify_emails'] = app.config['NOTIFY_EMAILS']
		else:
			options["notify_emails"] = []

		if 'WINRPC' in app.config:
			options['dsc_config'] = app.config['WINRPC']
		else:
			options['dsc_config'] = app.config['WINRPC']


		if 'WINRPC' in app.config:
			options['dsc_config'] = app.config['WINRPC']
		else:
			options['dsc_config'] = app.config['WINRPC']


		# Connect to NeoCortex and start the task
		neocortex = cortex.lib.core.neocortex_connect()
		task_id = neocortex.create_task(__name__, session["username"], options, description="Creates and sets up a virtual machine (Build Type = {})".format(build_type))

		# Log the Task ID
		cortex.lib.core.log(__name__, "workflow.buildvm.{}".format(build_type), "Build standard VM task {} started by {} with ServiceNow task {}".format(task_id, session["username"], task or "None"))

		# Redirect to the status page for the task
		return redirect(url_for("task_status", task_id=task_id))

	# Get a list of Users
	autocomplete_users = get_user_list_from_cache()

	# Get the VM Specs from the DB
	try:
		vm_spec_json = cortex.lib.admin.get_kv_setting("vm.specs", load_as_json=True)
	except ValueError:
		flash("Could not parse JSON from the database.", "alert-danger")

	# Get the VM Specs Config from the DB.
	try:
		vm_spec_config_json = cortex.lib.admin.get_kv_setting("vm.specs.config", load_as_json=True)
	except ValueError:
		flash("Could not parse JSON from the database.", "alert-danger")
		vm_spec_config_json = {}

	# Get the VM Specs from the DB
	try:
		vm_spec_json = cortex.lib.admin.get_kv_setting("vm.specs", load_as_json=True)
	except ValueError:
		flash("Could not parse JSON from the database.", "alert-danger")
		vm_spec_json = {}

	# Get the VM Specs Config from the DB.
	try:
		vm_spec_config_json = cortex.lib.admin.get_kv_setting('vm.specs.config', load_as_json=True)
	except ValueError:
		flash("Could not parse JSON from the database.", "alert-danger")
		vm_spec_config_json = {}

	try:
		proxy = cortex.lib.dsc.dsc_connect()
		vm_spec_dsc_roles = cortex.lib.dsc.get_roles(proxy)
		vm_spec_dsc_roles = list(set([key.split("_")[0].replace("UOS", "") for key in vm_spec_dsc_roles if key != "AllNodes"]))
	except Exception as e:
		flash("DSC Error:" + str(e), "alert-danger")
		vm_spec_dsc_roles = []



	## Show form
	return workflow.render_template(
		"build.html",
		build_type=build_type,
		title=title,
		clusters=clusters,
		default_cluster=get_build_config(build_type, "DEFAULT_CLUSTER", None),
		environments=environments,
		default_env=get_build_config(build_type, "DEFAULT_ENV", None),
		folders=folders,
		os_names=get_build_config(build_type, "OS_DISP_NAMES"),
		os_order=get_build_config(build_type, "OS_ORDER"),
		os_types=get_build_config(build_type, "OS_TYPES"),
		network_names=get_build_config(build_type, "NETWORK_NAMES"),
		networks_order=get_build_config(build_type, "NETWORK_ORDER"),
		autocomplete_users=autocomplete_users,
		vm_spec_json=vm_spec_json,
		vm_spec_config_json=vm_spec_config_json,
		dsc_roles = vm_spec_dsc_roles,
	)

################################################################################
## Build VM View Routes

@workflow.route("standard", title="Create Standard VM", order=10, permission="buildvm.standard", methods=["GET", "POST"])
def standard():
	return build("standard")

@workflow.route("sandbox", title="Create Sandbox VM", order=20, permission="buildvm.sandbox", methods=["GET", "POST"])
def sandbox():
	return build("sandbox")
