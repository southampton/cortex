from flask_restplus import reqparse

pagination_arguments = reqparse.RequestParser()
pagination_arguments.add_argument(
	'page', type=int, required=False, default=1, help='Page Number'
)
pagination_arguments.add_argument(
	'per_page', type=int, required=False, choices=[10, 15, 50, 100], default=10, help='Results per page'
)
puppet_post_args = reqparse.RequestParser()

puppet_info_root = reqparse.RequestParser()
puppet_info_root.add_argument('modules', type=dict)

puppet_info_module = reqparse.RequestParser()
puppet_info_module.add_argument('module_name', type=dict, location=('modules',))

puppet_info_class = reqparse.RequestParser()
puppet_info_class.add_argument('class_name', type=dict, location=('module_name',))

puppet_info_parameter = reqparse.RequestParser()
puppet_info_parameter.add_argument('class_parameter', type=dict, location=('class_name',))

puppet_info_description = reqparse.RequestParser()
puppet_info_description.add_argument('description', location=('class_parameter',))

puppet_info_tag = reqparse.RequestParser()
puppet_info_tag.add_argument('tag_name', location=('class_parameter',))


















puppet_post_args.add_argument('module_name')
puppet_post_args.add_argument('class_name')
puppet_post_args.add_argument('class_parameter')
puppet_post_args.add_argument('description')
puppet_post_args.add_argument('tag_name')

