#### F5 BigIP NLB Create HTTP Site Workflow Task

def run(helper, options):

	# Configuration of task
	config = options['wfconfig'i]

	## Allocate a hostname #################################################

	# Start the task
	#helper.event("allocate_name", "Creating node")

	# End the event
	#helper.end_event(description="Created node")
