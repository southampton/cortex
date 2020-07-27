
from urllib.parse import urljoin

import requests


def run(helper, options):

	# check if workflows are locked
	if not helper.lib.check_workflow_lock():
		raise Exception("Workflows are currently locked")

	# Iterate over the actions that we have to perform
	for action in options["actions"]:
		# Start the event
		helper.event(action["id"], action["desc"])
		r = False

		# Select an action
		if action["id"] == "environment.create":
			r = environment_create(options["values"], helper)
		elif action["id"] == "environment.delete":
			r = environment_delete(options["values"], helper)

		# End the event (don't change the description) if the action
		# succeeded. The action_* functions either raise Exceptions or
		# end the events with a failure message on errors.
		if r:
			helper.end_event()
		else:
			raise RuntimeError("Action {} ({}) failed to complete successfully".format(action["desc"], action["id"]))

def environment_create(values, helper):
	"""Create a new Puppet environment"""

	# Build the URL
	base_url = helper.config["PUPPET_AUTOSIGN_URL"]
	if not base_url.endswith("/"):
		base_url += "/"

	# Send the request to the Cortex Puppet Bridge to create the environment
	try:
		r = requests.post(
			base_url + "environment/create",
			headers={"X-Auth-Token": helper.config["PUPPET_AUTOSIGN_KEY"], "Accept": "application/json", "Content-Type": "application/json",},
			json={"environment_name": values["environment_name"], "environment_short_name": values["environment_short_name"], "username": helper.username},
			verify=helper.config["PUPPET_AUTOSIGN_VERIFY"],
		)
	except Exception as ex:
		helper.end_event(success=False, description="Failed to create environment on Puppet Master: {ex}".format(ex=ex))
		return False

	# Check return code
	if r.status_code != 200:
		helper.end_event(success=False, description="Failed to create environment on Puppet Master, Cortex Puppet Bridge returned error code: {status_code}".format(status_code=r.status_code))
		return False

	# Insert the details into the database
	helper.curd.execute("INSERT INTO `puppet_environments` (`short_name`, `environment_name`, `type`, `owner`) VALUES (%s, %s, %s, %s)", (values["environment_short_name"], values["environment_name"], values["environment_type"], values["environment_owner"]))
	helper.curd.connection.commit()

	# Output a success message
	helper.end_event(success=True, description="Sucessfully created Puppet environment: '{short_name}' ({name}, ID: {id}).".format(
		id=helper.curd.lastrowid,
		name=values["environment_name"],
		short_name=values["environment_short_name"]
	))
	return True

def environment_delete(values, helper):
	"""Delete an exisitng Puppet environment"""

	# Select the environment to get its name
	helper.curd.execute("SELECT * FROM `puppet_environments` WHERE `id`=%s", (values["environment_id"],))
	environment = helper.curd.fetchone()

	if environment is None:
		helper.end_event(success=False, description="Failed to delete Puppet environment, an environment with ID={id} does not exist.".format(
			id=values["environment_id"],
		))
		return False

	helper.curd.execute("SELECT 1 FROM `puppet_nodes` WHERE `env`=%s", (environment["environment_name"],))
	if helper.curd.fetchone():
		helper.end_event(success=False, description="Failed to delete Puppet environment, one or more nodes are currently classified with environment '{name}'".format(
			name=environment["environment_name"],
		))
		return False

	# Build the URL
	base_url = helper.config["PUPPET_AUTOSIGN_URL"]
	if not base_url.endswith("/"):
		base_url += "/"

	# Send the request to the Cortex Puppet Bridge to delete the environment
	try:
		r = requests.post(
			base_url + "environment/delete",
			headers={"X-Auth-Token": helper.config["PUPPET_AUTOSIGN_KEY"], "Accept": "application/json", "Content-Type": "application/json",},
			json={"environment_name": environment["environment_name"], "username": helper.username},
			verify=helper.config["PUPPET_AUTOSIGN_VERIFY"],
		)
	except Exception as ex:
		helper.end_event(success=False, description="Failed to delete environment on Puppet Master: {ex}".format(ex=ex))
		return False

	# Check return code
	if r.status_code != 200:
		helper.end_event(success=False, description="Failed to delete environment on Puppet Master, Cortex Puppet Bridge returned error code: {status_code}".format(status_code=r.status_code))
		return False

	## Check graphite for monitoring entries
	graphite_delete = False
	try:
		if helper.lib.config['GRAPHITE_URL']:
			r = requests.get(
				urljoin(helper.lib.config['GRAPHITE_URL'], '/host/' + environment["environment_name"]),
				auth=(helper.lib.config['GRAPHITE_USER'], helper.lib.config['GRAPHITE_PASS'])
			)
			if r.status_code == 200:
				r_json = r.json()
				graphite_delete = bool(isinstance(r_json, list) and r_json)
			else:
				helper.flash('Warning - CarbonHTTPInterface returned error code ' + str(r.status_code), 'warning')
		else:
			helper.flash('No Graphite URL Supplied, Skipping Step', 'success')
	except Exception as ex:
		helper.flash('Warning - An error occurred when communicating with ' + str(helper.lib.config['GRAPHITE_URL']) + ': ' + str(ex), 'warning')

	## Delete from graphite
	if graphite_delete:
		try:
			r = requests.delete(
				urljoin(helper.lib.config['GRAPHITE_URL'], '/host/' + environment["environment_name"]),
				auth=(helper.lib.config['GRAPHITE_USER'], helper.lib.config['GRAPHITE_PASS'])
			)

			if r.status_code != 200:
				helper.end_event(success=False, description="Failed to remove metrics from Graphite. CarbonHTTPInterface returned error code: {rc}".format(rc=r.status_code))
				return False

		except Exception as ex:
			helper.end_event(success=False, description="Failed to remove the metrics from Graphite: {ex}".format(ex=ex))
			return False


	# Delete the environment from the database
	helper.curd.execute("DELETE FROM `puppet_environments` WHERE `id`=%s", (values["environment_id"],))
	helper.curd.connection.commit()

	# Output a success messsage
	helper.end_event(success=True, description="Sucessfully delete Puppet environment: '{short_name}' ({name}, ID: {id})".format(
		id=values["environment_id"],
		name=environment["environment_name"],
		short_name=environment["short_name"]
	))

	return True
