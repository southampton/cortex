from urllib.parse import urljoin

import ldap3
import requests
import requests.exceptions
from pyVmomi import vim


def run(helper, options):

	# check if workflows are locked
	if not helper.lib.check_workflow_lock():
		raise Exception("Workflows are currently locked")

	# Iterate over the actions that we have to perform
	for action in options["actions"]:
		# Start the event
		helper.event(action["id"], action["desc"])
		if action["id"] == "task.log":
			r = True
		elif action["id"] == "system.check":
			r = action_check_system(action, helper, options["wfconfig"])
		elif action["id"] == "vm.poweroff":
			r = action_vm_poweroff(action, helper)
		elif action["id"] == "vm.delete":
			r = action_vm_delete(action, helper)
		elif action["id"] == "cmdb.update":
			r = action_cmdb_update(action, helper)
		elif action["id"] == "cmdb.relationships.delete":
			r = action_cmdb_relationships_delete(action, helper)
		elif action["id"] == "dns.delete":
			r = action_dns_delete(action, helper)
		elif action["id"] == "puppet.cortex.delete":
			r = action_puppet_cortex_delete(action, helper)
		elif action["id"] == "puppet.master.delete":
			r = action_puppet_master_delete(action, helper)
		elif action["id"] == "ad.delete":
			r = action_ad_delete(action, helper)
		elif action["id"] == "entca.delete":
			r = action_entca_delete(action, helper)
		elif action["id"] == "ticket.ops":
			r = action_ticket_ops(action, helper, options["wfconfig"])
		elif action["id"] == "tsm.decom":
			r = action_tsm_decom(action, helper)
		elif action["id"] == "rhn5.delete":
			r = action_rhn5_delete(action, helper)
		elif action["id"] == "satellite6.delete":
			r = action_satellite6_delete(action, helper)
		elif action["id"] == "sudoldap.update":
			r = action_sudoldap_update(action, helper, options["wfconfig"])
		elif action["id"] == "sudoldap.delete":
			r = action_sudoldap_delete(action, helper, options["wfconfig"])
		elif action["id"] == "graphite.delete":
			r = action_graphite_delete(action, helper, options["wfconfig"])
		elif action["id"] == "nessus.delete":
			r = action_nessus_delete(action, helper, options["wfconfig"])
		elif action["id"] == "system.update_decom_date":
			r = action_update_decom_date(action, helper)

		# End the event (don't change the description) if the action
		# succeeded. The action_* functions either raise Exceptions or
		# end the events with a failure message on errors.
		if r:
			helper.end_event()
		else:
			raise RuntimeError("Action {} ({}) failed to complete successfully".format(action["desc"], action["id"]))

################################################################################

def action_check_system(action, helper, wfconfig):

	# Actions to perform during decom stage.
	system_actions = []

	# Locate the system
	system = helper.lib.get_system_by_id(action['data']['system_id'])
	system_link = "{{{{system_link id=\"{id}\"}}}}{name}{{{{/system_link}}}}".format(id=system["id"], name=system["name"])
	helper.logger.warning(system_link)
	if system is None:
		helper.end_event(success=False, description="No such system exists with ID {id}.".format(id=system["id"]))
		return False
	else:
		helper.end_event(success=True, description="Found {system_link}.".format(system_link=system_link))

	# Add an action to log later when the actual task begins.
	system_actions.append({"id": "task.log", "desc": "Starting decommission task for {system_link}".format(system_link=system_link)})

	## Is the system linked to vmware?
	if 'vmware_uuid' in system:
		if system['vmware_uuid'] is not None:
			if len(system['vmware_uuid']) > 0:
				## The system is linked to vmware - e.g. a VM exists

				vmobj = helper.lib.vmware_get_vm_by_uuid(system['vmware_uuid'],system['vmware_vcenter'])

				if vmobj:
					if vmobj.runtime.powerState == vim.VirtualMachine.PowerState.poweredOn:
						system_actions.append({'id': 'vm.poweroff', 'desc': 'Power off the virtual machine ' + system_link, 'detail': system['vmware_name'] + ' (UUID ' + system['vmware_uuid'] + ') on ' + system['vmware_vcenter'], 'data': {'uuid': system['vmware_uuid'], 'vcenter': system['vmware_vcenter']}})

					system_actions.append({'id': 'vm.delete', 'desc': 'Delete the virtual machine ' + system_link, 'detail': system['vmware_name'] + ' (UUID ' + system['vmware_uuid'] + ') on ' + system['vmware_vcenter'], 'data': {'uuid': system['vmware_uuid'], 'vcenter': system['vmware_vcenter']}})

	## Is the system linked to service now?
	if 'cmdb_id' in system:
		if system['cmdb_id'] is not None:
			if len(system['cmdb_id']) > 0:
				# Add a task to mark the object as Deleted/Decommissioned
				if system['cmdb_is_virtual']:
					if system['cmdb_operational_status'] != u'Deleted':
						system_actions.append({'id': 'cmdb.update', 'desc': 'Mark the system as Deleted in the CMDB', 'detail': system['cmdb_id'] + " on " + helper.lib.config['SN_HOST'], 'data': system['cmdb_id']})
				else:
					if system['cmdb_operational_status'] != u'Decommissioned':
						system_actions.append({'id': 'cmdb.update', 'desc': 'Mark the system as Decommissioned in the CMDB', 'detail': system['cmdb_id'] + " on " + helper.lib.config['SN_HOST'], 'data': system['cmdb_id']})

				# Remove CI relationships if the exist
				try:
					rel_count = len(helper.lib.servicenow_get_ci_relationships(system['cmdb_id']))
					if rel_count > 0:
						system_actions.append({'id': 'cmdb.relationships.delete', 'desc': 'Remove ' + str(rel_count) + ' relationships from the CMDB CI', 'detail': str(rel_count) + ' entries from ' + system['cmdb_id'] + " on " + helper.lib.config['SN_HOST'], 'data': system['cmdb_id']})
				except Exception as ex:
					helper.flash('Warning - An error occured when communicating with ServiceNow: ' + str(ex), 'warning')


	## Ask Infoblox if a DNS host object exists for the name of the system
	if 'DNS_DOMAINS' in wfconfig and wfconfig['DNS_DOMAINS'] is not None:
		# Ensure we have a list
		dns_domains = wfconfig['DNS_DOMAINS']
		if type(dns_domains) is str:
			dns_domains = [dns_domains]

		# Iterate over domains
		for domain in dns_domains:
			try:
				refs = helper.lib.infoblox_get_host_refs(system['name'] + '.' + str(domain))

				if refs is not None:
					for ref in refs:
						system_actions.append({'id': 'dns.delete', 'desc': 'Delete the DNS record ' + ref.split(':')[-1], 'detail': 'Delete the name ' + system['name'] + '.' + str(domain) + ' - Infoblox reference: ' + ref, 'data': ref})

			except Exception as ex:
				helper.flash('Warning - An error occured when communicating with Infoblox: ' + str(type(ex)) + ' - ' + str(ex), 'warning')

	## Check if a puppet record exists
	if 'puppet_certname' in system:
		if system['puppet_certname'] is not None:
			if len(system['puppet_certname']) > 0:
				system_actions.append({'id': 'puppet.cortex.delete', 'desc': 'Delete the Puppet ENC configuration', 'detail': system['puppet_certname'] + ' on ' + helper.lib.config['CORTEX_DOMAIN'], 'data': system['id']})
				system_actions.append({'id': 'puppet.master.delete', 'desc': 'Delete the system from the Puppet Master', 'detail': system['puppet_certname'] + ' on ' + helper.lib.config['PUPPET_MASTER'], 'data': system['puppet_certname']})

	## Check if TSM backups exist
	try:
		tsm_clients = helper.lib.tsm_get_system(system['name'])
		#if the TSM client is not decomissioned, then decomission it
		for client in tsm_clients:
			if client['DECOMMISSIONED'] is None:
				system_actions.append({'id': 'tsm.decom', 'desc': 'Decommission the system in TSM', 'detail': 'Node ' + client['NAME']  + ' on server ' + client['SERVER'], 'data': {'NAME': client['NAME'], 'SERVER': client['SERVER']}})
	except requests.exceptions.HTTPError as e:
		helper.flash("Warning - An error occured when communicating with TSM: " + str(e), "warning")
	except LookupError:
		pass
	except Exception as ex:
		helper.flash("Warning - An error occured when communicating with TSM: " + str(ex), "warning")

	# We need to check all (unique) AD domains as we register development
	# Linux boxes to the production domain
	tested_domains = set()
	for adenv in helper.lib.config['WINRPC']:
		try:
			# If we've not tested this CortexWindowsRPC host before
			if helper.lib.config['WINRPC'][adenv]['host'] not in tested_domains:
				# Add it to the set of tested hosts
				tested_domains.update([helper.lib.config['WINRPC'][adenv]['host']])

				# If an AD object exists, append an action to delete it from that environment
				if helper.lib.windows_computer_object_exists(adenv, system['name']):
					system_actions.append({'id': 'ad.delete', 'desc': 'Delete the Active Directory computer object', 'detail': system['name'] + ' on domain ' + helper.lib.config['WINRPC'][adenv]['domain'], 'data': {'hostname': system['name'], 'env': adenv}})

		except Exception as ex:
			helper.flash("Warning - An error occured when communicating with Active Directory: " + str(type(ex)) + " - " + str(ex), "warning")

	# Check Enterprise CA certificate
	if 'ENTCA_SERVERS' in wfconfig and wfconfig['ENTCA_SERVERS'] is not None:
		entca_servers = wfconfig['ENTCA_SERVERS']
		if type(entca_servers) is str:
			entca_servers = [entca_servers]

		for entca in entca_servers:
			try:
				r = requests.get('https://' + entca['hostname'] + '/get_entca_certificate/' + system['name'] + '.' + entca['entdomain'], headers={'X-Client-Secret': entca['api_token']}, verify=entca['verify_ssl'])
			except:
				helper.flash("Warning - An error occured when communicating with Enterprise CA", "warning")
			else:
				if r.status_code == 200:
					system_actions.append({'id': 'entca.delete', 'desc': 'Delete certificate from Enterprise CA', 'detail': system['name'] + '.' + entca['entdomain'] + ' to be removed from Enterprise CA ' + entca['hostname'], 'data': {'hostname': system['name'] + '.' + entca['entdomain'], 'entca_hostname': entca['hostname'], 'entca_api_token': entca['api_token'], 'entca_verify_ssl': entca['verify_ssl']}})
				elif r.status_code == 404:
					# Do nothing here, this is a valid result
					pass
				else:
					helper.flash('Warning - An error occured when communicating with Enterprise CA, code: ' + str(r.status_code), 'warning')

	# RHN 5
	if 'RHN5_ENABLE_DECOM' in wfconfig and wfconfig['RHN5_ENABLE_DECOM']:
		## Work out the URL for any RHN systems
		rhnurl = helper.lib.config['RHN5_URL']
		if not rhnurl.endswith("/"):
			rhnurl = rhnurl + "/"
		rhnurl = rhnurl + "rhn/systems/details/Overview.do?sid="

		## Check if a record exists in RHN for this system
		try:
			(rhn,key) = helper.lib.rhn5_connect()
			rsystems = rhn.system.search.hostname(key,system['name'])
			if len(rsystems) > 0:
				for rsys in rsystems:
					system_actions.append({'id': 'rhn5.delete', 'desc': 'Delete the RHN Satellite object', 'detail': rsys['name'] + ', RHN ID <a target="_blank" href="' + rhnurl + str(rsys['id']) + '">' + str(rsys['id']) + "</a>", 'data': {'id': rsys['id']}})
		except Exception as ex:
			helper.flash("Warning - An error occured when communicating with RHN: " + str(ex), "warning")

	## Check if a record exists in SATELLITE 6 for this system.
	try:
		try:
			rsys = helper.lib.satellite6_get_host(system['name'])
		except requests.exceptions.RequestException as ex:
			# Check if the error was raised due to not being able to find the system.
			if ex.response.status_code != 404:
				helper.flash("Warning - An error occured when communicating with Satellite 6: " + str(ex), "warning")
		else:
			saturl = urljoin(helper.lib.config['SATELLITE6_URL'], 'hosts/{0}'.format(rsys['id']))
			system_actions.append({'id': 'satellite6.delete', 'desc': 'Delete the host from Satellite 6', 'detail': '{0}, Satellite 6 ID <a target=""_blank" href="{1}">{2}</a>'.format(rsys['name'], saturl, rsys['id']), 'data': {'id':rsys['id']}})

	except Exception as ex:
		helper.flash("Warning - An error occured when communicating with Satellite 6: " + str(ex), "warning")

	## Check sudoldap for sudoHost entries
	if 'SUDO_LDAP_ENABLE' in wfconfig and wfconfig['SUDO_LDAP_ENABLE']:
		try:
			# Connect to LDAP
			l = ldap3.Connection(
				ldap3.Server(wfconfig['SUDO_LDAP_URL']),
				wfconfig['SUDO_LDAP_USER'],
				wfconfig['SUDO_LDAP_PASS'],
				auto_bind=False
			)

			if not l.bind():
				raise helper.lib.TaskFatalError(message="Failed to bind to the sudoldap server.")

			# This contains our list of changes and keeps track of sudoHost entries
			ldap_dn_data = {}

			# Iterate over the search domains
			for domain_suffix in wfconfig['SUDO_LDAP_SEARCH_DOMAINS']:
				# Prefix '.' to our domain suffix if necessary
				if domain_suffix != '' and domain_suffix[0] != '.':
					domain_suffix = '.' + domain_suffix

				# Get our host entry
				host = system['name'] + domain_suffix

				formatted_filter = wfconfig['SUDO_LDAP_FILTER'].format(host)
				search = l.search(
					search_base=wfconfig['SUDO_LDAP_SEARCH_BASE'],
					search_filter=formatted_filter,
					search_scope=ldap3.SUBTREE,
					attributes=ldap3.ALL_ATTRIBUTES,
				)

				if search and l.response:
					for result in l.response:
						dn = result['dn']

						# Store the sudoHosts for each DN we find
						if dn not in ldap_dn_data:
							ldap_dn_data[dn] = {'cn': result['attributes']['cn'][0], 'sudoHost': result['attributes']['sudoHost'], 'action': 'none', 'count': 0, 'remove': []}

						# Keep track of what things will look like after a deletion (so
						# we can track when a sudoHosts entry becomes empty and as such
						# the entry should be deleted)
						for idx, entry in enumerate(ldap_dn_data[dn]['sudoHost']):
							if entry.lower() == host.lower():
								ldap_dn_data[dn]['sudoHost'].pop(idx)
								ldap_dn_data[dn]['action'] = 'modify'
								ldap_dn_data[dn]['remove'].append(entry)

			# Determine if any of the DNs are now empty
			for dn in ldap_dn_data:
				if len(ldap_dn_data[dn]['sudoHost']) == 0:
					ldap_dn_data[dn]['action'] = 'delete'

			# Print out system_actions
			for dn in ldap_dn_data:
				if ldap_dn_data[dn]['action'] == 'modify':
					for entry in ldap_dn_data[dn]['remove']:
						system_actions.append({'id': 'sudoldap.update', 'desc': 'Remove sudoHost attribute value ' + entry + ' from ' + ldap_dn_data[dn]['cn'], 'detail': 'Update object ' + dn + ' on ' + wfconfig['SUDO_LDAP_URL'], 'data': {'dn': dn, 'value': entry}})
				elif ldap_dn_data[dn]['action'] == 'delete':
					system_actions.append({'id': 'sudoldap.delete', 'desc': 'Delete ' + ldap_dn_data[dn]['cn'] + ' because we\'ve removed its last sudoHost attribute', 'detail': 'Delete ' + dn + ' on ' + wfconfig['SUDO_LDAP_URL'], 'data': {'dn': dn, 'value': ldap_dn_data[dn]['sudoHost']}})

		except Exception as ex:
			raise ex
			helper.flash('Warning - An error occurred when communicating with ' + str(wfconfig['SUDO_LDAP_URL']) + ': ' + str(ex), 'warning')

	## Check graphite for monitoring entries
	if 'GRAPHITE_DELETE_ENABLE' in wfconfig and wfconfig['GRAPHITE_DELETE_ENABLE']:
		try:
			if not helper.lib.config['GRAPHITE_URL'] == '':
				for suffix in wfconfig['GRAPHITE_DELETE_SUFFIXES']:
					host = system['name'] + suffix
					url = urljoin(helper.lib.config['GRAPHITE_URL'], '/host/' + system['name'] + suffix)
					r = requests.get(url, auth=(helper.lib.config['GRAPHITE_USER'], helper.lib.config['GRAPHITE_PASS']))
					if r.status_code == 200:
						js = r.json()
						if type(js) is list and len(js) > 0:
							system_actions.append({'id': 'graphite.delete', 'desc': 'Remove metrics from Graphite / Grafana', 'detail': 'Delete ' + ','.join(js) + ' from ' + helper.lib.config['GRAPHITE_URL'], 'data': {'host': host}})
					else:
						helper.flash('Warning - CarbonHTTPInterface returned error code ' + str(r.status_code), 'warning')
			else:
				helper.flash('No Graphite URL Supplied, Skipping Step', 'success')
		except Exception as ex:
			helper.flash('Warning - An error occurred when communicating with ' + str(helper.lib.config['GRAPHITE_URL']) + ': ' + str(ex), 'warning')

	## Check Nessus / Tenable for registered agents
	if "TENABLE_IO_ENABLE_DECOM" in wfconfig and wfconfig["TENABLE_IO_ENABLE_DECOM"]:
		try:
			if all(k in helper.lib.config and helper.lib.config[k] for k in ["TENABLE_IO_URL", "TENABLE_IO_ACCESS_KEY", "TENABLE_IO_SECRET_KEY"]):
				r = requests.get(
					urljoin(helper.lib.config["TENABLE_IO_URL"], "/scanners/{scanner_id}/agents".format(scanner_id=1)),
					headers={"Accept": "application/json", "X-ApiKeys": "accessKey={a}; secretKey={s};".format(a=helper.lib.config["TENABLE_IO_ACCESS_KEY"], s=helper.lib.config["TENABLE_IO_SECRET_KEY"])},
					params={"f": "name:match:{name}".format(name=system["name"])},
				)
				if r.status_code == 200:
					js = r.json()
					for agent in js.get("agents", []):
						system_actions.append({"id": "nessus.delete", "desc": "Remove agent from Nessus / Tenable", "detail": "Delete Nessus agent '{name}' (id: {id})".format(name=agent["name"], id=agent["id"]), "data": {"id": agent["id"]}})

				else:
					helper.flash("Warning - Nessus API returned error code {status_code}.".format(status_code=r.status_code), "warning")
			else:
				helper.flash("Warning - Missing configuration key for Nessus", "warning")
		except Exception as ex:
			helper.flash("Warning - An error occured when communicating with {nessus_url}: {ex}".format(nessus_url=helper.lib.config["TENABLE_IO_URL"], ex=ex), "warning")

	# If the config says nothing about creating a ticket, or the config
	# says to create a ticket:
	if 'TICKET_CREATE' not in wfconfig or wfconfig['TICKET_CREATE'] is True:
		# If there are actions to be performed, add on an action to raise a ticket to ESM (but not for Sandbox!)
		if len(system_actions) > 0 and system['class'] != "play":
			system_actions.append({'id': 'ticket.ops', 'desc': 'Raises a ticket with operations to perform manual steps, such as removal from monitoring', 'detail': 'Creates a ticket in ServiceNow and assigns it to ' + wfconfig['TICKET_TEAM'], 'data': {'hostname': system['name']}})

	# Add action to input the decom date.
	system_actions.append({'id': 'system.update_decom_date', 'desc': 'Update the decommission date in Cortex', 'detail': 'Update the decommission date in Cortex and set it to the current date and time.', 'data': {'system_id': system['id']}})

	# A success message
	helper.flash('Successfully completed a pre-decommission check of {system_link}. Found {n_actions} actions for decommissioning'.format(system_link=system_link, n_actions=len(system_actions)), 'success')

	helper.event('system.check.redis', 'Caching system actions in the Redis database')
	if helper.lib.redis_cache_system_actions(helper.task_id, system["id"], system_actions):
		return True
	else:
		helper.end_event(success=False, description='Failed to cache system actions in the Redis database')
		return False

################################################################################

def action_vm_poweroff(action, helper):
	# Get the managed VMware VM object
	vm = helper.lib.vmware_get_vm_by_uuid(action['data']['uuid'], action['data']['vcenter'])

	# Not finding the VM is fatal:
	if not vm:
		raise helper.lib.TaskFatalError(message="Failed to power off VM. Could not locate VM in vCenter")

	# Power off the VM
	task = helper.lib.vmware_vm_poweroff(vm)

	# Wait for the task to complete
	helper.lib.vmware_task_wait(task)

	return True

################################################################################

def action_vm_delete(action, helper):
	# Get the managed VMware VM object
	vm = helper.lib.vmware_get_vm_by_uuid(action['data']['uuid'], action['data']['vcenter'])

	# Not finding the VM is fatal:
	if not vm:
		raise helper.lib.TaskFatalError(message="Failed to delete VM. Could not locate VM in vCenter")

	# Delete the VM
	task = helper.lib.vmware_vm_delete(vm)

	# Wait for the task to complete
	if not helper.lib.vmware_task_wait(task):
		raise helper.lib.TaskFatalError(message="Failed to delete the VM. Check vCenter for more information")
	helper.lib.delete_system_from_cache(action['data']['uuid'])
	return True

################################################################################

def action_cmdb_update(action, helper):
	try:
		# This will raise an Exception if it fails, but it is not fatal
		# to the decommissioning process
		helper.lib.servicenow_mark_ci_deleted(action['data'])
		return True
	except Exception as e:
		helper.end_event(success=False, description=str(e))
		return False

################################################################################

def action_cmdb_relationships_delete(action, helper):
	try:
		# Remove the CI relationships
		(successes, warnings) = helper.lib.servicenow_remove_ci_relationships(action['data'])

		# Special action-end-cases
		if successes == 0 and warnings == 0:
			# This technically shouldn't happen unless somebody deletes them between the "Check System"
			# stage and the task actually running
			helper.end_event(success=True, warning=True, description="Found no CI relationships to remove")
		elif successes == 0 and warnings > 0:
			helper.end_event(success=False, description="Failed to remove any CI relationships")
		elif successes > 0 and warnings > 0:
			helper.end_event(success=True, warning=True, description="Failed to remove some CI relationships: " + str(successes) + " succeeded, " + str(warnings) + " failed")

		return True
	except Exception as e:
		helper.end_event(success=False, description=str(e))
		return False

################################################################################

def action_dns_delete(action, helper):
	try:
		helper.lib.infoblox_delete_host_record_by_ref(action['data'])
		return True
	except Exception as e:
		helper.end_event(success=False, description=str(e))
		return False

################################################################################

def action_puppet_cortex_delete(action, helper):
	try:
		helper.lib.puppet_enc_remove(action['data'])
		return True
	except Exception as e:
		helper.end_event(success=False, description="Failed to remove Puppet node from ENC: " + str(e))
		return False

################################################################################

def action_puppet_master_delete(action, helper):
	# Build the URL
	base_url = helper.config['PUPPET_AUTOSIGN_URL']
	if not base_url.endswith('/'):
		base_url += '/'
	clean_url = base_url + 'cleannode/' + str(action['data'])
	deactivate_url = base_url + 'deactivatenode/' + str(action['data'])

	# Send the request to Cortex Puppet Bridge to clean the node
	try:
		r = requests.get(clean_url, headers={'X-Auth-Token': helper.config['PUPPET_AUTOSIGN_KEY']}, verify=helper.config['PUPPET_AUTOSIGN_VERIFY'])
	except Exception as ex:
		helper.end_event(success=False, description="Failed to remove node from Puppet Master: " + str(ex))
		return False

	# Check return code
	if r.status_code != 200:
		helper.end_event(success=False, description="Failed to remove node from Puppet Master. Cortex Puppet Bridge returned error code " + str(r.status_code))
		return False

	# Send the request to Cortex Puppet Bridge to deactivate the node
	try:
		r = requests.get(deactivate_url, headers={'X-Auth-Token': helper.config['PUPPET_AUTOSIGN_KEY']}, verify=helper.config['PUPPET_AUTOSIGN_VERIFY'])
	except Exception as ex:
		helper.end_event(success=False, description="Failed to deactivate node on Puppet Master: " + str(ex))
		return False

	# Check return code
	if r.status_code != 200:
		helper.end_event(success=False, description="Failed to deactivate node on Puppet Master. Cortex Puppet Bridge returned error code " + str(r.status_code))
		return False

	return True

################################################################################

def action_ad_delete(action, helper):
	try:
		helper.lib.windows_delete_computer_object(action['data']['env'], action['data']['hostname'])
		return True
	except Exception as e:
		helper.end_event(success=False, description="Failed to remove AD object: " + str(e))
		return False

################################################################################

def action_entca_delete(action, helper):
	try:
		r = requests.post('https://' + action['data']['entca_hostname'] + '/delete_entca_certificate', json={'fqdn': action['data']['hostname']}, headers={'Content-Type': 'application/json', 'X-Client-Secret': action['data']['entca_api_token']}, verify=action['data']['entca_verify_ssl'])
	except:
		helper.end_event(success=False, description='Error whilst communicating with ' + action['data']['entca_hostname'])
		return False

	if r.status_code != 200:
		helper.end_event(success=False, description='Failed to remove certificate from ' + action['data']['entca_hostname'])
		return False
	else:
		helper.end_event(success=True, description='Certificate ' + action['data']['hostname'] + ' removed from ' + action['data']['entca_hostname'])
		return True

################################################################################

def action_ticket_ops(action, helper, wfconfig):
	try:
		short_desc = "Finish manual decommissioning steps of " + action['data']['hostname']
		message  = 'Cortex has decommissioned the system ' + action['data']['hostname'] + '.\n\n'
		message += 'Please perform the final, manual steps of the decommissioning process:\n'
		message += ' - Remove the system from monitoring\n'
		message += ' - Remove any associated perimeter firewall rules\n'
		message += ' - Remove any associated load balancer configuration\n'
		message += ' - Update any relevant documentation\n'

		helper.lib.servicenow_create_ticket(short_desc, message, wfconfig['TICKET_OPENER_SYS_ID'], wfconfig['TICKET_TEAM'])
		return True
	except Exception as e:
		helper.end_event(success=False, description="Failed to raise ticket: " + str(e))
		return False

################################################################################

def action_tsm_decom(action, helper):
	try:
		helper.lib.tsm_decom_system(action['data']['NAME'], action['data']['SERVER'])
		return True
	except Exception:
		helper.end_event(success=False, description="Failed to decomission system in TSM")
		return False

################################################################################

def action_rhn5_delete(action, helper):
	try:
		(rhn,key) = helper.lib.rhn5_connect()
		rhn.system.deleteSystem(key, int(action['data']['id']))
		return True
	except Exception:
		helper.end_event(success=False, description="Failed to delete the system object in RHN5")
		return False

def action_satellite6_delete(action, helper):
	try:
		try:
			helper.lib.satellite6_disassociate_host(action['data']['id'])
		except Exception:
			helper.end_event(success=False, description="Failed to disassociate the host object with ID {0} from a VM in Satellite 6".format(action['data']['id']))
			return False

		try:
			helper.lib.satellite6_delete_host(action['data']['id'])
		except Exception:
			helper.end_event(success=False, description="Failed to delete the host object with ID {0} in Satellite 6".format(action['data']['id']))
			return False

		# We disassociated and deleted successfully.
		return True

	except Exception:
		helper.end_event(success=False, description="Failed to delete the host object in Satellite 6")
		return False

################################################################################

def action_sudoldap_update(action, helper, wfconfig):
	try:
		# Connect to LDAP
		l = ldap3.Connection(
			ldap3.Server(wfconfig['SUDO_LDAP_URL']),
			wfconfig['SUDO_LDAP_USER'],
			wfconfig['SUDO_LDAP_PASS'],
			auto_bind=False
		)
		if not l.bind():
			raise helper.lib.TaskFatalError(message="Failed to bind to the sudoldap server.")

		# Replace the value of sudoHost with the calculated list
		l.modify(action['data']['dn'], {
			'sudoHost': [(ldap3.MODIFY_DELETE, action['data']['value'])]
		})

		return True
	except Exception as e:
		helper.end_event(success=False, description="Failed to update the object in sudoldap: " + str(e))
		return False

################################################################################

def action_sudoldap_delete(action, helper, wfconfig):
	try:
		# Connect to LDAP
		l = ldap3.Connection(
			ldap3.Server(wfconfig['SUDO_LDAP_URL']),
			wfconfig['SUDO_LDAP_USER'],
			wfconfig['SUDO_LDAP_PASS'],
			auto_bind=False
		)
		if not l.bind():
			raise helper.lib.TaskFatalError(message="Failed to bind to the sudoldap server.")

		# Delete the entry
		l.delete(action['data']['dn'])

		return True
	except Exception:
		helper.end_event(success=False, description="Failed to delete the object in sudoldap")
		return False

################################################################################

def action_graphite_delete(action, helper, wfconfig):
	try:
		# Make the REST call to delete the metrics
		url = urljoin(helper.config['GRAPHITE_URL'], '/host/' + action['data']['host'])
		r = requests.delete(url, auth=(helper.config['GRAPHITE_USER'], helper.config['GRAPHITE_PASS']))

		if r.status_code != 200:
			helper.end_event(success=False, description="Failed to remove metrics from Graphite. CarbonHTTPInterface returned error code " + str(r.status_code))
			return False

		return True
	except Exception as e:
		helper.end_event(success=False, description="Failed to remove the metrics from Graphite: " + str(e))
		return False

################################################################################

def action_nessus_delete(action, helper, wfconfig):
	try:
		if not all(k in helper.lib.config and helper.lib.config[k] for k in ["TENABLE_IO_URL", "TENABLE_IO_ACCESS_KEY", "TENABLE_IO_SECRET_KEY"]):
			raise Exception("Missing configuration key for Nessus")

		r = requests.delete(
			urljoin(helper.lib.config["TENABLE_IO_URL"], "/scanners/{scanner_id}/agents/{agent_id}".format(scanner_id=1, agent_id=action["data"]["id"])),
			headers={"Accept": "application/json", "X-ApiKeys": "accessKey={a}; secretKey={s};".format(a=helper.lib.config["TENABLE_IO_ACCESS_KEY"], s=helper.lib.config["TENABLE_IO_SECRET_KEY"])},
		)
		if r.status_code != 200:
			helper.end_event(success=False, description="Failed to delete Nessus agent, Nessus API returned error code: {status_code}.".format(status_code=r.status_code))
			return False

	except Exception as ex:
		helper.end_event(success=False, description="Failed to remove the Nessus agent: {ex}".format(ex))
		return False

	return True

################################################################################

def action_update_decom_date(action, helper):
	try:
		helper.lib.update_decom_date(action["data"]["system_id"])
		return True
	except Exception:
		helper.end_event(success=False, description="Failed to update the decommission date in Cortex")
		return False
