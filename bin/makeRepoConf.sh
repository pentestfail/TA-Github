#!/bin/bash
# What:     Reads git to create the config file for TA-github
# How:      Runs curl against the git REST api to traverse the Organizations, and for each org,
#           retrieve its repos.
# Who:      adrianblakeyATgmailDOTCOM
# When:     Needs to run daily on a "cron."
# Prereqs.: jq and curl - both need to be in the PATH
# ToDo:     Use a better separator than ":"
# How:      Put the git credentials, git hostname and the TA-Github Account Name in a file called .ta-git in the root of the app.
#           E.g. mygitid:mygitpwd:myhost.foo.com:GitSuperUser
#
#set -x
ME=${0}

# TY Stackoverflow
function whereami() {
    echo "$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null && pwd )"
}

# Stupid logger call it as:
# log ERROR|DEBUG|INFO msg
function log() {
    ts=`date "+%Y%m%d-%H%M%S"`
    echo "${ts} - ${1}: ${ME} - ${2}"
}

ts=`date "+%Y%m%d-%H%M%S"`
log "INFO" "Starting config file creation"

j=$(command -v jq)
if [ -z "$j" ] ; then
    log "ERROR" "jq is not in the path or not installed on the system"
    log "ERROR" "Run: wget https://github.com/stedolan/jq/releases/download/jq-1.6/jq-linux64"
    exit 666
fi
c=$(command -v curl)
if [ -z "$c" ] ; then
    log "ERROR" "curl is not in the path or not installed on the system"
    exit 666
fi

# Important places
MEDIR=$(whereami)             # This should be $SPLUNK_HOME/etc/apps/TA-Github/bin

APP="${MEDIR}/.."              # TA-Github
CRED=${APP}/.ta-git
CONF_DIR="local"
BACKUP="${APP}/${CONF_DIR}/.backups"     # Secret place to keep backups
CONFIG="${APP}/${CONF_DIR}/inputs.conf"
FN="/tmp/__inputs.new"

# Get and parse the git creds. from a hidden file
function cred() {
    if [ ! -f "${CRED}" ] ; then
	log "ERROR" "The credential file ${CRED} is missing."
	exit 66
    else
	while IFS=':' read -r uid pat fqdn acctName ; do
	    break
	done < "${CRED}"
    fi
}
cred
# For Windows testing
if [ ! -d "/tmp" ] ; then
    mkdir -f /tmp
fi
# Place to keep some backups of the config - just in case
if [ ! -d "${BACKUPS}" ] ; then
    mkdir -p ${BACKUP}
fi
# Number of repos.
count=$(curl -s -L -k -u ${uid}:${pat} https://${fqdn}/api/v3/organizations | jq -r '. | length')
repoCount=0
if [ $count -gt 0 ] ; then
    rm -rf $FN
    # Create a login/url array of all Organizations
    # Get the list of organizations in the repo - filter name (login) and URL to get repos for the org
    urls=$(curl -s -L -k -u $uid}:${pat} https://${fqdn}/api/v3/organizations | jq -r '[.[] | { l: .login, u: .url }]')
    i=0
    # Iterate through all the Organizations that have been extracted as name/url
    while [ $i -lt $count ] ; do
	org=$(echo $urls | jq -r ".[$i] | .l")
	# Run the URL that returns all the org's repos
	url=$(echo $urls | jq -r ".[$i] | .u")
	# Return the URL for this org that returns the list of repos
	repoUrls=$(curl -s -L -k -u ${uid}:${pat} $url | jq -r '. | .repos_url')
	for repoUrl in $repoUrls ; do
	    repoNames=$(curl -s -L -k -u ${uid}:${pat} $repoUrl | jq -r '.[] | .name')
	    for repoName in $repoNames ; do
		# Write the conf file, with a poll interval of 24hrs
		rn=$repoName
		repoName=$(echo $repoName | tr '-' '_')
		echo "[github_api_repos_commits://Commits_$repoName]" | cat >> $FN
		echo "github_creds = ${acctName}" | cat >> $FN
		echo "github_owner = $org" | cat >> $FN
		echo "github_repo = $rn" | cat >> $FN
		echo "interval = 86400" | cat >> $FN
		echo "" | cat >> $FN
		let repoCount=repoCount+1
	    done
	done
	let i=i+1
    done
fi
ts=`date "+%Y%m%d-%H%M%S"`
if [ -f "${CONFIG}" ] ; then
    fn="${BACKUP}/$ts.inputs.conf"
    log "INFO" "Backing up ${CONFIG} to ${fn}"
    cp -rf "${CONFIG}" "${fn}"
    if [ -f "${FN}" ] ; then
	log "INFO" "Replacing ${CONFIG} with ${FN}"
	mv -f "${FN}" "${CONFIG}"
    fi
    find "${BACKUP}" -mtime +10 -type f -delete  # delete files oder than 10 days
fi
log "INFO" "Created ${CONFIG}, wrote $count orgs. and $repoCount repos."
exit
