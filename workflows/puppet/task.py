
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

	# Insert the details into the database
	helper.curd.execute("INSERT INTO `puppet_environments` (`short_name`, `environment_name`, `type`) VALUES (%s, %s, %s)", (values["environment_short_name"], values["environment_name"], values["environment_type"]))

	# TODO: Send an API call to the cortex-puppet-bridge to create the environment

	return True

def environment_delete(values, helper, wfconfig):
	"""Delete an exisitng Puppet environment"""

	# Insert the details into the database
	helper.curd.execute("DELETE FROM `puppet_environments` WHERE `id`=%s", (values["environment_id"],))

	# TODO: Send an API call to the cortex-puppet-bridge to delete the environment

	return True
