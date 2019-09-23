#!/usr/bin/env python

from __future__ import print_function
import os, sys, subprocess, json, requests, imp

# The cortex-puppet-strngs.conf file is in the same folder as our binary
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cortex-puppet-strings.conf')

# Read the config
def load_config():
	d = imp.new_module('config')
	d.__file__ = CONFIG_FILE
	try:
		with open(CONFIG_FILE) as config_file:
			exec(compile(config_file.read(), CONFIG_FILE, 'exec'), d.__dict__)
	except IOError as e:
		print('Unable to load configuration file ' + e.strerror, file=sys.stderr)
		sys.exit(1)
	config = {}

	for key in dir(d):
		if key.isupper():
			config[key] = getattr(d, key)

	## ensure we have required config options
	for wkey in ['PUPPET_BINARY', 'PUPPET_PATHS', 'API_TOKEN', 'API_URL', 'SSL_VERIFY']:
		if not wkey in config.keys():
			print('Missing configuration option: ' + wkey, file=sys.stderr)
			sys.exit(1)

	return config

def generate_puppet_strings_json(config):
	modules_seen = set()
	outcome = {'puppet_classes': []}

	# Iterate over all the paths that could contain Puppet modules
	for current_path in config['PUPPET_PATHS']:
		# List the contents of the current path
		contents = os.listdir(current_path)

		# For each top-level item in the current path
		for item in contents:

			# Generate it's fully qualified paths
			fq_path = os.path.join(current_path, item)
			manifests_path = os.path.join(fq_path, 'manifests')
			pp_wildcard_path = os.path.join(manifests_path, '**', '*.pp')

			# If it's a directory (i.e. could be a Puppet module)
			if os.path.isdir(fq_path) and os.path.isdir(manifests_path):
				# Don't do the same module twice
				if item not in modules_seen:
					# Add to the list of seen modules
					modules_seen.add(item)

					print("Running on " + pp_wildcard_path)

					# Run puppet strings, returning output to the "output" variable
					process = subprocess.Popen([config['PUPPET_BINARY'], 'strings', 'generate', '--format', 'json', pp_wildcard_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
					output, output_err = process.communicate()

					# If unsuccessful
					if process.returncode != 0:
						print("Error running puppet strings. Exit code was " + str(process.returncode), file=sys.stderr)
					else:
						# Parse the 
						try:
							puppet_strings = json.loads(output)
						except Exception as e:
							print("Skipping " + item + " as no JSON output")
							continue

						output = {}
						output['puppet_classes'] = []
						for c in puppet_strings['puppet_classes']:
							this_class_details = {}
							this_class_details['name'] = c['name']
							if 'docstring' in c and 'tags' in c['docstring']:
								this_class_details['docstring'] = {'tags': c['docstring']['tags']}
							output['puppet_classes'].append(this_class_details)
							outcome['puppet_classes'].append(output['puppet_classes'])

	return outcome

if __name__ == "__main__":
	config = load_config()
	outcome = generate_puppet_strings_json(config)
	headers = {'Accept': 'application/json', 'Content-Type': 'application/json', 'X-Auth-Token': config['API_TOKEN']}
	r = requests.post(config['API_URL'], headers=headers, json=outcome, verify=config['SSL_VERIFY'])
