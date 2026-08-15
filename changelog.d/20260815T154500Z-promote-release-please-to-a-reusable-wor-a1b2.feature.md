Added `release-please.yml` as a reusable workflow so the fleet's release
automation lives in one place instead of a copy in each of the fourteen
consuming repos.  It carries the `workflows: write` token scope that release
creation needs whenever workflow files have drifted since the release commit —
without it the tag is never cut and every later push retries the same
`Resource not accessible by integration` failure.
