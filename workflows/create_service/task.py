import time
import Pyro4
import re
import json

# Maybe should add a third parameter that contains the options?
def run(helper, options):
	
	# Get NeoCortex connection
	neocortex = Pyro4.Proxy('PYRO:neocortex@localhost:1888')
	neocortex._pyroHmacKey = helper.config['NEOCORTEX_KEY']
	neocortex._pyroTimeout = 5

	# map each recipe name to a task ID
	recipe_to_id_map = {}

	# The username is going to be the same for all the VMs which are going to be created
	username = helper.username

	for vm_recipe in options['vm_recipes']:
		# Fire new event
		helper.event("create_vm", "Running buildvm task for "+ vm_recipe)

		options['vm_recipes'][vm_recipe]['vm_recipe_name'] = vm_recipe
		options['vm_recipes'][vm_recipe]['service_task_id'] = helper.task_id
		options['vm_recipes'][vm_recipe]['purpose'] = parse_references(options['vm_recipes'][vm_recipe]['purpose'], options)
		options['vm_recipes'][vm_recipe]['comments'] = parse_references(options['vm_recipes'][vm_recipe]['comments'], options)
		
		# Start the buildvm task
		vm_task_id = neocortex.create_task("buildvm", username, options['vm_recipes'][vm_recipe], description="Creates and sets up a virtual machine (sandbox VMware environment)")

		# Map the recipe name to the task ID
		recipe_to_id_map[vm_recipe] = vm_task_id

	# All the buildvm tasks have started, but they all need to finish before the puppet code can be applied
	helper.event("wait_buildvm","Waiting for all the buildvm tasks to finish")
	helper.lib.neocortex_multi_tasks_wait(recipe_to_id_map.values())
	helper.end_event(description="All buildvm tasks have finished running")
	
	# Now that the VMs have been set up, apply the Puppet code
	tasks_output = {}
	
	# Get the task output from each buildvm task
	for key in recipe_to_id_map.keys():
		vm_task_id = recipe_to_id_map[key]
		result = helper.execute_query("SELECT `task_output` FROM `tasks` WHERE `id` = %s;", params=(vm_task_id,))[0] # [0] cause execute_query returns a tuple (uses fetchall)
		
		# map the recipe name to a task output
		tasks_output[key] = json.loads(result['task_output'])

	tasks_output['questions'] = options['questions']

	for recipe_name in recipe_to_id_map.keys():
	
		# Replaces the references in the recipe code
		puppet_code_recipe = options['vm_recipes'][recipe_name]['puppet_code']
		puppet_code_parsed = parse_references(puppet_code_recipe, tasks_output)
		
		puppet_certname = tasks_output[recipe_name]['system_name'] + "." + options['wfconfig']['PUPPET_CERT_DOMAIN']
		
		# Updates the puppet code
		helper.event("update_puppet", "Updating the puppet code for " + recipe_name)
		helper.execute_query('UPDATE `puppet_nodes` SET `classes` = %s WHERE `certname` = %s', (puppet_code_parsed, puppet_certname,))
		helper.end_event(description="Puppet code for " + recipe_name + " updated.")

	subject = 'Cortex has finished building your service, ' + str(options['service_name'])

	message = "Cortex has finished building your service. The details of the service can be found below.\n"
	message += '\n'
	if options['workflow_type'] == 'standard':
		message += 'ServiceNow Task: ' + str(options['task']) + '; \n'
	if 'expiry' in options and options['expiry'] is not None:
		message += 'All the VMs which are part of this service will expire on: ' + str(options['expiry']) + '; \n'
	
	message += '\n'
	message += 'The service contains the following VMs: \n'
	message += '\n'
	
	for recipe_name in recipe_to_id_map.keys():
		message += str(recipe_name) + ' with the real name ' + tasks_output[recipe_name]['system_name'] + ': https://' + str(helper.config['CORTEX_DOMAIN']) + '/systems/edit/' + str(tasks_output[recipe_name]['system_dbid']) + '; \n'

	message += 'All the VMs were built in the ' + options['env'] + ' environment. \n'
	message += '\n'
	message += 'More information can be found on Cortex at https://' + str(helper.config['CORTEX_DOMAIN']) + '. \n'
	
	# Send the email to the user who started the task
	
	if 'sendmail' in options and options['sendmail'] is not None:
		helper.lib.send_email(helper.username, subject, message)
	
################################################################################

def parse_references(text, values_dict):

        # Find all the substrings which match the given regex, such ass {{some_reference.system_name}}
        references = re.findall("{{\w+(?:\.\w+)*}}", text)

        reference_to_system_name = {}
        for reference in references:
                # temp var which contains the reference without the curly brackets
                temp = reference[2:-2]
                reference_value = values_dict
                try:
                        # try to split the string
                        result_list = temp.split(".")
                        for element in result_list:
                                reference_value = reference_value[element]
                        print(reference_value)
                        text = re.sub(reference, reference_value, text)
                except Exception as e:
                        # if the reference is not correct, print the error into the error log
                        print(str(e))
                        # continue without breaking the for loop
                        continue
        return text
