
import requests

def run(helper, options):

	# Iterate over the actions that we have to perform
	for action in options["actions"]:
		# Start the event
		helper.event(action["id"], action["desc"])
		r = False

		# Select an action
		if action["id"] == "environment.create":
			r = environment_create(options["values"], helper, options["wfconfig"])
		elif action["id"] == "environment.delete":
			r = environment_create(options["values"], helper, options["wfconfig"])

		# End the event (don't change the description) if the action
		# succeeded. The action_* functions either raise Exceptions or
		# end the events with a failure message on errors.
		if r:
			helper.end_event()
		else:
			raise RuntimeError("Action {} ({}) failed to complete successfully".format(action["desc"], action["id"]))

def environment_create(values, helper, wfconfig):
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
			json={"environment_name": values["environment_name"], "username": helper.username},
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
	helper.curd.execute("INSERT INTO `puppet_environments` (`short_name`, `environment_name`, `type`) VALUES (%s, %s, %s)", (values["environment_short_name"], values["environment_name"], values["environment_type"]))
	environment_id = helper.curd.lastrowid

	# Insert the puppet_users into the database
	for user in values["puppet_users"]:
		helper.curd.execute("INSERT INTO `puppet_users` (`environment_id`, `who`, `type`, `level`) VALUES (%s, %s, %s, %s)", (environment_id, user["who"], user["type"], user["level"]))

	return True

def environment_delete(values, helper, wfconfig):
	"""Delete an exisitng Puppet environment"""

	# Insert the details into the database
	helper.curd.execute("DELETE FROM `puppet_environments` WHERE `id`=%s", (values["environment_id"],))

	# TODO: Send an API call to the cortex-puppet-bridge to delete the environment

	return True
