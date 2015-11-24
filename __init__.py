#!/usr/bin/python
#

from flask import Flask
import logging
import os.path
from logging.handlers import SMTPHandler
from logging.handlers import RotatingFileHandler
from logging import Formatter
from cortex.fapp import CortexFlask
from datetime import timedelta

################################################################################
#### Default config options

## Debug mode. This engages the web-based debug mode
DEBUG = False

## Enable the debug toolbar. DO NOT DO THIS ON A PRODUCTION SYSTEM. EVER. It exposes SECRET_KEY.
DEBUG_TOOLBAR = False

## Session signing key
# Key used to sign/encrypt session data stored in cookies.
# If you've set up cortex behind a load balancer then this must match on all
# web servers.
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

## Redis
REDIS_ENABLED=True
REDIS_HOST='localhost'
REDIS_PORT=6379

## MySQL
MYSQL_HOST='localhost'
MYSQL_USER='cortex'
MYSQL_PW=''
MYSQL_DB=''
MYSQL_PORT=3306

## CMDB Integration
CMDB_URL_FORMAT="http://localhost/cmdb/%s"
CMDB_CLASS_NAMES={'cmdb_ci_esx_server': 'VMware ESXi Server', 'cmdb_ci_linux_server': 'Linux Server', 'cmdb_ci_win_server': 'Windows Server', 'cmdb_ci_solaris_server': 'Solaris Server', 'cmdb_ci_server': 'Generic Server', 'cmdb_ci': 'Unknown'}

## Cortex internal version number
VERSION='0.1'

## Flask defaults (changed to what we prefer)
SESSION_COOKIE_SECURE      = False
SESSION_COOKIE_HTTPONLY    = False
PREFERRED_URL_SCHEME       = 'http'
PERMANENT_SESSION_LIFETIME = timedelta(days=7)

## LDAP AUTH
LDAP_URI            = 'ldaps://localhost.localdomain'
LDAP_SEARCH_BASE    = ''
LDAP_USER_ATTRIBUTE = 'sAMAccountName' ## default to AD style as lets face it, sadly, most people use it :'(
LDAP_ANON_BIND      = True
LDAP_BIND_USER      = ''
LDAP_BIND_PW        = ''

## login background random int.
LOGIN_IMAGE_RANDOM_MAX = 17

## TOTP 2-factor auth
TOTP_ENABLED = False
TOTP_IDENT   = 'cortex'

## Infoblox server
INFOBLOX_HOST = "localhost" 
INFOBLOX_USER = "user"
INFOBLOX_PASS = "pass"

## VMWare vCenter configuration
VMWARE_HOST = "localhost"
VMWARE_PORT = 443
VMWARE_USER = ""
VMWARE_PASS = ""

## Neocortex is a daemon 
NEOCORTEX_KEY="changeme"

WORKFLOWS_DIR="/data/cortex/workflows/"

################################################################################

# set up our application
app = CortexFlask(__name__)

# load default config
app.config.from_object(__name__)

# try to load config from various paths
if os.path.isfile('/etc/cortex.conf'):
	app.config.from_pyfile('/etc/cortex.conf')
elif os.path.isfile('/etc/cortex/cortex.conf'):
	app.config.from_pyfile('/etc/cortex/cortex.conf')
elif os.path.isfile('/data/cortex/cortex.conf'):
	app.config.from_pyfile('/data/cortex/cortex.conf')

## Set up logging to file
if app.config['FILE_LOG'] == True:
	file_handler = RotatingFileHandler(app.config['LOG_DIR'] + '/' + app.config['LOG_FILE'], 'a', app.config['LOG_FILE_MAX_SIZE'], app.config['LOG_FILE_MAX_FILES'])
	file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'))
	app.logger.addHandler(file_handler)

## Set up the max log level
if app.debug:
	app.logger.setLevel(logging.DEBUG)
	file_handler.setLevel(logging.DEBUG)
else:
	app.logger.setLevel(logging.INFO)
	file_handler.setLevel(logging.INFO)

## Output some startup info
app.logger.info('cortex version ' + app.config['VERSION'] + ' initialised')
app.logger.info('cortex debug status: ' + str(app.config['DEBUG']))

# set up e-mail alert logging
if app.config['EMAIL_ALERTS'] == True:
	## Log to file where e-mail alerts are going to
	app.logger.info('cortex e-mail alerts are enabled and being sent to: ' + str(app.config['ADMINS']))

	## Create the mail handler
	mail_handler = SMTPHandler(app.config['SMTP_SERVER'], app.config['EMAIL_FROM'], app.config['ADMINS'], app.config['EMAIL_SUBJECT'])

	## Set the minimum log level (errors) and set a formatter
	mail_handler.setLevel(logging.ERROR)
	mail_handler.setFormatter(Formatter("""
A fatal error occured in Cortex.

Message type:       %(levelname)s
Location:           %(pathname)s:%(lineno)d
Module:             %(module)s
Function:           %(funcName)s
Time:               %(asctime)s
Logger Name:        %(name)s
Process ID:         %(process)d

Further Details:

%(message)s

"""))

	app.logger.addHandler(mail_handler)

## Debug Toolbar
if app.config['DEBUG_TOOLBAR']:
	app.debug = True
	from flask_debugtoolbar import DebugToolbarExtension
	toolbar = DebugToolbarExtension(app)
	app.logger.info('cortex debug toolbar enabled - DO NOT USE THIS ON PRODUCTION SYSTEMS!')

# load core functions
import cortex.core
import cortex.errors
import cortex.admin

# load view functions
import cortex.views
import cortex.systemviews
import cortex.statsviews

#if app.config['TOTP_ENABLED']:
#	if app.config['REDIS_ENABLED']:
#		import cortex.totp
#	else:
#		app.logger.error("Cannot enable TOTP 2-factor auth because REDIS is not enabled")

# load jinja functions
app.jinja_env.globals['csrf_token']         = core.generate_csrf_token
app.jinja_env.filters['class_display_name'] = core.class_display_name

# preload workflows
app.load_workflows()
