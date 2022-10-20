
# encoding = utf-8

import os
import sys
import time
import base64
try:
    from urllib import parse as urlparse
except ImportError:
    from urllib2 import urlparse
import json
from datetime import datetime, timedelta

def validate_input(helper, definition):
    github_owner = definition.parameters.get('github_owner', None)
    github_repo = definition.parameters.get('github_repo', None)
    github_stat = definition.parameters.get('github_stat', None)
    github_creds = definition.parameters.get('github_creds', None)
    github_pagesize = definition.parameters.get('pagesize', None)
    github_since = definition.parameters.get('days_ago', None)
    pass

def collect_events(helper, ew):
    # Retrieve runtime variables
    git_instance = helper.get_arg('github_creds')['github_instance']
    git_owner = helper.get_arg('github_owner')
    git_repo = helper.get_arg('github_repo')
    git_username = helper.get_arg('github_creds').get('username', "")
    git_password = helper.get_arg('github_creds')['password']
    git_enterprise = bool(helper.get_arg('github_creds').get('enterprise', 0))
    git_pagesize = helper.get_arg('pagesize') or 50 #Page size of results
    git_daysago = helper.get_arg('days_ago') or 356 #Max days ago since created
    opt_proxy = bool(helper.get_proxy())
    inputname = helper.get_input_stanza_names()
    inputtype = helper.get_input_type()
    inputsource = inputtype + ":" + inputname
    helper.log_info("input_type={0:s} input={1:s} message='Collecting events.'".format(inputtype,inputname))

    # Create checkpoint key
    opt_checkpoint = "{0:s}-{1:s}".format(inputtype,inputname)  

    # Create initial time to query for issues in last 365days
    initial_status = (datetime.now() - timedelta(git_daysago)).strftime("%Y-%m-%d")
    
    #Check for last query execution data in kvstore & generate if not present
    try:
        last_status = helper.get_check_point(opt_checkpoint) or initial_status
        helper.log_debug("input_type={0:s} input={1:s} message='Last successful checkpoint time.' last_status={2:s}".format(inputtype,inputname,json.dumps(last_status)))
    except Exception as e:
        helper.log_error("input_type={0:s} input={1:s} message='Unable to retrieve last execution checkpoint!'".format(inputtype,inputname))
        raise e
    
    # Create API request parameters    
    connect_string = "{}:{}".format(git_username, git_password)
    auth = base64.b64encode(connect_string.encode("ascii")).decode("ascii")
    header =  {'Authorization': 'Basic {}'.format(auth)}
    if git_username == "":
        header = {'Authorization': 'Bearer {}'.format(git_password)}
    parameter = {
        'since': last_status,
        'per_page': git_pagesize
    }
    method = 'GET'

    # Determine API schema to use
    if git_instance=="api.github.com":
        url = "https://{0}/repos/{1}/{2}/issues".format(git_instance,git_owner,git_repo)
        helper.log_debug("input_type={0:s} input={1:s} message='Github.com identified as instance. Using api subdomain.' url='{2:s}'".format(inputtype,inputname,url))
        header['Accept'] = 'application/vnd.github.v3+json'
    elif git_enterprise is True:
        url = "https://{0}/api/v3/repos/{1}/{2}/issues".format(git_instance,git_owner,git_repo)
        helper.log_debug("input_type={0:s} input={1:s} message='Github Enterprise specified in input configuration. Using /api/v3/repos/ path instead of subdomain.' url='{2:s}'".format(inputtype,inputname,url))
    else:
        url = "https://{0}/repos/{1}/{2}/issues".format(git_instance,git_owner,git_repo)
        header['Accept'] = 'application/vnd.github.v3+json'
        helper.log_error("input_type={0:s} input={1:s} message='Github instance not configured as enterprise & doesn't match public API domain! WTF!? Defaulting to public API path (/repos/).' url='{2:s}'".format(inputtype,inputname,url))

    try:
        has_results = True
        #total = 0
        i=0
        while has_results:
            # Leverage helper function to send http request
            helper.log_debug("input_type={0:s} input={1:s} message='Requesting issue data from Github API.' url='{2:s}' parameters='{3:s}'".format(inputtype,inputname,url,json.dumps(parameter)))
            response = helper.send_http_request(url, method, parameters=parameter, payload=None, headers=header, cookies=None, verify=True, cert=None, timeout=25, use_proxy=opt_proxy)
            
            # Return API response code
            r_status = response.status_code
            r_reason = response.reason
            # Return API request status_code
            if r_status is not 200:
                helper.log_error("input_type={0:s} input={1:s} message='API request unsuccessful.' status_code={2:d} reason='{3:s}'".format(inputtype,inputname,r_status,r_reason))
                response.raise_for_status()
            # Return API request as JSON
            obj = response.json()

            if obj is None:
                helper.log_info("input_type={0:s} input={1:s} message='No records retrieved from Github API.'".format(inputtype,inputname))
                has_results = False

            #page_count = len(obj) #Count of items in the results from page.
            #total += len(obj) #Add count of items in results to total.
            #helper.log_debug("input_type=github_api_repos_issues input={0:s} page_count={1:d}".format(inputname,page_count))
            
            try:
                url = response.links['next']['url']
                parameter = None
                has_results = True
            except:
                has_results = False
            
            for record in obj:
                record['repository'] = git_repo
                record['owner'] = git_owner

                try:
                    # Extract fields we care about
                    record['user_login'] = record.get('user').get('login')
                    record['user_id'] = record.get('user').get('id')
                    record['user_dn'] = record.get('user').get('ldap_dn')
                    record['assignee_login'] = record.get('assignee').get('login')
                    record['assignee_id'] = record.get('assignee').get('id')
                    record['assignee_dn'] = record.get('assignee').get('ldap_dn')
                    # Remove fields we don't care about
                    del record['milestone']['creator']
                    del record['assignees']
                    del record['assignee']
                    del record['user']
                    # Reduce complexity of fields we care about
                    record['labels'] = list(label['name'] for label in record['labels'])
                    record['pull_request'] = record.get('pull_request').get('html_url')
                except:
                    pass
                
                # Write event to index
                ew.write_event(helper.new_event(source=inputsource, index=helper.get_output_index(), sourcetype=helper.get_sourcetype(), data=json.dumps(record)))
                i+=1
                #helper.log_debug("input_type=github_api_repos_issues input={0:s} processed={1:d} total={2:d}".format(inputname,i,total))
            
            helper.log_debug("input_type={0:s} input={1:s} processed={2:d}".format(inputtype,inputname,i))

            if has_results:
                helper.log_debug("input_type={0:s} input={1:s} message='Getting next page.' link_next='{2:s}'".format(inputtype,inputname,url))
                response = helper.send_http_request(url, method, parameters=None, payload=None, headers=header, cookies=None, verify=True, cert=None, timeout=25, use_proxy=opt_proxy)
            else:
                helper.log_debug("input_type={0:s} input={1:s} message='No additional pages.'".format(inputtype,inputname))
            
        #Update last completed execution time
        updated = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) #Add meta value for troubleshooting
        helper.save_check_point(opt_checkpoint,updated)
        helper.log_info("input_type={0:s} input={1:s} message='Collection complete.' indexed={2:d}".format(inputtype,inputname,i))
        helper.log_debug("input_type={0:s} input={1:s} message='Storing checkpoint.' updated={2:s}".format(inputtype,inputname,updated))

    except Exception as error:
        helper.log_error("input_type={0:s} input={1:s} status_code={2:d} reason='{3:s}'' message='{4:s}'".format(inputtype,inputname,r_status,r_reason,error))
        raise error