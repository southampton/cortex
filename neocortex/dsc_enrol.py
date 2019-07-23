import MySQLdb as mysql

def run(helper, options):

	# Set up cursor to access the DB
	curd = helper.db.cursor(mysql.cursors.DictCursor)


	curd.execute("SELECT `id` FROM `systems` WHERE `name` = %s;", (options['machine'], ))
	system_id = curd.fetchone()['id']

	# helper.event("updating db", "Adding machine " + options['machine'] + " to dsc")
	helper.event('fsd',description='INSERT INTO `dsc_config` (system_id, config, roles) VALUES ( ' + options['machine'] + ', "", "");' )

	curd.execute('INSERT INTO `dsc_config` (system_id, config, roles) VALUES (%s, "", "");', (system_id, ))
	helper.db.commit()
	helper.end_event("Committed changes")
