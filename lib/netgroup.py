
from ctypes import CDLL
from ctypes import byref as _byref
from ctypes import c_char_p

################################################################################

def exists(name):
	"""Validates the name of a netgroup"""

	try:
		# Try to switch to 'str' object rather than unicode
		name = name.encode('utf8')
	except Exception:
		# Ignore
		pass

	host,user,domain = c_char_p(None),c_char_p(None),c_char_p(None)
	libc = CDLL('libc.so.6')
	libc.setnetgrent(name)

	try:
		while libc.getnetgrent(_byref(host), _byref(user), _byref(domain)):
			libc.endnetgrent()
			return True

		libc.endnetgrent()
		return False

	except Exception:
		libc.endnetgrent()
		return False

################################################################################

def contains_host(host, netgroup):
	"""Determines if a given host exists within a given netgroup."""

	try:
		# Try to switch to 'str' objects rather than unicode
		host     = host.encode('utf8')
		netgroup = netgroup.encode('utf8')
	except Exception:
		# Ignore, might already have been a str
		pass

	libc = CDLL('libc.so.6')

	try:
		found = libc.innetgr(netgroup,host,None,None)
		if found == 1:
			return True
		else:
			return False
	except Exception:
		return False
