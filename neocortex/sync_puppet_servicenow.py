#!/usr/bin/python

import MySQLdb as mysql
from corpus import SNPuppetConnector

def run(helper, options):

	# Connect to database.
	db = helper.db_connect()

	# Create the connector object.
	connector = SNPuppetConnector.SNPuppetConnector(
		sn_host = helper.config['SN_HOST'],
		sn_version = 'v1',
		sn_user = helper.config['SN_USER'],
		sn_pass = helper.config['SN_PASS'],
		puppet_host = helper.config['PUPPETDB_HOST'],
		puppet_port = helper.config['PUPPETDB_PORT'],
		puppet_ssl_cert = helper.config['PUPPETDB_SSL_CERT'],
		puppet_ssl_key = helper.config['PUPPETDB_SSL_KEY'],
		puppet_ssl_verify = helper.config['PUPPETDB_SSL_VERIFY'],
	)

	helper.event('puppet_nodes', 'Getting nodes from Puppet')
	nodes = connector.get_nodes_from_puppet()
	helper.end_event(description="Received nodes from Puppet")

	for node in nodes:
		helper.event('push_facts_to_service_now', 'Pushing facts for node ' + str(node.name) + ' to ServiceNow')

		# Use the cortex database to get the node sys_id.
		curd = db.cursor(mysql.cursors.SSDictCursor)
		curd.execute('SELECT `name`, `cmdb_id`, `puppet_certname`, `vmware_ram` FROM `systems_info_view` WHERE `puppet_certname`="%s"' %(node.name))		
		result = curd.fetchone()
		curd.close()
		# Ensure we have a result.
		if result is not None:
			cmdb_id = result["cmdb_id"]

			# If there is no CMDB id then there would be nothing to update.
			if cmdb_id is not None:
				try:
					# push the facts
					connector.push_facts(node, cmdb_id, vmware_ram=result["vmware_ram"])
				except Exception as e:
					helper.end_event(description='Failed to push facts for node ' + str(node.name), success=False)
				else:
					helper.end_event(description='Successfully pushed facts for node ' + str(node.name) + ' with CMDB ID ' + str(cmdb_id))

		else:
			# No result found - the certname of this node is not in the cortex db.
			helper.end_event(description='No result for node ' + str(node.name) + ' in the Cortex DB.', success=False)
