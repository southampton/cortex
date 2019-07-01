from corpus import rubrik

def run(helper, options):
	# helper
	helper.event('_test', 'testing the rubrik api')
	rub = rubrik.Rubrik(helper)
	test = rub.get_sla_domains()
	helper.end_event(success=True, description=test)
