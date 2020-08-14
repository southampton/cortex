
import datetime
import imp
import json
import os
import re

import MySQLdb as mysql
import Pyro4
import requests


# Helper exception
class TooManyVMsException(Exception):
	pass

# Helper function to add a worknote to an object in ServiceNow
def add_servicenow_work_note(helper, object_type, sys_id, note):
	if note is not None and note != "":
		# Oddity: the V1 API didn't work for me here - I got a 200 back from a
		# PUT request to /api/now/table/sc_task/<sys_id> but no note appeared
		request_uri = 'https://' + str(helper.config['SN_HOST']) + '/' + object_type + '.do?JSONv2&sysparm_action=update&sysparm_query=sys_id=' + str(sys_id)
		json_headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
		r = requests.post(request_uri, auth=(helper.config['SN_USER'], helper.config['SN_PASS']), headers=json_headers, data=json.dumps({'work_notes': note}))
		r.raise_for_status()

# Helper function to update a task state in ServiceNow
def update_servicenow_task_state(helper, task_sys_id, new_state):
	request_uri = 'https://' + str(helper.config['SN_HOST']) + '/api/now/table/sc_task/' + str(task_sys_id)
	json_headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
	r = requests.put(request_uri, auth=(helper.config['SN_USER'], helper.config['SN_PASS']), headers=json_headers, data=json.dumps({'state': new_state}))
	r.raise_for_status()

def read_config_file(file_path):
	# Load settings for this workflow
	if not os.path.isfile(file_path):
		raise Exception('Couldn\'t find configuration file "' + str(file_path) + '"')

	# Start a new module, which will be the context for parsing the config
	# pylint: disable=invalid-name
	d = imp.new_module('config')
	d.__file__ = file_path

	# Read the contents of the configuration file and execute it as a
	# Python script within the context of a new module
	with open(file_path) as config_file:
		# pylint: disable=exec-used
		exec(compile(config_file.read(), file_path, 'exec'), d.__dict__)

	# Extract the config options, which are those variables whose names are
	# entirely in uppercase
	config = {}
	for key in dir(d):
		if key.isupper():
			config[key] = getattr(d, key)

	return config

# The actual task
# pylint: disable=protected-access
def run(helper, _options):
	# Compile VM name regex
	re_vm_name = re.compile(helper.config['SNVM_VALID_VM_NAME_REGEX'])

	# Load buildvm config
	buildvm_config = read_config_file(os.path.join(helper.config['WORKFLOWS_DIR'], helper.config['SNVM_CORTEX_BUILDVM_TASK_NAME'], 'workflow.conf'))

	helper.event('check_expire_count', 'Checking ServiceNow for VMs waiting to be built')

	# Make the request to ServiceNow
	json_headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
	request_uri = 'https://' + helper.config['SN_HOST'] + '/api/now/table/sc_task?sysparm_query=active%3DTRUE%5Eassigned_to.user_name%3D' + helper.config['SN_USER'] + '%5E' + str(helper.config['SNVM_TASK_STATE_FIELD']) + '=' + str(helper.config['SNVM_STATE_OPEN']) + '&sysparm_fields=' + ('%2C'.join(['sys_id', str(helper.config['SNVM_TASK_DESCRIPTION_FIELD']), str(helper.config['SNVM_TASK_USER_FIELD']), str(helper.config['SNVM_TASK_STATE_FIELD']), str(helper.config['SNVM_TASK_FRIENDLY_ID_FIELD'])]))
	r = requests.get(request_uri, auth=(helper.config['SN_USER'], helper.config['SN_PASS']), headers=json_headers)
	r.raise_for_status()

	try:
		result_rows = r.json()['result']
	except Exception as e:
		raise Exception('Failed to parse JSON response from ServiceNow: ' + str(e))

	# Setup for building VMs loop
	index = 0
	num_builds = len(result_rows)
	helper.end_event(description='Found ' + str(num_builds) + ' VMs waiting to be built')

	for details in result_rows:
		index = index + 1
		helper.event('validate_student_vm_task', 'Validating task details (' + str(index) + '/' + str(num_builds) + ')')
		vm_error = False

		# Make sure we have all the required information
		for key in ['sys_id', helper.config['SNVM_TASK_STATE_FIELD'], helper.config['SNVM_TASK_FRIENDLY_ID_FIELD'], helper.config['SNVM_TASK_DESCRIPTION_FIELD'], helper.config['SNVM_TASK_USER_FIELD']]:
			if key not in details:
				helper.end_event(success=False, description='Missing ' + key + ' attribute from ServiceNow task')
				vm_error = True
				break

		# Skip to the next VM if we encountered an error
		if vm_error:
			continue

		# Extract the ServiceNow task details
		sys_id = str(details['sys_id']).strip()
		friendly_id = str(details[helper.config['SNVM_TASK_FRIENDLY_ID_FIELD']]).strip()
		user = str(details[helper.config['SNVM_TASK_USER_FIELD']]).strip()
		try:
			description = json.loads(details[helper.config['SNVM_TASK_DESCRIPTION_FIELD']])
		except Exception:
			# End the event with an error
			helper.end_event(success=False, description='Failed to parse JSON description for ServiceNow task ' + friendly_id + ' for user ' + user)

			# Skip to the next VM
			continue

		# Make sure we have all the required information
		for key in [helper.config['SNVM_VM_OS_FIELD'], helper.config['SNVM_VM_NAME_FIELD'], helper.config['SNVM_VM_NETWORK_FIELD'], helper.config['SNVM_VM_END_DATE_FIELD']]:
			if key not in description:
				helper.end_event(success=False, description='Missing ' + key + ' attribute from description of ServiceNow task ' + sys_id + ' for user ' + user)
				vm_error = True
				break

		# Skip to the next VM if we encountered an error
		if vm_error:
			continue

		# Extract the VM details
		osid = str(description[helper.config['SNVM_VM_OS_FIELD']]).strip()
		name = str(description[helper.config['SNVM_VM_NAME_FIELD']]).strip()
		network = str(description[helper.config['SNVM_VM_NETWORK_FIELD']]).strip()
		end_date = str(description[helper.config['SNVM_VM_END_DATE_FIELD']]).strip()

		# Skip the VM if the name is invalid
		if re_vm_name.match(name) is None:
			helper.end_event(success=False, description='Invalid VM name (' + name + ') for ServiceNow task ' + friendly_id + ' for user ' + user)
			continue

		# For the end date as a datetime object, skipping the VM if invalid
		try:
			end_datetime = datetime.datetime.strptime(end_date, '%Y-%m-%d')
			if end_datetime < datetime.datetime.now():
				raise Exception('Date is in the past')
		except Exception as e:
			helper.end_event(success=False, description='Invalid end date (' + end_date + ') for ServiceNow task ' + friendly_id + ' for user ' + user + ': ' + str(e))
			continue

		# Skip past the VM is the OS choice is invalid
		if osid not in helper.config['SNVM_VALID_OSES']:
			helper.end_event(success=False, description='Invalid OS choice (' + osid + ') for ServiceNow task ' + friendly_id + ' for user ' + user)
			continue

		# Skip past the VM is the network choice is invalid
		if network not in helper.config['SNVM_VALID_NETWORKS']:
			helper.end_event(success=False, description='Invalid network choice (' + network + ') for ServiceNow task ' + friendly_id + ' for user ' + user)
			continue

		helper.end_event(description='Validated task details for ' + friendly_id + ' (' + str(index) + '/' + str(num_builds) + ')')

		try:
			helper.event('start_servicenow_vm_build', 'Starting build of VM ' + name + ' for user ' + user)

			# Get the task
			request_uri = 'https://' + helper.config['SN_HOST'] + '/api/now/table/sc_task/' + sys_id + '?sysparm_fields=' + str(helper.config['SNVM_TASK_STATE_FIELD'])
			r = requests.get(request_uri, auth=(helper.config['SN_USER'], helper.config['SN_PASS']), headers=json_headers)
			r.raise_for_status()

			# Make sure the state is still "Open"
			if str(r.json()['result'][helper.config['SNVM_TASK_STATE_FIELD']]).strip() != str(helper.config['SNVM_STATE_OPEN']).strip():
				raise Exception('ServiceNow task has changed state!')

			# Update the task
			update_servicenow_task_state(helper, sys_id, helper.config['SNVM_STATE_IN_PROGRESS'])

			# Add a note to the task indicating that the creation is in progress
			add_servicenow_work_note(helper, 'sc_task', sys_id, helper.config['SNVM_NOTE_CREATION_STARTED'])

			# Generate the VM name and build the VM
			vm_friendly_name = helper.config['SNVM_VM_FRIENDLY_NAME_FORMAT'].format(user=user, name=name, task_sys_id=sys_id, task_friendly_id=friendly_id)
			build_servicenow_vm(helper, buildvm_config, sys_id, friendly_id, vm_friendly_name, user, osid, network, end_date)

			# Add note to task indicating completion
			add_servicenow_work_note(helper, 'sc_task', sys_id, helper.config['SNVM_NOTE_CREATION_SUCCEEDED'])

			# Update the task
			update_servicenow_task_state(helper, sys_id, helper.config['SNVM_STATE_CLOSED_COMPLETE'])

		except TooManyVMsException:
			helper.end_event(success=False, description='Creation denied for VM ' + name + ' for user ' + user + ': User has too many VMs')

			# Update the task to close it and mark it as cancelled (denied)
			add_servicenow_work_note(helper, 'sc_task', sys_id, helper.config['SNVM_NOTE_TOO_MANY_VMS'])
			update_servicenow_task_state(helper, sys_id, helper.config['SNVM_STATE_CLOSED_CANCELLED'])

		except Exception as e:
			helper.end_event(success=False, description='Failed to build VM ' + name + ' for user ' + user + ': ' + str(e))

			# Mark the task as failed. An admin can go back to ServiceNow and reset the state
			# to open if they want to try the task again
			add_servicenow_work_note(helper, 'sc_task', sys_id, helper.config['SNVM_NOTE_CREATION_FAILED'])
			update_servicenow_task_state(helper, sys_id, helper.config['SNVM_STATE_CLOSED_INCOMPLETE'])

# Perform the build by starting a new task
def build_servicenow_vm(helper, buildvm_config, task_sys_id, task_friendly_id, friendly_name, user, osid, network, end_date):
	# Connect to the database
	curd = helper.db.cursor(mysql.cursors.DictCursor)

	# Find out how many systems the user has
	curd.execute('SELECT COUNT(*) AS `count` FROM `systems_info_view` WHERE `allocation_who` = %s AND `vmware_uuid` IS NOT NULL', (user,))
	user_vm_count = curd.fetchall()[0]['count']
	if user_vm_count >= helper.config['SNVM_USER_VM_LIMIT']:
		raise TooManyVMsException()

	# Build buildvm VM workflow options
	options = {}
	options['build_type'] = 'student'
	options['task'] = task_friendly_id
	options['workflow'] = helper.config['SNVM_OS_TO_BUILDVM_WORKFLOW_MAP'][osid]
	options['sockets'] = helper.config['SNVM_OS_TO_SOCKETS_MAP'][osid]
	options['cores'] = helper.config['SNVM_OS_TO_CORES_MAP'][osid]
	options['ram'] = helper.config['SNVM_OS_TO_RAM_MAP'][osid]
	options['disk_swap'] = 0
	options['disk'] = helper.config['SNVM_OS_TO_DISK_MAP'][osid]
	options['template'] = helper.config['SNVM_OS_TO_BUILD_MAP'][osid]
	options['network'] = helper.config['SNVM_NETWORK_MAP'][network]
	options['cluster'] = helper.config['SNVM_OS_TO_CLUSTER_MAP'][osid]
	options['env'] = helper.config['SNVM_OS_TO_ENV_MAP'][osid]
	options['purpose'] = helper.config['SNVM_VM_PURPOSE_FORMAT'].format(user=user, name=friendly_name, task_sys_id=task_sys_id, task_friendly_id=task_friendly_id)
	options['comments'] = ''
	options['expiry'] = end_date
	options['sendmail'] = True
	options['dns_aliases'] = [friendly_name + '.' + helper.config['SNVM_VM_FRIENDLY_NAME_DOMAIN']]
	options['notify_emails'] = []
	options['wfconfig'] = buildvm_config

	# Start the NeoCortex task (as the user)
	neocortex = Pyro4.Proxy('PYRO:neocortex@localhost:1888')
	neocortex._pyroHmacKey = helper.config['NEOCORTEX_KEY']
	neocortex._pyroTimeout = 5
	nc_task_id = neocortex.create_task(helper.config['SNVM_CORTEX_BUILDVM_TASK_NAME'], user, options, description="Creates and configures a virtual machine (via ServiceNow)")

	helper.end_event(description='NeoCortex task ' + str(nc_task_id) + ' kicked off for task ' + task_friendly_id)

	# Create an event to wait for the task
	helper.event('wait_neocortex_task', 'Waiting for NeoCortex task {{task_link id="' + str(nc_task_id) + '"}}' + str(nc_task_id) + '{{/task_link}} to complete')

	# Wait for the NeoCortex task to complete
	result = helper.lib.neocortex_task_wait(nc_task_id)

	# A result of 1 is completed successfully
	if result == 1:
		helper.end_event(description='NeoCortex task {{task_link id="' + str(nc_task_id) + '"}}' + str(nc_task_id) + '{{/task_link}} completed successfully')
	else:
		# Raise an exception to end this build. The exception andles the ServiceNow task state
		raise Exception("NeoCortex task {{task_link id='" + str(nc_task_id) + "'}}" + str(nc_task_id) + "{{/task_link}} did not complete successfully. Check the task for errors.")
