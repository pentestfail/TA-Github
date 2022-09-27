
# encoding = utf-8

import os
import sys
import time
import datetime
import base64
try:
    from urllib import parse as urlparse
except ImportError:
    from urllib2 import urlparse
import json


def validate_input(helper, definition):
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
    git_enterprise = bool(helper.get_arg('github_creds')['enterprise'])
    inputname = helper.get_input_stanza_names()
    inputtype = helper.get_input_type()
    inputsource = inputtype + ":" + inputname
    helper.log_info("input_type={0:s} input={1:s} message='Collecting events.'".format(inputtype,inputname))

    # Create checkpoint key
    opt_checkpoint = "{0:s}-{1:s}".format(inputtype,inputname)

    # Create API request parameters    
    auth = base64.b64encode(git_username + ":" + git_password).decode("ascii")
    header =  {'Authorization': 'Basic {}'.format(auth)}
    parameter = {}
    method = 'GET'

    # Determine API schema to use
    if git_instance=="api.github.com":
        url = "https://{0}/repos/{1}/{2}/stats/contributors".format(git_instance,git_owner,git_repo)
        helper.log_debug("input_type={0:s} input={1:s} message='Github.com identified as instance. Using api subdomain.' url='{2:s}'".format(inputtype,inputname,url))
        header['Accept'] = 'application/vnd.github.v3+json'
    elif git_enterprise is True:
        url = "https://{0}/api/v3/repos/{1}/{2}/stats/contributors".format(git_instance,git_owner,git_repo)
        helper.log_debug("input_type={0:s} input={1:s} message='Github Enterprise specified in input configuration. Using /api/v3/repos/ path instead of subdomain.' url='{2:s}'".format(inputtype,inputname,url))
    else:
        url = "https://{0}/repos/{1}/{2}/stats/contributors".format(git_instance,git_owner,git_repo)
        header['Accept'] = 'application/vnd.github.v3+json'
        helper.log_error("input_type={0:s} input={1:s} message='Github instance not configured as enterprise & doesn't match public API domain! WTF!? Defaulting to public API path (/repos/).' url='{2:s}'".format(inputtype,inputname,url))
    
    try:
        # Leverage helper function to send http request
        helper.log_debug("input_type={0:s} input={1:s} message='Requesting repository stats from Github API.' url='{2:s}' parameters={3:s}".format(inputtype,inputname,url,parameter))
        response = helper.send_http_request(url, method, parameters=parameter, payload=None, headers=header, cookies=None, verify=True, cert=None, timeout=25, use_proxy=True)

        # Return API response code
        r_status = response.status_code
        r_reason = response.reason
        # Return API request status_code
        if r_status is 202:
            helper.log_info("input_type={0:s} input={1:s} message='API still processing request. Will retry in 10 seconds.' status_code={2:d} reason='{3:s}'".format(inputtype,inputname,r_status,r_reason))
            time.sleep(15) # Wait 15 seconds and retry
            response = helper.send_http_request(url, method, parameters=parameter, payload=None, headers=header, cookies=None, verify=True, cert=None, timeout=25, use_proxy=True)
            # Return API response code
            r_status = response.status_code # Update response status_code
            r_reason = response.reason # Update response reason
            pass # Continue processing response
        elif r_status is not 200:
            helper.log_error("input_type={0:s} input={1:s} message='API request unsuccessful.' status_code={2:d} reason='{3:s}'".format(inputtype,inputname,r_status,r_reason))
            response.raise_for_status()
        # Return API request as JSON
        obj = response.json()

        if obj is None:
            helper.log_info("input_type={0:s} input={1:s} message='No events retrieved from Github API.'".format(inputtype,inputname))
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
        helper.log_info("input_type={0:s} input={1:s} message='Collection complete.' indexed={2:d}".format(inputtype,inputname,i))
        helper.log_debug("input_type={0:s} input={1:s} message='Storing checkpoint.' updated={2:s}".format(inputtype,inputname,updated))

    except Exception as error:
        helper.log_error("input_type={0:s} input={1:s} status_code={2:d} reason='{3:s}' error='{4:s}'".format(inputtype,inputname,r_status,r_reason,error))
        raise error