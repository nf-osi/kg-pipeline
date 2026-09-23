# Build capacity — where CI is constrained, and what to do about it

Working notes on whether `build-image` needs more than a GitHub-hosted runner, written
while adding the opt-in variant-layer build ([`8bffd515`](https://github.com/nf-osi/kg-pipeline/commit/8bffd515)).
The prompt was "set up our own build runner on AWS for higher capacity". The measurements
below say that is the right instinct for one of the three reasons usually given for it,
and the wrong tool for the other two.

**Recommendation in one line:** take the free disk fix now, mirror the source data to S3
next, and revisit a runner only if a measured build still doesn't fit.

## What we measured

Run [`35825572724`](https://github.com/nf-osi/kg-pipeline/actions/runs/35825572724) —
the first dispatch of `build-image` with `variants: true`, on `ubuntu-latest`:

| Step | Time | Outcome |
|---|---|---|
| Materialize RDF pipeline (core) | 7.6 min | ok |
| Validate RDF outputs | 0.5 min | ok |
| Install vrsify (`cargo install`, pinned rev) | **0.4 min** | ok |
| Fetch GRCh38 + derive seqmap (983 MB download, gunzip to 3.1 GB, digest per contig) | **0.7 min** | ok |
| Materialize the variant layer | 0.1 min | **failed — upstream, see below** |

Baseline for comparison: `build-image` without variants has a median of 9.8 min over its
last 28 runs.

The two steps that looked expensive when they were written — building a Rust binary from
source and pulling a whole reference genome — cost **67 seconds between them**. Neither
is a reason to move hardware.

## Runner specification, as it actually applies to us

`nf-osi/kg-pipeline` is a **public** repo in an org on the **Free** plan. Two
consequences that shape every option below:

- GitHub-hosted standard runners are free and unlimited for public repos. The 2,000
  minute / 500 MB figures are private-repo quotas and do not apply. **We pay nothing for
  CI today**, so anything moved to AWS is new spend, not a saving.
- GitHub's *larger* runners need Team or Enterprise Cloud and are billed even for public
  repos. Not available without an org upgrade (~25 seats).

| | vCPU | RAM | Disk |
|---|---|---|---|
| `ubuntu-latest`, public repo | 4 | 16 GB | 14 GB documented, **~21 GB actually free** |
| CodeBuild Linux Medium | 4 | 8 GiB | 128 GB |
| CodeBuild Linux Large | 8 | 16 GiB | 128 GB |
| CodeBuild Linux XLarge | 36 | 72 GiB | 256 GB |

## Driver 1 — the disk ceiling

Real, but **not yet demonstrated**: the run above died before reaching the disk-hungry
part, so the projection below is arithmetic, not observation. Measured footprints from a
local variants build:

| | Size | Freed before the index build? |
|---|---|---|
| GRCh38 (`hg38.fa.gz` → `hg38.fa`) | 983 MB → 3.05 GB | yes, by `Reclaim disk` |
| cBioPortal MAFs (4 studies) | 607 MB | no — build input |
| VRS NDJSON intermediates | 741 MB | yes, by `Reclaim disk` |
| `data/rdf/variants/*.ttl` | 1.18 GB | no — build input |
| Core `data/rdf/`, `data/csv/`, `data/raw/` | ~1 GB | no |
| Three QLever indexes in one job (`runtime-rdf`, `runtime-text`, `runtime-variants`) | ~930 MB each plus sort intermediates | n/a |

Against ~21 GB this is tight but probably survivable *with* the `Reclaim disk` step, and
would very likely not fit without it. The cheap mitigation is
[`jlumbroso/free-disk-space`](https://github.com/jlumbroso/free-disk-space), which
reclaims ~31 GB in ~3 min by deleting preinstalled .NET/Android/Haskell toolchains we
never use — taking the runner to ~50 GB for free. That is a one-step change and it should
be tried before any infrastructure exists.

Note also that the job builds **three separate indexes**. Splitting `build-image` into
parallel jobs per target would cut peak disk roughly threefold and shorten wall-clock,
independent of what hardware it runs on.

## Driver 2 — control and reproducibility

This is the one the failed run actually proved, and it is more urgent than capacity.

`Materialize the variant layer` failed with `HTTP 403` from
`fetch_cbioportal_maf.resolve_lfs_download`. The body:

> `This repository exceeded its LFS budget. The account responsible for the budget should increase it to restore access.`

That is not a rate limit, not an auth problem, and not ours to fix. `cBioPortal/datahub`
has exhausted its Git LFS bandwidth quota, so **the four MAFs the variant layer is built
from cannot currently be downloaded by anyone**, in CI or locally, with or without a
token. The variant layer is unbuildable from source until upstream restores it.

Two things survive the outage, and they are the basis of the fix:

- The pointers still resolve. `read_lfs_pointer` uses the contents API, which is
  unaffected, so the pinned `oid`s are still readable and still verifiable.
- We hold the bytes. All four local `data/raw/*_data_mutations.txt` hash to exactly the
  pinned oids:

  | Study | sha256 == pinned LFS oid | Size |
  |---|---|---|
  | `nst_nfosi_ntap` | `57f97f7f…` ✓ | 27,602,039 |
  | `schw_ctf_synodos_2025` | `103448718d…` ✓ | 47,216,814 |
  | `lgg_ctf_synodos_2025` | `fd30ed55…` ✓ | 36,502,411 |
  | `nfib_ctf_biobank_2025` | `5d1792d0…` ✓ | 495,645,736 |

So a content-addressed mirror is straightforward and loses nothing: store the objects
under their oid, fetch from the mirror first, and keep validating against the upstream
pointer so the pin still means what it says. `scripts/fetch_cbioportal_maf.py` already
documents a cBioPortal REST API fallback as "documented fallback, not implemented" — that
remains a worse option, because the REST route drops `Consequence`, `HGVSc`, `HGVSp`,
`HGNC_ID` and gnomAD AF, which the variant layer needs.

This is a *storage* problem, not a *compute* problem. It is solved by S3 plus a few lines
in the fetcher, on whatever runner we use. It does not argue for AWS runners; it argues
for AWS storage, which we already have (the Sage Brain deposit path writes to S3 from
CI under an existing OIDC role).

A secondary robustness gap worth fixing at the same time: the fetcher anticipates LFS
failures reported as an `error` field inside a `200` response, but an HTTP-level `403`
propagates as a raw `urllib` traceback. The message above is buried in a 60-line Dagster
stack trace.

## Driver 3 — future heavy workloads

Nothing here is constrained today, but three things are visibly approaching:

- `publish-embeddings.yml` already carries `timeout-minutes: 90` and has never run. Node
  embeddings over a 26.9M-triple graph are the most plausible first workload to exceed
  16 GB RAM.
- The variant layer is four studies. More studies scale MAFs, NDJSON and TTL roughly
  linearly; `nfib_ctf_biobank_2025` alone is 496 MB and 680k rows.
- The GitHub-hosted job cap is 6 hours. Self-hosted is 5 days. We are nowhere near
  either, and should say so rather than cite it as a reason.

The honest read: this driver justifies *knowing what we'd do*, not doing it yet.

## Options

| Option | Disk | RAM ceiling | Cost | Effort |
|---|---|---|---|---|
| Stay hosted, add `free-disk-space` | ~50 GB | 16 GB | $0 | ~10 min |
| Stay hosted, split targets into parallel jobs | ~21 GB each | 16 GB | $0 | ~half a day |
| **AWS CodeBuild managed runners** | 128 GB | 16 GiB (Large) / 72 GiB (XLarge) | ~$0.60/build at Large ≈ $12/mo | ~half a day |
| Self-managed ephemeral EC2 (ARC, `terraform-aws-github-runner`) | anything | anything | ~$0.20/build + idle + ops | days, ongoing |
| Third-party managed (RunsOn, Depot, Blacksmith) | anything | anything | varies | ~hours, new vendor |

CodeBuild is the strongest AWS option *for us specifically*: the account, the OIDC trust
(`GitHubActionPushKGToECR`) and ECR already exist in `050451359079`; runners are ephemeral
per job; and the webhook filters on workflow name, so only `build-image` need move.
Compute is chosen per job with a `runs-on` label, so a single project can serve a small
job and a 72 GiB one.

### The constraint any self-hosted path must respect

GitHub's own guidance:

> We recommend that you only use self-hosted runners with private repositories. This is
> because forks of your public repository can potentially run dangerous code on your
> self-hosted runner machine by creating a pull request that executes the code in a
> workflow.

`build-image.yml` is `workflow_dispatch`/tag-only and cannot be triggered by a fork, so
routing that one workflow is defensible. **`tests.yml` runs on `pull_request` and must
stay GitHub-hosted.** Any migration has to state this split explicitly rather than move
`runs-on` globally.

Also worth pricing in as risk, not cost: GitHub announced a $0.002/min charge for
self-hosted runners from March 2026, then postponed it after pushback. It has not taken
effect and no replacement has been announced, but the intent was stated once.

## Proposed sequence

Staged deliberately so each step is independently useful and the expensive one is last.

1. **Unblock the variant build.** Mirror the four pinned MAF objects to S3, content-
   addressed by oid; make `fetch_cbioportal_maf.py` try the mirror first and fall back to
   upstream LFS, verifying the sha256 against the upstream pointer either way. Without
   this, the variant layer cannot be rebuilt at all.
2. **Surface upstream failures legibly.** Catch `HTTPError` in `resolve_lfs_download` and
   raise the LFS budget/quota message directly, matching the handling already there for
   in-band LFS errors.
3. **Take the free headroom.** Add `free-disk-space` to `build-image`, gated on
   `inputs.variants` so normal builds don't pay the ~3 min. Keep the `df -h /` in
   `Reclaim disk` and record the real number — this is the measurement that decides
   whether anything below is needed.
4. **Get a green variants build and measure it.** Peak disk, wall-clock, image size. Until
   this exists, every capacity claim here is a projection.
5. **Split `build-image` into per-target jobs.** Parallel `runtime-rdf` / `runtime-text` /
   `runtime-variants`, sharing the materialized RDF via artifact. Cuts peak disk ~3× and
   wall-clock, and is a prerequisite for sending only the heavy job elsewhere.
6. **Only then, if 4 shows it's still tight:** stand up one CodeBuild runner project
   scoped to `build-image`, with the webhook filtered to that workflow, and move the
   variants job alone.

Steps 1–2 are unblocking work and should not wait on the rest. Step 6 is the only one
that creates infrastructure, and it is deliberately last because nothing measured so far
requires it.

## What we are not doing, and why

- **GitHub larger runners** — needs an org plan upgrade, and is billed even for a public
  repo. Strictly worse than CodeBuild for us.
- **An always-on EC2 runner** — a ~10-minute build a few times a week does not justify a
  persistent host, and a long-lived self-hosted runner on a public repo is the exact
  configuration GitHub warns against.
- **Moving all of CI** — `tests.yml` runs on fork PRs. It stays hosted regardless.
- **Vendoring the MAFs into git** — 607 MB, and it would duplicate the LFS problem in our
  own repo. Content-addressed S3 is the same guarantee without the repo weight.
