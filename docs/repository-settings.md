# Repository settings

GitHub settings live outside git, so this file records what is configured and
why. If a setting changes in GitHub, update this file in the same pull
request.

Last verified: 2026-10-02.

## Branch protection on `main`

| Setting | Value | Why |
|---|---|---|
| Pull request required | Yes, 0 approvals | Every change is reviewed in a PR. A solo maintainer cannot approve their own PR, so no approval count is enforced. |
| Required status check | `feedback` (strict) | Nothing merges unless the CI is green and the branch is up to date with `main`. |
| Resolve conversations | Required | Review comments cannot be ignored. |
| Dismiss stale approvals | Yes | A new push invalidates an earlier review. |
| Include administrators | Yes | The rules also bind the owner. |
| Force pushes | Blocked | Published history is never rewritten. |
| Branch deletion | Blocked | `main` cannot be deleted. |

`feedback` is the job id in `.github/workflows/harny-feedback.yml`. When new
workflows add jobs that must pass (for example `tests` on Day 6), add their
check names to the required list.

If a broken CI blocks the fix for itself, an administrator can temporarily
turn off "Include administrators", merge the fix, and turn it back on.

## Merging

| Setting | Value | Why |
|---|---|---|
| Delete branch on merge | On | Merged branches do not pile up. |
| Auto-merge | Allowed | A PR can be queued to merge once the required checks pass. |
| Update branch button | On | Brings a PR up to date with `main` from the UI. |
| Squash merge | Allowed | Collapses noisy work-in-progress commits. |
| Merge commit | Allowed | Keeps granular history, consistent with earlier PRs. |
| Rebase merge | Disabled | Rewrites commit hashes and is easy to misuse. |

## Security

| Setting | Value |
|---|---|
| Secret scanning and push protection | On |
| Dependabot alerts and security updates | On |
| Dependabot version updates | `github-actions`, weekly (`.github/dependabot.yml`) |
| Default `GITHUB_TOKEN` permissions | Read-only |

The `pip` ecosystem is added to `.github/dependabot.yml` once the Python
toolchain is decided and a manifest exists.
