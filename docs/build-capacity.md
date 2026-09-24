# Build capacity — where CI is constrained, and what to do about it

Working notes on whether `build-image` needs more than a GitHub-hosted runner, written
while adding the opt-in variant-layer build ([`8bffd515`](https://github.com/nf-osi/kg-pipeline/commit/8bffd515)).
The prompt was "set up our own build runner on AWS for higher capacity". The measurements
below say that is the right instinct for one of the three reasons usually given for it,
and the wrong tool for the other two.

**Recommendation in one line:** mirror the source data (done — that was the real
problem), and do *not* move runners; a completed build has since measured 85 GB free
where this doc originally assumed 21 GB.

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
| `ubuntu-latest`, public repo | 4 | 16 GB | 14 GB documented, **145 GB volume / 85 GB free, measured** |
| CodeBuild Linux Medium | 4 | 8 GiB | 128 GB |
| CodeBuild Linux Large | 8 | 16 GiB | 128 GB |
| CodeBuild Linux XLarge | 36 | 72 GiB | 256 GB |

## Driver 1 — the disk ceiling — **measured, and it does not exist**

> **Corrected 2026-09-24 by run [`35937975360`](https://github.com/nf-osi/kg-pipeline/actions/runs/35937975360)**, the first
> variants build to complete. Everything in this section below the measurement was
> written from the documented runner spec and is wrong. It is kept rather than deleted
> because the reasoning it contains is the reasoning that *would* apply on a 21 GB
> runner, and because the gap between the documented spec and the real one is the
> finding.
>
> | point in the job | total | used | free |
> |---|---|---|---|
> | before `free-disk-space` | 145 GB | 60 GB | **85 GB** |
> | after `free-disk-space` (saved 22 GB) | 145 GB | 38 GB | 108 GB |
> | peak, just before `Reclaim disk` | 145 GB | 43 GB | **102 GB** |
> | after `Reclaim disk` | 145 GB | 39 GB | 106 GB |
>
> `ubuntu-latest` is a **145 GB volume with 85 GB free**, not the 14 GB the GitHub docs
> state or the ~21 GB widely reported. The entire variant build — reference, MAFs,
> NDJSON, 1.18 GB of Turtle and three QLever indexes — peaked at about **5 GB above
> baseline**. It would have fitted with roughly 80 GB to spare and no cleanup at all.
>
> So `free-disk-space` is unnecessary here: it spent 1.1 min freeing 22 GB that were
> never needed. `Reclaim disk` is still worth keeping, not for headroom but because its
> `df` is the only thing that would catch this premise going stale in the other
> direction.
>
> The lesson generalises past this repo: the documented runner spec was off by an order
> of magnitude, and one `df` settled what a page of arithmetic could not.

The projection that prompted all of the above, from a local variants build:

| | Size | Freed before the index build? |
|---|---|---|
| GRCh38 (`hg38.fa.gz` → `hg38.fa`) | 983 MB → 3.05 GB | yes, by `Reclaim disk` |
| cBioPortal MAFs (4 studies) | 607 MB | no — build input |
| VRS NDJSON intermediates | 741 MB | yes, by `Reclaim disk` |
| `data/rdf/variants/*.ttl` | 1.18 GB | no — build input |
| Core `data/rdf/`, `data/csv/`, `data/raw/` | ~1 GB | no |
| Three QLever indexes in one job (`runtime-rdf`, `runtime-text`, `runtime-variants`) | ~930 MB each plus sort intermediates | n/a |

Against ~21 GB that would have been tight. Against the 85 GB the runner actually has, it
is not close to a constraint.

The job does still build **three separate indexes** in one job. Splitting `build-image`
into parallel jobs per target would shorten wall-clock — the case for it is now purely
time, not disk.

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
| **Stay hosted, change nothing** | **85 GB free, measured** | 16 GB | $0 | none |
| Stay hosted, split targets into parallel jobs | 85 GB each | 16 GB | $0 | ~half a day |
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
3. ~~**Take the free headroom.**~~ Done, and then shown to be unnecessary — see the
   measurement above. `free-disk-space` should be dropped from `build-image`; it costs
   1.1 min and frees space nothing was competing for.
4. ~~**Get a green variants build and measure it.**~~ Done: run `35937975360`, 29.4 min
   end to end, peak 43 GB of 145 GB, images pushed. This is what falsified step 1 of the
   disk argument.
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
