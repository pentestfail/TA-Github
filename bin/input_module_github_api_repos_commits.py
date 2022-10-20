
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

class GithubRateLimitException(Exception):
    def __init__(self, reset_time):
        # Calculate seconds to wait from certain time diff
        retry_after = reset_time - float(datetime.strftime(datetime.now(), "%s"))
        self.retry_after = retry_after

def parse_response(helper, res):
    response = res.json()

    if res.status_code == 403:
        if res.headers['X-RateLimit-Remaining'] == '0':
            raise GithubRateLimitException(float(res.headers["X-RateLimit-Reset"]))
        else:
            raise Exception("Check your Token - {0}".format(response['message']))
    elif res.status_code == 404:
        raise Exception("Check your Endpoint / URL - {0}".format(response['message']))
    elif res.status_code == 409 and response['message'] == "Git Repository is empty.":
        return {}
    elif res.status_code != 200:
        helper.log_debug("Github responded with [{0}] - {1}".format(
            res.status_code,
            res.text
        ))
        raise Exception("Request to Github unsuccessful. {0} - Error message {1}".format(res.status_code, response['message']))

    return response

def fetch_repos(helper, url, header):
    repo_names = []
    repo_dt_lastpush = ""
    params = {
        'type': helper.get_arg('github_repotype'),
        'per_page': 100,
        'page': 1
    }

    while True:
        try:
            response = helper.send_http_request(url, "GET", parameters=params, headers=header, verify=True, timeout=25, use_proxy=bool(helper.get_proxy()))
            repositories = parse_response(helper, response)

        except GithubRateLimitException as e:
            helper.log_info("GitHub Rate Limit hit: waiting for {0} seconds before trying again the call to {1}".format(e.retry_after, url))
            time.sleep(e.retry_after)
            response = helper.send_http_request(url, "GET", parameters=params, headers=header, verify=True, timeout=25, use_proxy=bool(helper.get_proxy()))
            repositories = parse_response(helper, response)

        total_repos = len(repositories)
        for repo in repositories:
            repo_names.append(repo['full_name'])

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
    header = {
        'Authorization': 'Basic {0}'.format(auth),
        'Accept': 'application/vnd.github+json'
    }
    if git_username == "":
        header['Authorization'] = 'Bearer {0}'.format(git_password)
    method = 'GET'

    # Determine API schema to use
    if git_enterprise is True:
        base_url = "https://{0}/api/v3".format(git_instance)
        helper.log_debug("input_type={0:s} input={1:s} message='Github Enterprise specified in input configuration. Using /api/v3/ path instead of subdomain.' base_url='{2:s}'".format(inputtype, inputname, base_url))
    else:
        if git_instance != "api.github.com":
            helper.log_error("input_type={0:s} input={1:s} message='Github instance not configured as enterprise & doesn't match public API domain! WTF!? Using default API resource.'".format(inputtype, inputname))
            git_instance = "api.github.com"

        base_url = "https://{0}".format(git_instance)
        helper.log_debug("input_type={0:s} input={1:s} message='Github.com identified as instance.' base_url='{2:s}'".format(inputtype, inputname, base_url))

    if git_repo == "*":
        try:
            url = "{0}/orgs/{1}/repos".format(base_url, git_owner)
            # Fetch all repos and the start date (oldest over all)
            git_repositories, initial_status = fetch_repos(helper, url, header)
        except Exception as e:
            helper.log_error("Exception occurred while fetching all repositories - {0}".format(e))
            raise e
    else:
        git_repositories = git_repo.split(',')
    
    for git_repo in git_repositories:
        git_repo_fullname = ""

        if '/' in git_repo:
            # This is a GitHub repository fullname
            git_repo_fullname = git_repo
            git_repo = git_repo.split('/')[1]

        # Setting URL for fetching commits
        url = "{0}/repos/{1}/{2}/commits".format(base_url, git_owner, git_repo)

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
                try:
                    # Leverage helper function to send http request
                    response = helper.send_http_request(url, method, parameters=parameter, payload=None, headers=header, cookies=None, verify=True, cert=None, timeout=25, use_proxy=opt_proxy)
                    helper.log_debug("input_type={0:s} input={1:s} message='Requesting commit data from Github API.' url='{2:s}' parameters='{3:s}'".format(inputtype,inputname,url,json.dumps(parameter)))
                    obj = parse_response(helper, response)
                except GithubRateLimitException as e:
                    helper.log_info("GitHub Rate Limit hit: waiting for {0} seconds before trying again the call to {1}".format(e.retry_after, url))
                    time.sleep(e.retry_after)
                    response = helper.send_http_request(url, method, parameters=parameter, payload=None, headers=header, cookies=None, verify=True, cert=None, timeout=25, use_proxy=opt_proxy)
                    obj = parse_response(helper, response)

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
                    if git_repo_fullname:
                        event['repository_fullname'] = git_repo_fullname
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