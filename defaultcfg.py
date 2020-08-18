from datetime import timedelta

## Debug mode. This engages the web-based debug mode
DEBUG = False

# Key used to sign session data stored in cookies.
SECRET_KEY = ''

## File logging
FILE_LOG = True
LOG_FILE = 'cortex.log'
LOG_DIR = '/tmp'
LOG_FILE_MAX_SIZE = 1 * 1024 * 1024
LOG_FILE_MAX_FILES = 10

EMAIL_ALERTS = False
ADMINS = ['root']
SMTP_SERVER = 'localhost'
EMAIL_FROM = 'root'
EMAIL_SUBJECT = 'Cortex Runtime Error'
EMAIL_DOMAIN = 'localdomain'

## Redis
REDIS_HOST = 'localhost'
REDIS_PORT = 6379

#USER auth mode
#can be 'cas' or 'ldap'
DEFAULT_USER_AUTH = 'cas'

#CAS configuration
CAS_SERVER_URL = 'https://domain.invalid/'
CAS_SERVICE_URL = 'https://cortex.invalid/cas'

## MySQL
MYSQL_HOST = 'localhost'
MYSQL_USER = 'cortex'
MYSQL_PASS = ''
MYSQL_NAME = 'cortex'
MYSQL_PORT = 3306

## CMDB Integration
CMDB_URL_FORMAT = "http://localhost/cmdb/%s"
PRJTASK_URL_FORMAT = "http://localhost/pm_project_task/%s"

## Cortex internal version number
VERSION = '6.0.3'

## Flask defaults (changed to what we prefer)
SESSION_COOKIE_SECURE = False
SESSION_COOKIE_HTTPONLY = False
PREFERRED_URL_SCHEME = 'http'
PERMANENT_SESSION_LIFETIME = timedelta(days=7)

## LDAP AUTH
LDAP_URI = 'ldaps://localhost.localdomain'
LDAP_GROUP_SEARCH_BASE = ''
LDAP_USER_SEARCH_BASE = ''
LDAP_USER_ATTRIBUTE = 'sAMAccountName'
LDAP_BIND_USER = ''
LDAP_BIND_PW = ''

# Infoblox server
INFOBLOX_HOST = ""
INFOBLOX_USER = ""
INFOBLOX_PASS = ""

# ServiceNow instance
SN_HOST = ''
SN_USER = ''
SN_PASS = ''
CMDB_URL_FORMAT = 'https://myinstance.service-now.com/nav_to.do?uri=cmdb_ci_server.do?sys_id=%s'
CMDB_CACHED_CLASSES = {'cmdb_ci_server': 'Server'}

# VMware configuration
VMWARE = {}
VMWARE_CACHE_UPDATE_TIMEOUT = 1800

# Do not raise exceptions if Cortex cannot talk to the vCenter
HANDLE_UNAVAILABLE_VCENTER_GRACEFULLY = True

# Neocortex is a daemon
NEOCORTEX_KEY = 'changeme'
NEOCORTEX_SET_GID = 'nginx'
NEOCORTEX_SET_UID = 'nginx'
WORKFLOWS_DIR = '/data/cortex/workflows/'
NEOCORTEX_TASKS_DIR = '/data/cortex/cortex/neocortex'

# Other
ENVIRONMENTS = []

## API pre-shared keys
# used by puppet master to get ENC data
ENC_API_AUTH_TOKEN = 'changeme'
# used by all other API calls
CORTEX_API_AUTH_TOKEN = 'changeme'

# PuppetDB
PUPPETDB_HOST = ''
PUPPETDB_PORT = 8081
PUPPETDB_SSL_VERIFY = False
PUPPETDB_SSL_CERT = ''
PUPPETDB_SSL_KEY = ''

# Cortex Puppet Bridge (Puppet autosign server)
PUPPET_MASTER = 'puppet.yourdomain.tld'
PUPPET_AUTOSIGN_URL = 'https://yourserver.tld/getcert'
PUPPET_AUTOSIGN_KEY = 'changeme'
PUPPET_AUTOSIGN_VERIFY = False

# Graphite
GRAPHITE_URL = 'https://graphite.yourdomain.tld'
GRAPHITE_USER = 'user'
GRAPHITE_PASS = 'pass'

# Red Hat Satellite Keys
SATELLITE_KEYS = {
	'el7s' : {
		'development': 'changeme'
	}
}

# Cortex Windwos RPC configuration
WINRPC = {
	'development': {'host': 'cortex-win-rpc.yourdomain.tld', 'port': 1888, 'domain': 'yourdomain.tld', 'key': 'changeme'},
}

# Cortex domain name (mostly needed by tasks who have no concept of what URL we're on)
CORTEX_DOMAIN = 'localdomain'

# VM Review configuration: the sys_id of the user who opens the task
REVIEW_TASK_OPENER_SYS_ID = ""

# VM Review configuration: the name of the team who owns the task
REVIEW_TASK_TEAM = ""

# VM Review configuration: the sys_id of the project task to create new tasks under
REVIEW_TASK_PARENT_SYS_ID = ""

# Notification e-mails for new VM creation
NOTIFY_EMAILS = []

# Messages to send to primary/secondary owners when VMs are about to expire. This is a dictionary
# keyed on an arbitrary identifier to a value of a dictionary of the following:
#  - regex: Required. The regex to match system names on
#  - description: Required. The description of the expiry report (to use in Task descriptions in Cortex)
#  - message_start: Optional. The start of the message to send to the user.
#  - message_system: Required. Each line to add for each system due to expire. Can contain {allocator}, {primary_owner}, {secondary_owner}, {name}, {description}, {allocation_date}, {expiry_date}, {days_left}, {os}, {link}, {power_status}, {cmdb_description}, {cmdb_environment}, {cmdb_operational_status}, {cmdb_u_number}, {cmdb_link}
#  - message_end: Optional. The end of the message to send to the user.
#  - when_days: Required. An array of numbers which specify at what point to notify the user (in days remaining to expiry). If a negative number is given, this means "less than x days".
#  - who: Required. An array of people to notify. Each element is either an e-mail address, or @PRIMARY, @SECONDARY, or @ALLOCATOR, for the primary owner, secondary owner or the person who allocated it
#  - weekly_on: Optional. A list of days of when to notify the user. Each item can be one of: MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY.
# Example:
# { 'notify_all': { 'regex': r'.*', 'description': 'My Expiry Notification Report', 'message_start': 'The following VMs will expire soon:\n\n', 'message_system': ' - {name} in {days_left} day(s)\n', 'message_end': '\nPlease review whether these VMs are still required.', 'when_days': [-3, 7, 14, 28], 'who': ['@ALLOCATOR', 'ithelpdesk@yourdomain.tld'] }
SYSTEM_EXPIRE_NOTIFY_CONFIG = {}

# TSM config
TSM_API_URL_BASE = 'https://tsm.yourdomain.tld'
TSM_API_USER = ''
TSM_API_PASS = ''
TSM_API_VERIFY_SERVER = False

# RHN Satellite management (for decom)
RHN5_URL = "https://rhn.yourdomain.tld"
RHN5_USER = "admin"
RHN5_PASS = "admin"
RHN5_CERT = "/usr/share/rhn/RHN-ORG-TRUSTED-SSL-CERT"

# Red Hat Satellite 6 configuration
SATELLITE6_URL = 'https://rhn6.yourdomain.tld'
SATELLITE6_USER = 'admin'
SATELLITE6_PASS = 'admin'
# Associations between VMware clusters and Compute Resources in Satellite 6.
SATELLITE6_CLUSTER_COMPUTE_RESOURCE = {
	"CLUSTER1": 1
}

# Rubrik
RUBRIK_API_URL_BASE = 'https://rubrik.domain.tld/api/'
RUBRIK_API_DEFAULT_VERSION = 'v1'
RUBRIK_API_VERIFY_SERVER = True
RUBRIK_API_USER = 'admin'
RUBRIK_API_PASS = 'admin'
RUBRIK_BACKUP_SCRIPT_CONFIG = {
	"linux": {
		"preBackupScript": {
			"scriptPath": "/path/to/pre-backup.sh",
			"timeoutMs": 60000,
			"failureHandling": "continue"
		},
		"postSnapScript": {
			"scriptPath": "/path/to/post-snapshot.sh",
			"timeoutMs": 60000,
			"failureHandling": "continue"
		},
		"postBackupScript": {
			"scriptPath": "/path/to/post-backup.sh",
			"timeoutMs": 60000,
			"failureHandling": "continue"
		},
	}
}
RUBRIK_NOTIFY_EMAILS = []

# Nessus / Tenable
NESSUS_URL = "https://cloud.tenable.com/"
NESSUS_ACCESS_KEY = ""
NESSUS_SECRET_KEY = ""
NESSUS_SCANNER_ID = ""

# Puppet Module Documentation Location
PUPPET_MODULE_DOCS_URL = None

# Cortex API Config
ERROR_404_HELP = False

# UI Banner
# uncomment the following line to enable the banner
#BANNER_MESSAGE='This is a development instance'

# Active Directory usernames/password
AD_DEV_JOIN_USER = 'Administrator'
AD_DEV_JOIN_PASS = 'password'
AD_PROD_JOIN_USER = 'Administrator'
AD_PROD_JOIN_PASS = 'password'

# When calling the /api/register endpoint, given a build ID, what actions to perform
REGISTER_ACTIONS = {
	'rhel': {
		'satellite': True,
		'puppet': True,
		'dsc': False,
		'password': False,
	},
	'windows': {
		'satellite': False,
		'puppet': False,
		'dsc': True,
		'password': False,
	}
}

# The field in the ServiceNow task that contains the state
SNVM_TASK_STATE_FIELD = 'state'

# The field in the ServiceNow task that contains the JSON description of the VM
SNVM_TASK_DESCRIPTION_FIELD = 'description'

# The field in the ServiceNow task that contains the username
SNVM_TASK_USER_FIELD = 'request_item.request.requested_for.user_name'

# The field in the ServiceNow task that contains the friendly task identiifer
SNVM_TASK_FRIENDLY_ID_FIELD = 'number'

# The field in the JSON description that contains the OS identifier
SNVM_VM_OS_FIELD = 'vm_os'

# The field in the JSON description that contains the VM name
SNVM_VM_NAME_FIELD = 'vm_name'

# The field in the JSON description that contains the network identifier
SNVM_VM_NETWORK_FIELD = 'vm_network'

# The field in the JSON description that contains the expiry date
SNVM_VM_END_DATE_FIELD = 'vm_end_date'

# The regex that covers valid VM names
SNVM_VALID_VM_NAME_REGEX = r'^[A-Za-z0-9\-]{1,14}$'

# A list of valid OS identifiers
SNVM_VALID_OSES = ['linux', 'windows']

# A list of valid network identifiers
SNVM_VALID_NETWORKS = ['internal', 'external']

# A map between valid OS identifiers and the identifier passed to the buildvm workflow
SNVM_OS_TO_BUILD_MAP = {'linux': 'linux', 'windows': 'windows_server_2016'}

# A map between valid OS identifiers and RAM size (GiB)
SNVM_OS_TO_RAM_MAP = {'linux': 4, 'windows': 4}

# A map between valid OS identifiers and number of CPU sockets
SNVM_OS_TO_SOCKETS_MAP = {'linux': 2, 'windows': 2}

# A map between valid OS identifiers and number of cores per CPU socket
SNVM_OS_TO_CORES_MAP = {'linux': 2, 'windows': 2}

# A map between valid OS identifiers and buildvm workflow identifiers
SNVM_OS_TO_BUILDVM_WORKFLOW_MAP = {'linux': 'student', 'windows': 'student'}

# A map between valid OS identifiers and environment
SNVM_OS_TO_ENV_MAP = {'linux': 'production', 'windows': 'production'}

# A map between valid OS identifiers and disk sizes
SNVM_OS_TO_DISK_MAP = {'linux': 0, 'windows': 0}

# A map between valid OS identifiers and clusters
SNVM_OS_TO_CLUSTER_MAP = {'linux': 'CLUSTER1', 'windows': 'CLUSTER1'}

# A map between valid network identifiers and buildvm networks
SNVM_NETWORK_MAP = {'internal': 'internal', 'external': 'external'}

# The maximum number of VMs a user can have
SNVM_USER_VM_LIMIT = 5

# Format string for VM friendly name. Valid fields include {user}, {name}, {task_sys_id}, {task_friendly_id}
SNVM_VM_FRIENDLY_NAME_FORMAT = 'vm-{user}-{name}'

# Domain name for
SNVM_VM_FRIENDLY_NAME_DOMAIN = 'yourdomain.tld'

# Format string for VM purpose. Valid fields include {user}, {name}, {task_sys_id}, {task_friendly_id}
SNVM_VM_PURPOSE_FORMAT = 'VM for {user} - {name}'

# The value of the state field when the task is "open" (ready to be processed)
SNVM_STATE_OPEN = 1

# The value of the state field when the task is "in progress" (i.e. building)
SNVM_STATE_IN_PROGRESS = 2

# The value of the state field when the task is closed and completed (i.e. built)
SNVM_STATE_CLOSED_COMPLETE = 3

# The value of the state field when the task is closed and cancelled (i.e. build was invalid)
SNVM_STATE_CLOSED_CANCELLED = 7

# The value of the state field when the task is closed and failed
SNVM_STATE_CLOSED_INCOMPLETE = 4

# The Cortex workflow to call
SNVM_CORTEX_BUILDVM_TASK_NAME = 'buildvm'

# Work note to add when the user has too many VMs
SNVM_NOTE_TOO_MANY_VMS = 'Your request for a VM was denied as you already have 5 VM(s)'

# Work note for creation started
SNVM_NOTE_CREATION_STARTED = 'Your requested VM has been picked up by Cortex and is entering the build queue.'

# Work note for creation failed
SNVM_NOTE_CREATION_FAILED = 'Your requested VM has failed to build. An administrator has been notified to investigate, who will attempt the build again when possible.'

# Work note for creation succeeded
SNVM_NOTE_CREATION_SUCCEEDED = 'Your requested VM has now been built and is ready to use. You will receive a second e-mail containing details of how to access your VM shortly.'

# Certificate scanning: Which ports to scan
CERT_SCAN_PORTS = [443, 25, 243, 389]

# Certificate scanning: Which ports to try STARTTLS on, and which implementation of STARTTLS to use (currently implemented: smtp, imap, ldap)
CERT_SCAN_PORTS_STARTTLS = {25: 'smtp', 143: 'imap', 389: 'ldap'}

# Certificate scanning: The number of worker processes to start
CERT_SCAN_WORKERS = 50

# Certificate scanning: The maximum amount of time a worker should spend on a single check
CERT_SCAN_THREAD_TIMEOUT = 30

# Certificate scanning: Expire certificates from the database if they've not been seen in a scan in this number of days
CERT_SCAN_EXPIRE_NOT_SEEN = 90

# Certificate scanning: Expire scan results from the database when they're older than this number of days
CERT_SCAN_EXPIRE_RESULTS = 90

# When and how to notify about expiring certs. Fields:
# - days_left: The number of days left on the expiration when we notify. Can be an array.
# - ignore_issuer_dn: Optional. Ignore certificates whose issuer DN matches this regex. Cannot be used with require_issuer_dn.
# - require_issuer_dn: Optional. Match only certificates whose issuer DN matches this regex. Cannot be used with ignore_issuer_dn.
# - type: The method used for notifying. Can be 'email', 'incident' or 'request'.
# - team_name: For type=incident and type=request, the team to assign the ticket to
# - opener_sys_id: For type=incident and type=request, the SNow sysid of the user opening the ticket
# - request_type: For type=request, the SNow sysid of the request type
# - to: For type=email the recipient address
#
# Example: Email root@mydomain on certificates with seven days left:
# [{'days_left': 7, 'type': 'email', 'to': 'root@mydomain'}]
#
# Example: Email root@mydomain on certificates not from Let's Encrypt with thirty days left and raise an incident in ServiceNow for Let's Encrypt certificates with two days left:
# [{'days_left': 2, 'type': 'incident', 'require_issuer_dn': ".*Let's Encrypt.*", 'team_name': 'Certificate Managers', 'opener_sys_id': 'af1d0283e83dfffa08e0b310ccc21901'}, {'days_left: 30, 'type': 'email' 'ignore_issuer_dn': ".*Let's Encrypt.*", 'to': 'root@mydomain'}]
CERT_SCAN_NOTIFY = []

# When doing a DNS lookup that is given just as a hostname, add on this domain
# suffix
DEFAULT_DOMAIN = 'domain'

# For DNS lookups: Consider hostname.anything_in_this_list to be a local domain,
# so add on DEFAULT_DOMAIN
KNOWN_DOMAIN_SUFFIXES = ['test', 'dev']

# Classes to show favourite lists for
FAVOURITE_CLASSES = []
