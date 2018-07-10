#### F5 BigIP NLB Create HTTP Site Workflow Task

def run(helper, options):

	# Configuration of task
	config = options['wfconfig']
	actions = options['actions']

	# Validate we get a list
	assert type(actions) is list, "actions list is not a Python list object"

	## Allocate a hostname #################################################

	# Start the task
	for action in actions:
		# Start the event
		helper.event(action['id'], action['action_description'])

		if action['id'] == 'generate_letsencrypt':
			r = action_generate_letsencrypt(action, helper)
		elif action['id'] == 'allocate_ip':
			r = action_allocate_ip(action, helper)
		elif action['id'] == 'create_node':
			r = action_create_node(action, helper)
		elif action['id'] == 'create_monitor':
			r = action_create_monitor(action, helper)
		elif action['id'] == 'create_pool':
			r = action_create_pool(action, helper)
		elif action['id'] == 'upload_key':
			r = action_upload_key(action, helper)
		elif action['id'] == 'upload_cert':
			r = action_upload_cert(action, helper)
		elif action['id'] == 'create_ssl_client_profile':
			r = action_create_ssl_client_profile(action, helper)
		elif action['id'] == 'create_http_profile':
			r = action_create_http_profile(action, helper)
		elif action['id'] == 'create_virtual_server':
			r = action_create_virtual_server(action, helper)

		# End the event (don't change the description) if the action
		# succeeded. The action_* functions either raise Exceptions or
		# end the events with a failure message on errors.
		if r:
			helper.end_event()

################################################################################

def action_generate_letsencrypt(action, helper):
	return True

################################################################################

def action_allocate_ip(action, helper):
	return True

################################################################################

def action_create_node(action, helper):
	return True

################################################################################

def action_create_monitor(action, helper):
	return True

################################################################################

def action_create_pool(action, helper):
	return True

################################################################################

def action_upload_key(action, helper):
	return True

################################################################################

def action_upload_cert(action, helper):
	return True

################################################################################

def action_create_ssl_client_profile(action, helper):
	return True

################################################################################

def action_create_http_profile(action, helper):
	return True

################################################################################

def action_create_virtual_server(action, helper):
	return True
