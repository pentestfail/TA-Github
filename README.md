GitHub Addon
========================
Provides modular inputs & framework to ingest JSON data from Github APIs.

### App Setup:
1. Store Github credentials to be used on the "Configuration" page and "Account" tab, then click "Add" to add new credentials. Since an account is specific to a GitHub instance, you must specify the server for the account (will be used for all inputs leveraging the account credentials).
    - App supports authentication via username & password or account "personal access tokens"
    - DOES NOT support 2-factor tokens
    - [GitHub Personal Access Tokens](https://github.com/blog/1509-personal-api-tokens)
2. Add inputs via the add-on's "Inputs" page, clicking "Create New Input", then clicking an input type you wish to create and entering the repository "owner" and "repository" from which the input will collect data.

```
Name of user or Github organization which owns the repository. Example: https://api.github.com/[OWNER]/repo
```
```
Name of repository. Example: https://api.github.com/owner/[REPOSITORY]
```

### APIs supported:
- Repository Stats (https://developer.github.com/v3/repos/statistics/#get-contributors-list-with-additions-deletions-and-commit-counts)
- Repository Commits (https://developer.github.com/v3/repos/commits/#list-commits-on-a-repository)
- Repository Issues (https://developer.github.com/v3/issues/#list-issues-for-a-repository)

## Release Notes:
Initial release. Documentation will be included in future releases.

## Submit issues or requests via Github:
TA-Github: https://github.com/pentestfail/TA-Github