from flask import Blueprint, Response, request, session, redirect
from flask_restx import Api
from functools import wraps
import json

import cortex
import cortex.lib.user
import cortex.lib.core
from cortex.api.exceptions import InvalidPermissionException, UnauthorizedException, NoResultsFoundException

# Create an API Blueprint.
api_blueprint = Blueprint('api', __name__, url_prefix='/api')

# Hacky way to fix a weird redirect issue.
@api_blueprint.route('/')
@api_blueprint.route('')
def handle_redirect():
	return redirect('/api/docs')

# Create an API manager
api_version = cortex.app.config.get('API_VERSION', '1.0')
api_manager = Api(
	api_blueprint,
	title = 'Cortex API',
	version = api_version,
	description = 'Cortex API, Version {0}'.format(api_version),
	doc='/docs'
)

def send_auth_required_response(allow_api_token = False):
	"""
	Send a 401 response.
	"""
	x_auth_token_message = ""
	if allow_api_token:
		x_auth_token_message = " or an API token via the X-Auth-Token header"
	return Response(
		response = json.dumps({'message':'Authentication is required: please provide your username and password via HTTP authentication' + x_auth_token_message + '.', 'error_code': 401}),
		status = 401,
		headers = {'WWW-Authenticate': 'Basic realm="Login Required"'},
		mimetype = 'application/json',
	)

def api_login_required(require_permission=None, allow_api_token=False):
	def decorator(f):
		"""
		This is a decorator function that ensures the user has logged into the API.
		"""
		@wraps(f)
		def decorated_function(*args, **kwargs):
			token_auth = False
			if not cortex.lib.user.is_logged_in():
				auth = request.authorization
				if not auth:
					if not allow_api_token:
						return send_auth_required_response(allow_api_token)
					else:
						if 'X-Auth-Token' not in request.headers:
							return send_auth_required_response(allow_api_token)
						else:
							if cortex.app.config['CORTEX_API_AUTH_TOKEN'] != request.headers['X-Auth-Token']:
								raise UnauthorizedException
							else:
								token_auth = True
				else:
					if not cortex.lib.user.authenticate(auth.username, auth.password):
						raise UnauthorizedException

				if not token_auth:
					# Mark as logged on
					session['username'] = auth.username.lower()
					session['logged_in'] = True

					# Log a successful login
					cortex.lib.core.log(__name__, 'cortex.api.login', '' + session['username'] + ' logged in (on API) using ' + request.user_agent.string)
				else:
					session['api_token_valid'] = True

			if not token_auth and require_permission is not None:
				if not cortex.lib.user.does_user_have_permission('api.{0}'.format(require_permission)):
					raise InvalidPermissionException
			return f(*args, **kwargs)
		return decorated_function
	return decorator

# Error handlers.
@api_manager.errorhandler
def default_error_handler(e):
	return {'message':'An unhandled exception occurred.', 'error_code':500}, 500

@api_manager.errorhandler(InvalidPermissionException)
def invalid_permission_handler(e):
	return {'message':str(e), 'error_code': e.status_code}, e.status_code

@api_manager.errorhandler(UnauthorizedException)
def invalid_permission_handler(e):
	return {'message':str(e), 'error_code': e.status_code}, e.status_code

@api_manager.errorhandler(NoResultsFoundException)
def invalid_permission_handler(e):
	return {'message':str(e), 'error_code': e.status_code}, e.status_code

# Add the namespaces.
from cortex.api.endpoints.systems_info_view import systems_info_view_namespace
from cortex.api.endpoints.tasks import tasks_namespace
from cortex.api.endpoints.dns import dns_namespace
from cortex.api.endpoints.puppet import puppet_modules_info_namespace
from cortex.api.endpoints.certificates import certificates_namespace

api_manager.namespaces.pop(0)
api_manager.add_namespace(systems_info_view_namespace)
api_manager.add_namespace(tasks_namespace)
api_manager.add_namespace(dns_namespace)
api_manager.add_namespace(puppet_modules_info_namespace)
api_manager.add_namespace(certificates_namespace)

