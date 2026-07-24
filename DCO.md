# Developer Certificate of Origin

Contributions use the [Developer Certificate of Origin 1.1](https://developercertificate.org/).
The complete text follows verbatim.

```text
Developer Certificate of Origin
Version 1.1

Copyright (C) 2004, 2006 The Linux Foundation and its contributors.

Everyone is permitted to copy and distribute verbatim copies of this
license document, but changing it is not allowed.

Developer's Certificate of Origin 1.1

By making a contribution to this project, I certify that:

(a) The contribution was created in whole or in part by me and I
    have the right to submit it under the open source license
    indicated in the file; or

(b) The contribution is based upon previous work that, to the best
    of my knowledge, is covered under an appropriate open source
    license and I have the right under that license to submit that
    work with modifications, whether created in whole or in part
    by me, under the same open source license (unless I am
    permitted to submit under a different license), as indicated
    in the file; or

(c) The contribution was provided directly to me by some other
    person who certified (a), (b) or (c) and I have not modified
    it.

(d) I understand and agree that this project and the contribution
    are public and that a record of the contribution (including all
    personal information I submit with it, including my sign-off) is
    maintained indefinitely and may be redistributed consistent with
    this project or the open source license(s) involved.
```

By adding a `Signed-off-by` trailer, a contributor makes this certification.

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
