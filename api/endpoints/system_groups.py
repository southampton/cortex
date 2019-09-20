from flask import request, session, jsonify, g
from flask_restplus import Resource
import math
import json

from cortex import app
from cortex.api import api_manager, api_login_required
from cortex.api.exceptions import BadRequestException

from cortex.lib.user import does_user_have_permission
import cortex.lib.core
import MySQLdb as mysql

system_groups_namespace = api_manager.namespace('system_groups', description='System Groups API')

@system_groups_namespace.route('/')
class SystemGroups(Resource):
	"""
	API Handler for Puppet module info
	"""

	@api_login_required('get')
	def get(self):
		"""
		Returns details about the current system groups
		"""

		# Get the database cursor
		curd = g.db.cursor(mysql.cursors.DictCursor)

		# Turn off autocommit cause a lot of insertions are going to be used
		curd.connection.autocommit(False)
		
		# Get all the details about a system group
		curd.execute("SELECT * FROM `system_groups`")
		
		groups = curd.fetchall()

		result = {}
		
		# For each system in the group
		for row in groups:

			# Get details about all the systems which are part of the group
			curd.execute("SELECT * FROM `system_group_systems` WHERE `group_id`=%s ORDER BY `order`", (row['id'],))

			group_systems = curd.fetchall()
			
			result[row['id']] = {'group_name': row['name'], 'notifyee': row['notifyee'], 'systems_list':[]}
			
			# Append each set of system details to the result dictionary
			for system in group_systems:
				result[row['id']]['systems_list'].append({'system_id': system['system_id'], 'restart_info': system['restart_info'], 'order':system['order']})
				
		return result
		
@system_groups_namespace.route('/update')
class SystemGroupsUpdate(Resource):

	@app.disable_csrf_check
	@api_login_required(allow_api_token=True)
	def post(self):
		
		request_data = request.json
		
		# Collect the base data about the system group which needs to be added/updated
		group_id = request_data.get('group_id', None)
		group_name = request_data['group_name']
		notifyee = request_data.get('notifyee', None)

		systems_list = request_data.get('systems_list', None)
		
		# Get DB cursor
		curd = g.db.cursor(mysql.cursors.DictCursor)

		# Turn off autocommit
		curd.connection.autocommit(False)
		
		# Check if the group already exists
		curd.execute("SELECT COUNT(*) AS count FROM `system_groups` WHERE `id`=%s", (group_id,))
		
		if group_name is None:
			raise BadRequestException
		
		if curd.fetchone()['count'] == 0 or group_id == None:
			
			# The group does not already exist, so insert it into the database
			curd.execute("INSERT INTO `system_groups`(`name`, `notifyee`) VALUES(%s, %s)", (group_name, notifyee,))
			
			# Insert each system into the database as well
			for system in systems_list:

				# Remeber that an existing system can be part of a group, so you should do both updates and insertions for them
				# Get the id which was allocated to the system group
				curd.execute("SELECT `id` FROM `system_groups` WHERE `name`=%s", (group_name,))
				group_id = curd.fetchone()['id']
				
				# insert each system into the database
				if 'system_id' in system and system['system_id'] is not None:
					curd.execute("INSERT INTO `system_group_systems`(`group_id`, `system_id`, `restart_info`, `order`) VALUES(%s, %s, %s, %s)", (group_id, system['system_id'], system['restart_info'], system['order'],))
				
		elif group_id is not None:
			
			curd.execute("UPDATE `system_groups` SET `name`=%s, `notifyee`=%s WHERE `id`=%s", (group_name, notifyee, group_id,))
			
			for system in systems_list:
				curd.execute("UPDATE `system_group_systems` SET `restart_info`=%s, `order`=%s WHERE `group_id`=%s AND `system_id`=%s", (system['restart_info'], system['order'], group_id, system['system_id'],))
		
		g.db.commit()

		return json.dumps({'success':True}), 200, {'ContentType':'application/json'}

@system_groups_namespace.route('/delete/<int:group_id>')
class SystemGroupsDeleteGroup(Resource):
	
	@app.disable_csrf_check
	@api_login_required(allow_api_token=True)
	def delete(self, group_id):
		
		# Get the DB cursor
		curd = g.db.cursor(mysql.cursors.DictCursor)

		# Turn off autocommit
		curd.connection.autocommit(False)
		
		# Delete the group
		curd.execute("DELETE FROM `system_groups` WHERE `id`=%s", (group_id,))

		# Remove all the systems which are part of that group
		curd.execute("DELETE FROM `system_group_systems` WHERE `group_id`=%s", (group_id,))

		# commit the changes
		g.db.commit()
		
		# Return an OK 200
		return json.dumps({'success':True}), 200, {'ContentType':'application/json'}

@system_groups_namespace.route('/delete/<int:group_id>/<int:system_id>')
class SystemGroupsDeleteSystem(Resource):

	@app.disable_csrf_check
	@api_login_required(allow_api_token=True)
	def delete(self, group_id, system_id):
		
		# Get the DB cursor
		curd = g.db.cursor(mysql.cursors.DictCursor)

		# Turn off autocommit
		curd.connection.autocommit(False)

		# Remove the system from the group
		curd.execute("DELETE FROM `system_group_systems` WHERE `group_id`=%s AND `system_id`=%s", (group_id, system_id,))

		# commit the changes
		g.db.commit()
		
		# Return an OK 200
		return json.dumps({'success':True}), 200, {'ContentType':'application/json'}



@system_groups_namespace.route('/control/<int:group_id>/<string:action>')
@api_manager.doc(params={'group_id':'The ID of the group which the command is being sent to', 'action':'The command which should be executed'})
class SystemGroupsControl(Resource):

	@app.disable_csrf_check
	@api_login_required(allow_api_token=True)
	def post(self, group_id, action):
			
		cortex.lib.systems.execute_system_group_action(action, group_id)

		return json.dumps({'success':True}), 200, {'ContentType':'application/json'}
