from flask_restx import reqparse

pagination_arguments = reqparse.RequestParser()
pagination_arguments.add_argument(
	'page', type=int, required=False, default=1, help='Page Number'
)
pagination_arguments.add_argument(
	'per_page', type=int, required=False, choices=[10, 15, 50, 100], default=10, help='Results per page'
)
