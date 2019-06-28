import os
import json
import requests
import MySQLdb as mysql
from flask import g

BASE_JSON_DIR_PATH = "/srv/cortex/cortex/test_data"

curd = g.db.cursor(mysql.cursors.DictCursor)
curd.connection.autocommit(False)
outcome = {'puppet_classes':[]}

for json_file in os.listdir(BASE_JSON_DIR_PATH):
	if json_file.endswith(".json"):
		f = open(json_file, 'r')
		content_raw = f.read()
		content_parsed = json.loads(content_raw)
		
		for module in content_parsed['puppet_classes']:
			outcome['puppet_classes'].append(content_parsed['puppet_classes'])

print("Finished gathering the data in a big dict")

for module in outcome['puppet_classes']:
	if "::" in module['name']:
		module_name = module['name'].split("::")[0]
		class_name = module['name'].split("::")[1]
	else:
		module_name = module['name']
		class_name = "init"
	for tag in module['docstring']['tags']:
		class_parameter = tag['name']
		description = tag['text']
		tag_name = tag['tag_name']
		curd.execute("INSERT INTO `puppet_modules_info` (`module_name`, `class_name`, `class_parameter`, `description`, `tag_name`) VALUES (%s, %s, %s, %s, %s)", (module_name, class_name, class_parameter, description, tag_name))

"""
# defining the api-endpoint 
API_ENDPOINT = "http://cortex-acv1y18.dev.soton.ac.uk/puppet_modules_info"

# your API key here 
API_KEY = "XXXXXXXXXXXXXXXXX"


# data to be sent to api 
data = {'api_dev_key':API_KEY, 
		'puppet_modules_info':outcome} 

# sending post request and saving response as response object 
r = requests.post(url = API_ENDPOINT, data = data) 

# extracting response text 
pastebin_url = r.text 
"""
