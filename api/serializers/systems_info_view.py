from flask_restx import fields
from cortex.api import api_manager
from cortex.api.serializers import pagination

systems_info_view_serializer = api_manager.model('systems_info_view', {
	'id': fields.Integer(required=True, description='System\'s ID.'),
	'type': fields.Integer(required=False, description='System\'s Type.'),
	'class': fields.String(required=False, description='System\'s Class.'),
	'number': fields.Integer(required=False, description='System\'s Number.'),
	'name': fields.String(required=False, description='System\'s Name.'),
	'allocation_date': fields.DateTime(required=False, description='The date this System was allocated.'),
	'expiry_date': fields.DateTime(required=False, description='The date this System will expire.'),
	'decom_date': fields.DateTime(required=False, description='The date this System was decommissioned.'),
	'allocation_who': fields.String(required=False, description='Who allocated this System.'),
	'allocation_who_realname': fields.String(required=False, description='Real name of the user who allocated this System.'),
	'allocation_comment': fields.String(required=False, description='Comment provided to Cortex when allocating this System.'),
	'review_status': fields.Integer(required=False, description='System\'s Review Status.'),
	'review_task': fields.String(required=False, description='System\'s Review Task.'),
	'cmdb_id': fields.String(required=False, description='System\'s ID in the CMDB.'),
	'build_count': fields.Integer(required=False, description='System\'s build count, the number of times the system has been built.'),
	'primary_owner_who': fields.String(required=False, description='System\'s primary owner.'),
	'primary_owner_role': fields.String(required=False, description='System\'s primary owner\'s role.'),
	'primary_owner_who_realname': fields.String(required=False, description='System\'s primary owner\'s realname.'),
	'secondary_owner_who': fields.String(required=False, description='System\'s secondary owner.'),
	'secondary_owner_role': fields.String(required=False, description='System\'s secondary owner\'s role.'),
	'secondary_owner_who_realname': fields.String(required=False, description='System\'s secondary owner\'s realname.'),
	'cmdb_sys_class_name': fields.String(required=False, description='System\'s class name in the CMDB.'),
	'cmdb_name': fields.String(required=False, description='System\'s name in the CMDB.'),
	'cmdb_operational_status': fields.String(required=False, description='System\'s operational status in the CMDB.'),
	'cmdb_u_number': fields.String(required=False, description='System\'s CMDB ID.'),
	'cmdb_environment': fields.String(required=False, description='System\'s environment in the CMDB.'),
	'cmdb_description': fields.String(required=False, description='System\'s description in the CMDB.'),
	'cmdb_comments': fields.String(required=False, description='Comments provided about the system in the CMDB.'),
	'cmdb_os': fields.String(required=False, description='The System\'s OS recorded in the CMDB.'),
	'cmdb_short_description': fields.String(required=False, description='System\'s short description in the CMDB.'),
	'cmdb_is_virtual': fields.Boolean(required=False, description='Whether the System is flagged as virtual in the CMDB.'),
	'vmware_name': fields.String(required=False, description='System\'s name in VMware.'),
	'vmware_vcenter': fields.String(required=False, description='The VMware vCenter this System is managed by.'),
	'vmware_uuid': fields.String(required=False, description='System\'s VMware UUID.'),
	'vmware_cpus': fields.Integer(required=False, description='System\'s CPU count in VMware.'),
	'vmware_ram': fields.Integer(required=False, description='System\'s RAM in VMware.'),
	'vmware_guest_state': fields.String(required=False, description='System\'s guest state in VMware.'),
	'vmware_os': fields.String(required=False, description='System\'s OS recorded in VMware.'),
	'vmware_hwversion': fields.String(required=False, description='System\'s VMware hardware version.'),
	'vmware_ipaddr': fields.String(required=False, description='System\'s IP Address in VMware.'),
	'vmware_tools_version_status': fields.String(required=False, description='VMware tools status on this Guest.'),
	'vmware_hostname': fields.String(required=False, description='System\'s hostname in VMware.'),
	'puppet_certname': fields.String(required=False, description='System\'s Puppet certificate name.'),
	'puppet_env': fields.String(required=False, description='System\'s Puppet environment.'),
	'puppet_include_default': fields.Boolean(required=False, description='Whether to include the Puppet default classes.'),
	'puppet_classes': fields.String(required=False, description='Puppet classes applied to this System'),
	'puppet_variables': fields.String(required=False, description='Puppet variables applied to this System.'),
})

page_systems_info_view_serializer = api_manager.inherit('Paginated systems_info_view', pagination, {
	'items': fields.List(fields.Nested(systems_info_view_serializer))
})

