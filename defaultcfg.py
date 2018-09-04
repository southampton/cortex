#!/usr/bin/python
from datetime import timedelta

## Debug mode. This engages the web-based debug mode
DEBUG = False

## Enable the debug toolbar. DO NOT DO THIS ON A PRODUCTION SYSTEM. EVER. It exposes SECRET_KEY.
DEBUG_TOOLBAR = False

# Key used to sign session data stored in cookies.
SECRET_KEY = ''

## File logging
FILE_LOG=True
LOG_FILE='cortex.log'
LOG_DIR='/tmp'
LOG_FILE_MAX_SIZE=1 * 1024 * 1024
LOG_FILE_MAX_FILES=10

EMAIL_ALERTS=False
ADMINS=['root']
SMTP_SERVER='localhost'
EMAIL_FROM='root'
EMAIL_SUBJECT='Cortex Runtime Error'
EMAIL_DOMAIN='localdomain'

## Redis
REDIS_HOST='localhost'
REDIS_PORT=6379

#USER auth mode
#can be 'cas' or 'ldap'
DEFAULT_USER_AUTH='cas'

#CAS configuration
CAS_SERVER_URL='https://domain.invalid/'
CAS_SERVICE_URL='https://cortex.invalid/cas'

## MySQL
MYSQL_HOST='localhost'
MYSQL_USER='cortex'
MYSQL_PASS=''
MYSQL_NAME='cortex'
MYSQL_PORT=3306

## CMDB Integration
CMDB_URL_FORMAT="http://localhost/cmdb/%s"
PRJTASK_URL_FORMAT="http://localhost/pm_project_task/%s"

## Cortex internal version number
VERSION='3.0'

## Flask defaults (changed to what we prefer)
SESSION_COOKIE_SECURE      = False
SESSION_COOKIE_HTTPONLY    = False
PREFERRED_URL_SCHEME       = 'http'
PERMANENT_SESSION_LIFETIME = timedelta(days=7)

## LDAP AUTH
LDAP_URI               = 'ldaps://localhost.localdomain'
LDAP_GROUP_SEARCH_BASE = ''
LDAP_USER_SEARCH_BASE  = ''
LDAP_USER_ATTRIBUTE    = 'sAMAccountName'
LDAP_ANON_BIND         = True
LDAP_BIND_USER         = ''
LDAP_BIND_PW           = ''

# Infoblox server
INFOBLOX_HOST = ""
INFOBLOX_USER = ""
INFOBLOX_PASS = ""

# ServiceNow instance
SN_HOST = ''
SN_USER = ''
SN_PASS = ''
CMDB_URL_FORMAT = 'https://myinstance.service-now.com/nav_to.do?uri=cmdb_ci_server.do?sys_id=%s'
CMDB_CACHED_CLASSES={'cmdb_ci_server': 'Server'}

# VMware configuration
VMWARE={}
VMWARE_CACHE_UPDATE_TIMEOUT = 1800

# Do not raise exceptions if Cortex cannot talk to the vCenter
HANDLE_UNAVAILABLE_VCENTER_GRACEFULLY = True

# Neocortex is a daemon 
NEOCORTEX_KEY='changeme'
NEOCORTEX_SET_GID='nginx'
NEOCORTEX_SET_UID='nginx'
WORKFLOWS_DIR='/data/cortex/workflows/'
NEOCORTEX_TASKS_DIR='/data/cortex/cortex/neocortex'

# Other
ENVIRONMENTS = []

## API pre-shared keys
# used by puppet master to get ENC data
ENC_API_AUTH_TOKEN    = 'changeme'
# used by all other API calls
CORTEX_API_AUTH_TOKEN = 'changeme'

# PuppetDB
PUPPETDB_HOST=''
PUPPETDB_PORT=8081
PUPPETDB_SSL_VERIFY=False
PUPPETDB_SSL_CERT=''
PUPPETDB_SSL_KEY=''

# Puppet Autosign server
PUPPET_MASTER='puppet.yourdomain.tld'
PUPPET_AUTOSIGN_URL='https://yourserver.tld/getcert'
PUPPET_AUTOSIGN_KEY='changeme'
PUPPET_AUTOSIGN_VERIFY=False

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
CORTEX_DOMAIN='localdomain'

# VM Review configuration: the sys_id of the user who opens the task
REVIEW_TASK_OPENER_SYS_ID=""

# VM Review configuration: the name of the team who owns the task
REVIEW_TASK_TEAM=""

# VM Review configuration: the sys_id of the project task to create new tasks under
REVIEW_TASK_PARENT_SYS_ID=""

# Notification e-mails for new VM creation
NOTIFY_EMAILS = []

# Regular expression of system names to not put in to VM expiration e-mails
SYSTEM_EXPIRE_NOTIFY_IGNORE_NAMES = r'^$'

# Notification e-mail address 
SYSTEM_EXPIRE_NOTIFY_EMAILS = []

# TSM config
TSM_API_URL_BASE = 'https://tsm.yourdomain.tld'
TSM_API_USER = ''
TSM_API_PASS = ''
TSM_API_VERIFY_SERVER = False

# RHN Satellite management (for decom)
RHN5_URL  = "https://rhn.yourdomain.tld"
RHN5_USER = "admin"
RHN5_PASS = "admin"
RHN5_CERT = "/usr/share/rhn/RHN-ORG-TRUSTED-SSL-CERT"

# Red Hat Satellite 6 configuration
SATELLITE6_URL  = 'https://rhn6.yourdomain.tld'
SATELLITE6_USER = 'admin'
SATELLITE6_PASS = 'admin'

# Rubrik
RUBRIK_API_URL_BASE = ''
RUBRIK_API_USER = ''
RUBRIK_API_PASS = ''

# Puppet Module Documentation Location
PUPPET_MODULE_DOCS_URL = None

# UI Banner
# uncomment the following line to enable the banner
#BANNER_MESSAGE='This is a development instance'

# Active Directory usernames/password
AD_DEV_JOIN_USER='Administrator'
AD_DEV_JOIN_PASS='password'
AD_PROD_JOIN_USER='Administrator'
AD_PROD_JOIN_PASS='password'

# When calling the /api/register endpoint, given a build ID, what actions to perform
REGISTER_ACTIONS = {
	'rhel': {
		'satellite': True,
		'puppet': True,
		'dsc': False,
		'password': False,
	}
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
