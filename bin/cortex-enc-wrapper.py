#!/bin/python

# Configuration
CACHE_DIR='/var/cache/cortex-penc'
CORTEX_URL='https://cortex.dev.soton.ac.uk/api/puppet/enc'
AUTH_TOKEN=''

import sys, requests, warnings, os

################################################################################

def cache_catalog(certname, catalog):
	"""Caches the catalog for the given node to disk"""

	# Open the file for writing
	with open(os.path.join(CACHE_DIR, certname), 'w') as f:
		# Write the catalog
		f.write(catalog)

################################################################################

def print_catalog(certname):
	"""Reads the catalog from disk (if possible) and then prints it out. Returns 0 on success and 1 on error"""

	try:
		# Open the catalog, read it and print it out
		with open(os.path.join(CACHE_DIR, certname), 'r') as f:
			print f.read()
	except Exception, e:
		return 1

	return 0

################################################################################

# Validate arguments
if len(sys.argv) <= 1:
	print >> sys.stderr, "Usage: cortex-env-wrapper <nodename"
	sys.exit(1)

# Get the certname of the node to find
certname = sys.argv[1]

# Request the page, and don't print out the InsecureRequestWarning
try:
	with warnings.catch_warnings():
		warnings.simplefilter("ignore", requests.packages.urllib3.exceptions.InsecureRequestWarning)
		r = requests.get(CORTEX_URL + '/' + certname + '?auth_token=' + AUTH_TOKEN, headers={'Accept': 'application/yml'}, verify=False)
except Exception, e:
	# On exception, attempt to print cache
	sys.exit(print_catalog(certname))

# On a 200 OK response, we should cache the catalog and print it out for the ENC
if r.status_code == 200:
	# Cache the catalog to the file system
	cache_catalog(certname, r.text)

	# Return the catalog to Puppet
	print r.text
	sys.exit(0)

# On a 404 Not Found response, print out an empty catalog
elif r.status_code == 404:
	# Return blank catalog to Pupper
	print "classes:"
	sys.exit(0)

# On any other response, attempt to return the cache
else:
	sys.exit(print_catalog(certname))

# Shouldn't get here
sys.exit(1)
