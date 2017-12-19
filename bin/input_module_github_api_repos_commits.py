
# encoding = utf-8

import os
import sys
import time
import base64
import urlparse
import json
from datetime import datetime, timedelta

def validate_input(helper, definition):
    #github_instance = definition.parameters.get('github_instance', None)
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
    git_username = helper.get_arg('github_creds')['username']
    git_password = helper.get_arg('github_creds')['password']
    git_pagesize = helper.get_arg('pagesize') or 50 #Page size of results
    git_daysago = helper.get_arg('days_ago') or 356 #Max days ago since commit
    inputname = helper.get_input_stanza_names()
    inputsource = helper.get_input_type() + ":" + inputname
    helper.log_info("input_type=github_api_repos_commits input={0:s} message='Collecting events.'".format(inputname))

    # Create initial time to query for commits in last 365days
    initial_status = (datetime.now() - timedelta(git_daysago)).strftime("%Y-%m-%d")
    #initial_status = "2017-01-01"

    # Create checkpoint key
    opt_checkpoint = "github_api_repos_commits-{0:s}".format(inputname)
    #helper.delete_check_point(opt_checkpoint)
    
    #Check for last query execution data in kvstore & generate if not present
    try:
        last_status = helper.get_check_point(opt_checkpoint) or initial_status
        helper.log_debug("input_type=github_api_repos_commits input={0:s} message='Last successful checkpoint time.' last_status={1:s}".format(inputname,json.dumps(last_status)))
    except Exception as e:
        helper.log_error("input_type=github_api_repos_commits input={0:s} message='Unable to retrieve last execution checkpoint!'".format(inputname))
        raise e
    
    # Create API request parameters    
    auth = base64.b64encode(git_username + ":" + git_password).decode("ascii")
    header =  {'Authorization': 'Basic {}'.format(auth)}
    parameter = {}
    parameter['since'] = last_status
    parameter['per_page'] = git_pagesize
    url = "https://{0}/repos/{1}/{2}/commits".format(git_instance,git_owner,git_repo)
    method = 'GET'
    
    try:
        has_results = True
        #total = 0
        i=0
        while has_results:
            # Leverage helper function to send http request
            response = helper.send_http_request(url, method, parameters=parameter, payload=None, headers=header, cookies=None, verify=True,     cert=None, timeout=25, use_proxy=True)
            helper.log_debug("input_type=github_api_repos_commits input={0:s} message='Requesting commit data from Github API.' url='{1:s}' parameters='{2:s}'".format(inputname,url,json.dumps(parameter)))

            # Return API response code
            r_status = response.status_code
            # Return API request status_code
            if r_status is 202:
                helper.log_info("input_type=github_api_repos_commits input={0:s} message='API still processing request. Will retry in 10 seconds.' status_code={1:d}".format(inputname,r_status))
                time.sleep(10)
            elif r_status is not 200:
                helper.log_error("input_type=github_api_repos_commits input={0:s} message='API request unsuccessful.' status_code={1:d}".format    (inputname,r_status))
                response.raise_for_status()
            # Return API request as JSON
            obj = response.json()

            if obj is None:
                helper.log_info("input_type=github_api_repos_commits input={0:s} message='No records retrieved from Github API.'".format    (inputname))
                has_results = False

            #page_count = len(obj) #Count of items in the results from page.
            #total += len(obj) #Add count of items in results to total.
            #helper.log_debug("input_type=github_api_repos_commits input={0:s} page_count={1:d}".format(inputname,page_count))
            
            try:
                url = response.links['next']['url']
                parameter = None
                has_results = True
            except:
                has_results = False
            
            for record in obj:
                event = record['commit']
                event['repository'] = git_repo
                event['owner'] = git_owner
                event['sha'] = record['sha']
                del event['tree']
                # Write event to index
                ew.write_event(helper.new_event(source=inputsource, index=helper.get_output_index(), sourcetype=helper.get_sourcetype(), data=json.dumps(event)))
                i+=1
                #helper.log_debug("input_type=github_api_repos_commits input={0:s} processed={1:d} total={2:d}".format(inputname,i,total))
            
            helper.log_debug("input_type=github_api_repos_commits input={0:s} processed={1:d}".format(inputname,i))

            if has_results:
                helper.log_debug("input_type=github_api_repos_commits input={0:s} message='Getting next page.' link_next='{1:s}'".format(inputname,url))
                response = helper.send_http_request(url, method, parameters=None, payload=None, headers=header, cookies=None, verify=True, cert=None, timeout=25, use_proxy=True)
            else:
                helper.log_debug("input_type=github_api_repos_commits input={0:s} message='No additional pages.'".format(inputname))
            
        #Update last completed execution time
        updated = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) #Add meta value for troubleshooting
        helper.save_check_point(opt_checkpoint,updated)
        helper.log_info("input_type=github_api_repos_commits input={0:s} message='Collection complete.' indexed={1:d}".format(inputname,i))
        helper.log_debug("input_type=github_api_repos_commits input={0:s} message='Storing checkpoint.' updated={1:s}".format(inputname,updated))

    except Exception as error:
        helper.log_error("input_type=github_api_repos_commits input={0:s} message='An unknown error occurred!'".format(inputname))
        raise error
