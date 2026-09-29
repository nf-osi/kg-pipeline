# Demo 2 presenter app

A single-file, local-only presenter for the Demo 2 story
([docs/demos/demo-2.md](../../docs/demos/demo-2.md)): patient `JH-2-002`,
genotype → pathway → mechanism → measured drug response, run live across three
sagebrain named graphs.

## Run it

No build, no server needed — the query API has open CORS:

```bash
# token picked up from the URL fragment (never sent to any server; stripped on load)
xdg-open "file://$PWD/examples/sagebrain-demo/index.html#token=$SYNAPSE_AUTH_TOKEN"
```

or open `index.html` directly and paste a Synapse PAT into the key panel — the
**Token** button top right, or **Access token** on the setup step, opens a side
drawer for it (`k` on the keyboard). The token must belong to a member of the
Sage Brain team; it is kept in `sessionStorage` only (gone when the tab closes).

## What each step runs

Every step embeds the same SPARQL as the corresponding canned query in
[`scripts/query_demo.py`](../../scripts/query_demo.py) — that script is the
source of truth; if a query changes there, change it here too.

| Step | Canned query | Graphs |
|---|---|---|
| Setup | `pinned` (full census via `graphs` behind a separate slow button) | (pinned three) |
| 1 Genotype | `demo2-progression-detail` | nf |
| 2 Screening | `demo2-screening` | nf |
| 3 Mechanism → pathway | `demo2-mechanism` | nf + opentargets + reactome |
| 4 Indication | `demo2-indication` | nf + opentargets |

Pinned graph versions live in the `CONFIG` object at the top of the script in
`index.html`. When a newer snapshot is deposited, re-pin there (the setup step's
connection check flags a missing pinned graph).

## Before the talk

Run **Rehearse — run all four steps now** on the setup step once. It runs all four
queries in sequence and reports `4 of 4 returned`, so a slow query, an unloaded
dataset, or an expired token turns up in rehearsal rather than on stage.

If a live query fails during the talk, each step offers **Show the recorded result
instead** — the verified 2026-09-28 results, embedded in the file. It renders the
same chart, stamped `Recorded 2026-09-28, not live.` It is never used silently and
never substitutes for a failure message.

## Keyboard

| Key | |
|---|---|
| `←` `→` | move between steps |
| `n` | presenter notes — the expected result for each step, and what to point at |
| `r` | reset the run (keeps the token, clears every result) |
| `k` | open the token panel (`Esc` shuts it) |
