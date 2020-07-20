
import MySQLdb as mysql

# bin/neocortex modifies sys.path so these are importable.
# pylint: disable=import-error
from corpus.puppetdb_connector import PuppetDBConnector
# pylint: enable=import-error


def run(helper, _options):
	"""
	Queries PuppetDB and updates `puppet_nodes` with last report status
	I.e. `last_failed`, `last_changed` and `noop_since`.
	"""

	# Create the PuppetDB object.
	helper.event("puppetdb_connect", "Connecting to PuppetDB.")
	puppet = PuppetDBConnector(
		host=helper.config["PUPPETDB_HOST"],
		port=helper.config["PUPPETDB_PORT"],
		ssl_cert=helper.config["PUPPETDB_SSL_CERT"],
		ssl_key=helper.config["PUPPETDB_SSL_KEY"],
		ssl_verify=helper.config["PUPPETDB_SSL_VERIFY"],
	)
	helper.end_event(description="Successfully connected to PuppetDB.")

	# Get the nodes from PuppetDB.
	helper.event("puppet_nodes", "Getting nodes from PuppetDB.")
	nodes = puppet.get_nodes(with_status=True)
	helper.end_event(description="Received nodes from PuppetDB.")

	# Create a database cursor
	curd = helper.db.cursor(mysql.cursors.DictCursor)

	# Iterate over the nodes.
	helper.event("puppet_nodes_status", "Updating database with last Puppet report information.")
	for node in nodes:
		# Use the clientnoop fact to decide if the node is actually in noop.
		noop = node.fact("clientnoop").value

		# Fetch `noop_since` from `puppet_nodes`
		curd.execute("SELECT `noop_since` FROM `puppet_nodes` WHERE `certname` = %s", (node.name,))
		puppet_node = curd.fetchone()

		# If the puppet_node is None or empty this node is not in our `puppet_nodes` table.
		# (Thus we don't really care about it...)
		if not puppet_node:
			continue

		if noop:
			if not puppet_node["noop_since"]:
				curd.execute("UPDATE `puppet_nodes` SET `noop_since` = %s WHERE `certname` = %s", (node.report_timestamp, node.name))

		else:
			if puppet_node["noop_since"]:
				curd.execute("UPDATE `puppet_nodes` SET `noop_since` = NULL WHERE `certname` = %s", (node.name, ))
			if node.status == "failed":
				curd.execute("UPDATE `puppet_nodes` SET `last_failed` = %s WHERE `certname` = %s", (node.report_timestamp, node.name))
			elif node.status == "changed":
				curd.execute("UPDATE `puppet_nodes` SET `last_changed` = %s WHERE `certname` = %s", (node.report_timestamp, node.name))

	helper.end_event(description="Database updated successfully.")
