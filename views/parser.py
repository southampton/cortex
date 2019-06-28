import json

filename = 'documentation.json'

with open(filename, 'r') as documentation:
    data = documentation.read()

result = json.loads(data)

outcome = {}

# These two for loops will generate the JSON object
# which contains the class names and their parameters.
# Basically just truncating the useless data
for class_obj in result['puppet_classes']:
	for tag in class_obj['docstring']['tags']:
		if class_obj['name'] in outcome:
			outcome[class_obj['name']].append(tag['name'])
		else:
			outcome[class_obj['name']] = [tag['name']]

print(json.dumps(outcome, indent=4, sort_keys=True))
