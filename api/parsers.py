import math

from flask_restx import reqparse

from cortex.api.exceptions import NoResultsFoundException

pagination_arguments = reqparse.RequestParser()
pagination_arguments.add_argument(
	'page', type=int, required=False, default=1, help='Page Number'
)
pagination_arguments.add_argument(
	'per_page', type=int, required=False, choices=[10, 15, 50, 100], default=10, help='Results per page'
)

def process_pagination_arguments(request):
	"""Helper function to process pagination arguments for a request object"""
	args = pagination_arguments.parse_args(request)
	page = args.get('page', 1)
	per_page = args.get('per_page', 10)

	limit_start = (page-1)*per_page
	limit_length = per_page

	return page, per_page, limit_start, limit_length

def pagination_response(results, page, per_page, total):
	"""Helper function to return a JSON pagination response"""

	if not results:
		raise NoResultsFoundException

	return {
		'page': page,
		'per_page': per_page,
		'pages': math.ceil(float(total)/float(per_page)),
		'total': total,
		'items': results,
	}
