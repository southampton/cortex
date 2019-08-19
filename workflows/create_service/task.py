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
		helper.event("create_vm", "Creating "+ vm_recipe)

		options['vm_recipes'][vm_recipe]['vm_recipe_name'] = vm_recipe
		options['vm_recipes'][vm_recipe]['service_task_id'] = helper.task_id
		
		# Start the buildvm task
		vm_task_id = neocortex.create_task("buildvm", username, options['vm_recipes'][vm_recipe], description="Creates and sets up a virtual machine (sandbox VMware environment)")

		# Map the recipe name to the task ID
		recipe_to_id_map[vm_recipe] = vm_task_id

		#helper.end_event("Probably created the VM")

	# All the buildvm tasks have started, but they all need to finish before the puppet code can be applied
	helper.event("wait_buildvm","Waiting for all the buildvm tasks to finish")
	helper.lib.neocortex_multi_tasks_wait(recipe_to_id_map.values())
	helper.end_event("All buildvm tasks have finished running")
	
	# Now that the VMs have been set up, apply the Puppet code
	tasks_output = {}
	
	# Get the task output from each buildvm task
	for key in recipe_to_id_map.keys():
		vm_task_id = recipe_to_id_map[key]
		result = helper.execute_query("SELECT `task_output` FROM `tasks` WHERE `id` = %s;", params=(vm_task_id,))[0] # [0] cause execute_query returns a tuple (uses fetchall)
		
		# map the recipe name to a task output
		tasks_output[key] = json.loads(result['task_output'])

	#  
	for recipe_name in recipe_to_id_map.keys():
		# Replaces the references in the recipe code
		puppet_code_recipe = options['vm_recipes'][recipe_name]['puppet_code']
		puppet_code_parsed = puppet_parse_references(helper, puppet_code_recipe, tasks_output)
		
		puppet_certname = tasks_output[recipe_name]['allocated_vm_name'] + "." + options['wfconfig']['PUPPET_CERT_DOMAIN']
		
		# Updates the puppet code
		helper.event("update_puppet", "Updating the puppet code for " + recipe_name)
		helper.execute_query('UPDATE `puppet_nodes` SET `classes` = %s WHERE `certname` = %s', (puppet_code_parsed, puppet_certname,))
		helper.end_event("Puppet code for " + recipe_name + " updated.")
	

# Helper function which replaces the references in the puppet code with 
# the actual values
def puppet_parse_references(helper, puppet_code_recipe, tasks_output):
	
	# Find all the substrings which match the given regex, such ass {{some_reference.allocated_vm_name}}
	systems_references = re.findall("{{\w*\.\w*}}", puppet_code_recipe)
	
	reference_to_system_name = {}
	for system_reference in systems_references:
		# temp var which contains the reference without the curly brackets
		temp = system_reference[2:-2]

		try:
			# try to split the string
			(recipe_name, attribute) = (temp.split(".")[0], temp.split(".")[1])
			puppet_code_recipe = re.sub(system_reference, tasks_output[recipe_name][attribute], puppet_code_recipe)
		except Exception as e:
			# if the reference is not correct, print the error into the error log
			print(str(e))
			# continue without breaking the for loop
			continue

	return puppet_code_recipe
