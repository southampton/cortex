
import MySQLdb as mysql

from corpus.puppetdb_connector import PuppetDBConnector
from corpus.sn_puppet_connector import SNPuppetConnector


def run(helper, options):

	# Connect to database.
	db = helper.db_connect()

	# Create the PuppetDB connector object.
	puppet_connector = PuppetDBConnector(
		host = helper.config['PUPPETDB_HOST'],
		port = helper.config['PUPPETDB_PORT'],
		ssl_cert = helper.config['PUPPETDB_SSL_CERT'],
		ssl_key = helper.config['PUPPETDB_SSL_KEY'],
		ssl_verify = helper.config['PUPPETDB_SSL_VERIFY'],
	)

	# Create the ServiceNow connector object.
	sn_connector = SNPuppetConnector(
		sn_host = helper.config['SN_HOST'],
		sn_version = 'v1',
		sn_user = helper.config['SN_USER'],
		sn_pass = helper.config['SN_PASS'],
		puppet_connector = puppet_connector,
	)


	helper.event('puppet_nodes', 'Getting nodes from Puppet')
	nodes = puppet_connector.get_nodes()
	helper.end_event(description="Received nodes from Puppet")

	for node in nodes:
		helper.event('push_facts_to_service_now', 'Pushing facts for node ' + str(node.name) + ' to ServiceNow')

		# Use the cortex database to get the node sys_id.
		curd = db.cursor(mysql.cursors.DictCursor)
		curd.execute('SELECT `name`, `cmdb_id`, `puppet_certname`, `vmware_ram` FROM `systems_info_view` WHERE `puppet_certname`=%s', (node.name,))
		result = curd.fetchone()
		curd.close()
		# Ensure we have a result.
		if result is not None:
			cmdb_id = result["cmdb_id"]

			# If there is no CMDB id then there would be nothing to update.
			if cmdb_id is not None:
				try:
					# Push the facts
					sn_connector.push_facts(node, cmdb_id, vmware_ram=result["vmware_ram"]) # Specifically push the VMware ram from the Cortex DB.
				except Exception as e:
					helper.end_event(description='Failed to push facts for node ' + str(node.name) + ' Exception: ' + str(e), success=False)
				else:
					helper.end_event(description='Successfully pushed facts for node ' + str(node.name) + ' with CMDB ID ' + str(cmdb_id))
			else:
				helper.end_event(description='CMDB ID not found for node ' + str(node.name) + ' in the Cortex DB', success=False)

		else:
			# No result found - the certname of this node is not in the cortex db.
			helper.end_event(description='No result for node ' + str(node.name) + ' in the Cortex DB.', success=False)
