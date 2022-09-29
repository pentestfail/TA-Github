
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
    #github_instance = definition.parameters.get('github_instance', None)
    github_owner = definition.parameters.get('github_owner', None)
    github_repo = definition.parameters.get('github_repo', None)
    github_stat = definition.parameters.get('github_stat', None)
    github_creds = definition.parameters.get('github_creds', None)
    github_pagesize = definition.parameters.get('pagesize', None)
    github_since = definition.parameters.get('days_ago', None)
    pass

def fetch_repos(helper, url, header):
    repo_names = []
    repo_dt_lastpush = ""
    header['Accept'] = 'application/vnd.github.v3+json'
    params = {
        'per_page': 100,
        'page': 1
    }

    while True:
        response = helper.send_http_request(url, "GET", parameters=params, headers=header, verify=True, timeout=25, use_proxy=bool(helper.get_proxy()))
        response.raise_for_status()

        repositories = response.json()
        total_repos = len(repositories)
        for repo in repositories:
            repo_names.append(repo['name'])

            last_pushed = repo['pushed_at']
            # Checking last push date
            if not repo_dt_lastpush:
                repo_dt_lastpush = last_pushed
                continue

            # if pushed dt is older than saved one -> overwrite
            if datetime.strptime(repo_dt_lastpush, "%Y-%m-%dT%H:%M:%SZ") > datetime.strptime(last_pushed, "%Y-%m-%dT%H:%M:%SZ"):
                repo_dt_lastpush = last_pushed

        if total_repos < 1 or total_repos < params['per_page']:
            # Fetched all repositories
            break

        # Fetch next page
        params['page'] += 1

    # Move 1 day back to prevent losing commits
    repo_dt_lastpush = (datetime.strptime(repo_dt_lastpush, "%Y-%m-%dT%H:%M:%SZ") - timedelta(1)).strftime("%Y-%m-%d")

    helper.log_debug("Fetched [{0}] repositories - {1}".format(len(repo_names), repo_names))
    helper.log_debug("Start datetime [{0}]".format(repo_dt_lastpush))
    return repo_names, repo_dt_lastpush

def collect_events(helper, ew):
    # Retrieve runtime variables
    git_instance = helper.get_arg('github_creds')['github_instance']
    git_owner = helper.get_arg('github_owner')
    git_repo = helper.get_arg('github_repo')
    git_username = helper.get_arg('github_creds').get('username', "")
    git_password = helper.get_arg('github_creds')['password']
    git_enterprise = bool(helper.get_arg('github_creds').get('enterprise', 0))
    git_pagesize = helper.get_arg('pagesize') or 50 #Page size of results
    git_daysago = helper.get_arg('days_ago') or 365 #Max days ago since commit
    git_ignorehistory = bool(helper.get_arg('ignore_history'))
    opt_proxy = bool(helper.get_proxy())
    inputname = helper.get_input_stanza_names()
    inputtype = helper.get_input_type()
    inputsource = inputtype + ":" + inputname
    helper.log_info("input_type={0:s} input={1:s} message='Collecting events.'".format(inputtype,inputname))

    # Create initial time to query for commits
    initial_status = (datetime.now() - timedelta(git_daysago)).strftime("%Y-%m-%d")
    
    # Create API request parameters
    connect_string = "{0}:{1}".format(git_username, git_password)
    auth = base64.b64encode(connect_string.encode("ascii")).decode("ascii")
    header =  {'Authorization': 'Basic {}'.format(auth)}
    if git_username == "":
        header['Authorization'] = 'Bearer {}'.format(git_password)
    method = 'GET'

    if git_repo == "*":
        try:
            # Fetch all repos and the start date (oldest over all)
            git_repositories, initial_status = fetch_repos(helper, "https://{0}/orgs/{1}/repos".format(git_instance, git_owner), header)
        except Exception as e:
            helper.log_error("Exception occurred while fetching all repositories - {}".format(e))
            raise e
    else:
        git_repositories = git_repo.split(',')
    
    for git_repo in git_repositories:
        # Determine API schema to use
        if git_instance=="api.github.com":
            url = "https://{0}/repos/{1}/{2}/commits".format(git_instance,git_owner,git_repo)
            helper.log_debug("input_type={0:s} input={1:s} message='Github.com identified as instance. Using api subdomain.' url='{2:s}'".format(inputtype,inputname,url))
            header['Accept'] = 'application/vnd.github.v3+json'
        elif git_enterprise is True:
            url = "https://{0}/api/v3/repos/{1}/{2}/commits".format(git_instance,git_owner,git_repo)
            helper.log_debug("input_type={0:s} input={1:s} message='Github Enterprise specified in input configuration. Using /api/v3/repos/ path instead of subdomain.' url='{2:s}'".format(inputtype,inputname,url))
        else:
            url = "https://{0}/repos/{1}/{2}/commits".format(git_instance,git_owner,git_repo)
            header['Accept'] = 'application/vnd.github.v3+json'
            helper.log_error("input_type={0:s} input={1:s} message='Github instance not configured as enterprise & doesn't match public API domain! WTF!? Defaulting to public API path (/repos/).' url='{2:s}'".format(inputtype,inputname,url))

        # Create checkpoint key
        opt_checkpoint = "{0:s}-{1:s}-{2:s}".format(inputtype,inputname,git_repo)

        # Check for last query execution data in kvstore & generate if not present
        try:
            last_status = helper.get_check_point(opt_checkpoint) or initial_status
            helper.log_debug("input_type={0:s} input={1:s} repo={2:s} message='Last successful checkpoint time.' last_status={3:s}".format(inputtype,inputname,git_repo,json.dumps(last_status)))
        except Exception as e:
            helper.log_error("input_type={0:s} input={1:s} repo={2:s} message='Unable to retrieve last execution checkpoint!'".format(inputtype,inputname,git_repo))
            raise e

        parameter = {
            'since': last_status,
            'per_page': 1 if git_ignorehistory else git_pagesize
        }

        try:
            has_results = True
            #total = 0
            i=0
            while has_results:
                # Leverage helper function to send http request
                response = helper.send_http_request(url, method, parameters=parameter, payload=None, headers=header, cookies=None, verify=True, cert=None, timeout=25, use_proxy=opt_proxy)
                helper.log_debug("input_type={0:s} input={1:s} message='Requesting commit data from Github API.' url='{2:s}' parameters='{3:s}'".format(inputtype,inputname,url,json.dumps(parameter)))

                # Return API response code
                r_status = response.status_code
                # Return API request status_code
                if r_status is 202:
                    helper.log_info("input_type={0:s} input={1:s} message='API still processing request. Will retry in 10 seconds.' status_code={2:d}".format(inputtype,inputname,r_status))
                    time.sleep(10)
                elif r_status is not 200:
                    helper.log_error("input_type={0:s} input={1:s} message='API request unsuccessful.' status_code={2:d}".format(inputtype,inputname,r_status))
                    response.raise_for_status()
                # Return API request as JSON
                obj = response.json()

                if obj is None:
                    helper.log_info("input_type={0:s} input={1:s} message='No records retrieved from Github API.'".format(inputtype,inputname))
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

                if git_ignorehistory:
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
            helper.log_error("input_type={0:s} input={1:s} message='An unknown error occurred!'".format(inputtype,inputname))
            raise error