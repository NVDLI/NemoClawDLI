# Developer Certificate of Origin

Contributions use the [Developer Certificate of Origin 1.1](https://developercertificate.org/).
By adding a `Signed-off-by` trailer, a contributor certifies that they created the contribution or
have the right to submit it under this repository's license, and that the contribution and signoff
record may be public and redistributed.

Sign every commit with your real name and an email address you control:

```text
Signed-off-by: Example Contributor <contributor@example.com>
```

Git can add the trailer:

```bash
git commit --signoff
```

If a check fails, amend an unpublished commit with `git commit --amend --signoff`. For several
commits, rebase and amend each commit deliberately. Do not rewrite commits another contributor has
already based work on; add corrected commits or coordinate the repair instead.

## Stacked proposal branches

Do not use a host-generated squash or merge commit to integrate one unmerged proposal branch into
another. Generated commits do not inherit the source commits' DCO trailers and can make the parent
proposal fail its complete-range check. Preserve the original signed commits with a maintainer-owned
fast-forward, or deliberately rebase or cherry-pick them while retaining authorship and matching
signoffs. Never fabricate a trailer for a bot or another contributor.

The signoff records origin. It does not replace source provenance, license review, tests, or human
approval required by [`CONTRIBUTING.md`](CONTRIBUTING.md).
