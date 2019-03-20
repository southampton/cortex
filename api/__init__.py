from flask import Blueprint, Response, request, session, redirect
from flask_restplus import Api
from functools import wraps
import json

import cortex
import cortex.lib.user
import cortex.lib.core
from cortex.api.exceptions import InvalidPermissionException, UnauthorizedException, NoResultsFoundException

api_version = cortex.app.config.get('API_VERSION', '1.0')

api_manager = Api(
	version = api_version,
	title = 'Cortex API',
	description = 'Cortex API, Version {0}'.format(api_version),
	doc='/docs'
)

def send_auth_required_response():
	"""
	Send a 401 response.
	"""
	return Response (
		response = json.dumps({'message':'Authentication is required: please provide your username and password via HTTP authentication.', 'error_code':401}),
		status = 401,
		headers = {'WWW-Authenticate': 'Basic realm="Login Required"'},
		mimetype = 'application/json',
	)

def api_login_required(require_permission=None):
	def decorator(f):
		"""
		This is a decorator function that ensures the user has logged into the API.
		"""
		@wraps(f)
		def decorated_function(*args, **kwargs):
			if not cortex.lib.user.is_logged_in():
				auth = request.authorization
				if not auth:
					return send_auth_required_response()
				if not cortex.lib.user.authenticate(auth.username, auth.password):
					raise UnauthorizedException

				# Mark as logged on
				session['username'] = auth.username.lower()
				session['logged_in'] = True

				# Log a successful login
				cortex.lib.core.log(__name__, 'cortex.api.login', '' + session['username'] + ' logged in using ' + request.user_agent.string)

			if require_permission is not None:
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

api_manager.namespaces.pop(0)
api_manager.add_namespace(systems_info_view_namespace)

# Create an API Blueprint.
api_blueprint = Blueprint('api', __name__, url_prefix='/api')

# Hacky way to fix a weird redirect issue.
@api_blueprint.route('/')
@api_blueprint.route('')
def handle_redirect():
	return redirect('/api/docs')

# Init the restplus api manager.
api_manager.init_app(api_blueprint)

