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

	recipe_to_id_map = {}
	# Create a new event each time a VM is set up?
	for vm_recipe in options['vm_recipes']:
		helper.event("create_vm", "Creating "+ vm_recipe)
		username = "acv1y18"  # THIS IS HARDCODED AND NEEDS TO BE CHANGEDt
		options['vm_recipes'][vm_recipe]['vm_recipe_name'] = vm_recipe
		options['vm_recipes'][vm_recipe]['service_task_id'] = helper.task_id
		vm_task_id = neocortex.create_task("buildvm", username, options['vm_recipes'][vm_recipe], description="Creates and sets up a virtual machine (sandbox VMware environment)")
		recipe_to_id_map[vm_recipe] = vm_task_id
		helper.end_event("Probably created the VM")

	helper.event("wait_buildvm","Waiting for all the buildvm tasks to finish")
	helper.lib.neocortex_multi_tasks_wait(recipe_to_id_map.values())
	#helper.lib.neocortex_task_wait(vm_task_id)
	helper.end_event("All buildvm tasks have finished running")
	
	# Now that the VMs have been set up, it's time to apply the Puppet code
	tasks_output = {}
	for key in recipe_to_id_map.keys():
		vm_task_id = recipe_to_id_map[key]
		result = helper.execute_query("SELECT `task_output` FROM `tasks` WHERE `id` = %s;", params=(vm_task_id,))[0] # [0] cause execute_query returns a tuple (uses fetchall)
		tasks_output[key] = json.loads(result['task_output'])
	print("==================================================++++++++++++++++++++++++++++++++++++++++++++++===========================================")
	print(json.dumps(tasks_output))
	for recipe_name in recipe_to_id_map.keys():
		puppet_code_template = options['vm_recipes'][vm_recipe]['vm_recipe_name']
		puppet_code_parsed = puppet_parse_references(helper, puppet_code_template, tasks_output)
		print("+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
		print("PARSED PUPPET: " + puppet_code_parsed)




def puppet_parse_references(helper, puppet_code_template, tasks_output):
	systems_references = re.findall("{{\w*}}", puppet_code_template)
	
	reference_to_system_name = {}
	for system_reference in systems_references:
		puppet_code_template = re.sub(system_reference, tasks_output[system_reference]['allocated_vm_name'], puppet_code_template)
	return puppet_code_template
