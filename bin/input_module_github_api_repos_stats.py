
# encoding = utf-8

import os
import sys
import time
import datetime
import base64
import urlparse
import json


def validate_input(helper, definition):
    #github_instance = definition.parameters.get('github_instance', None)
    github_owner = definition.parameters.get('github_owner', None)
    github_repo = definition.parameters.get('github_repo', None)
    github_stat = definition.parameters.get('github_stat', None)
    github_creds = definition.parameters.get('github_creds', None)
    pass

def collect_events(helper, ew):
    # Retrieve runtime variables
    git_instance = helper.get_arg('github_creds')['github_instance']
    git_owner = helper.get_arg('github_owner')
    git_repo = helper.get_arg('github_repo')
    git_username = helper.get_arg('github_creds')['username']
    git_password = helper.get_arg('github_creds')['password']
    inputname = helper.get_input_stanza_names()
    inputsource = helper.get_input_type() + ":" + inputname
    helper.log_info("input_type=github_api_repo_stats input={0:s} message='Collecting events.'".format(inputname))

    # Create checkpoint key
    opt_checkpoint = "github_api_repo_stats-{0:s}".format(inputname)
    
    # Create API request parameters    
    auth = base64.b64encode(git_username + ":" + git_password).decode("ascii")
    header =  {'Authorization': 'Basic {}'.format(auth)}
    parameter = {}
    url = "https://{0}/repos/{1}/{2}/stats/contributors".format(git_instance,git_owner,git_repo)
    method = 'GET'
    
    try:
        # Leverage helper function to send http request
        response = helper.send_http_request(url, method, parameters=parameter, payload=None, headers=header, cookies=None, verify=True, cert=None, timeout=25, use_proxy=True)
        helper.log_debug("input_type=github_api_repo_stats input={0:s} message='Requesting issue data from Github API.' url={1:s} parameters={2:s}".format(inputname,url,parameter))

        # Return API response code
        r_status = response.status_code
        # Return API request status_code
        if r_status is not 200:
            helper.log_error("input_type=github_api_repo_stats input={0:s} message='API request unsuccessful.' status_code={1:d}".format(inputname,r_status))
            response.raise_for_status()
        # Return API request as JSON
        obj = response.json()

        if obj is None:
            helper.log_info("input_type=github_api_repo_stats input={0:s} message='No events retrieved from Github API.'".format(inputname))
            exit()
        
        i=0
        for record in obj:
            for week in record['weeks']:
                event = {}
                event['repository'] = git_repo
                event['owner'] = git_owner
                event['author'] = record.get('author').get('login')
                event['author_dn'] = record.get('author').get('ldap_dn')
                event['author_id'] = record.get('author').get('id')
                event['author_type'] = record.get('author').get('type')
                event['total'] = record.get('author').get('total')
                event['time'] = week['w']
                event['additions'] = week['a']
                event['deletions'] = week['d']
                event['commits'] = week['c']
                
                event = helper.new_event(source=inputsource, index=helper.get_output_index(), sourcetype=helper.get_sourcetype(), data=json.dumps(event))
                ew.write_event(event)
                i+=1
            
        #Update last completed execution time
        updated = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) #Add meta value for troubleshooting
        helper.save_check_point(opt_checkpoint,updated)
        helper.log_info("input_type=github_api_repo_stats input={0:s} message='Collection complete.' indexed={1:d}".format(inputname,i))
        helper.log_debug("input_type=github_api_repo_stats input={0:s} message='Storing checkpoint.' updated={1:s}".format(inputname,updated))

    except Exception as error:
        helper.log_error("input_type=github_api_repo_stats input={0:s} message='An unknown error occurred!'".format(inputname))
        raise error
