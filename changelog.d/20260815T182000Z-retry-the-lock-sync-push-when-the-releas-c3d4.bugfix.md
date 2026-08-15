`release-please.yml`: retry the `uv.lock` sync when the release branch moves
under it.  release-please finishes writing the branch asynchronously and a
second run triggered by another merge does the same work concurrently, so the
push could be rejected with `(fetch first)` and fail the job — observed on
robotsix-file-hub minutes after adoption.  The lock commit is generated, not
authored, so the recovery is to start over on the branch's new tip.
