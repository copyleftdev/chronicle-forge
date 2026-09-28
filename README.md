# Chronicle Forge

**A synthetic history laboratory for Git and GitHub forensics.**

Generate a real Git repository, walk an API through virtual time, and check
observations against a separate ground-truth manifest. Everything runs locally;
no credentials, paid models, GitHub account, or network downloads are needed to
generate the corpus.

This is an initial, working test bed with **20 scenario families**. It is not a
complete GitHub emulator or a validated recruiting benchmark. All actors and
activity are fictional; email addresses use `example.invalid`.

## Quick start

Requires Python 3.11+ and a recent Git with SHA-1 object-format selection,
worktrees, notes, rerere and commit-graph support. Tested on Linux. Use commands
from this directory; no package installation required.

```sh
python3 -m chronicle_forge generate generated/demo --seed 42
python3 -m chronicle_forge snapshot generated/demo --at 2020-02-01T00:08:00Z --kind comment
python3 -m chronicle_forge serve generated/demo --port 8765
```

In another terminal:

```sh
curl 'http://127.0.0.1:8765/objects?kind=comment&pr=PR1&first=3&at=2020-02-01T00:08:00Z'
curl 'http://127.0.0.1:8765/objects/C8?at=2020-02-01T00:10:00Z'
curl 'http://127.0.0.1:8765/objects/PR5?at=2040-01-01T00:00:00Z'
git -C generated/demo/evidence/repo log --all --graph --oneline
python3 -m unittest discover -s tests -v
```

Generation refuses to overwrite an existing directory. Use a fresh destination
for every seed or version. Changing the seed changes synthetic content and
dependent commit IDs; it currently does not randomize scenario topology.

## Three separate surfaces

```text
generated/demo/
├── corpus.json                     Version, seed, event digest
├── evidence/
│   ├── repo/                       Real Git repository, including local state
│   ├── transport-clone/            Ordinary Git transport copy for comparison
│   ├── linked-worktree/            Real worktree with a .git pointer file
│   └── local/                      Captured conflict and inspection records
├── simulator/events.json           Service backing store: includes future events
└── oracle/
    ├── manifest.json               Facts, expected observations, unknowns, splits
    └── generation-trace.json        Builder command audit
```

An evaluator should receive only its assigned evidence surface. Keep both
`oracle/` **and** the simulator backing store outside the model/collector's
filesystem access. The API does not serve either directory and does not load
the oracle. Separation by directory is organizational, not an OS security boundary.

The local Git repository is a static full fixture and includes its future-dated
branch. Virtual time filters API evidence; it does not hide future Git objects
from a collector given full filesystem access. Choose access scope explicitly.

## Scenario coverage

| Family | Generated evidence |
|---|---|
| Merge | Real two-parent merge |
| Squash | Different feature/integration SHAs with matching trees |
| Rewrite | Amended-away commit, reflog retention, simulated force-push event |
| Rebase | Real rebase changes commit ID and parent |
| Backport | Cherry-pick trailer plus extra release-specific commit |
| Rename | Real file rename and updated import |
| Revert | Dependency change followed by a real revert |
| Generated work | Large mechanical diff and language-classification attributes |
| Identity | `.mailmap`, stable API identity with renamed login, bot identity |
| Coauthor | Commit trailer distinct from verified account identity |
| Pagination | Eight comments, default page size three |
| Edit | Same comment ID with changed content |
| Deletion | Comment disappears after its virtual deletion time |
| CI attempts | Failed run, successful second attempt, separately skipped run |
| Retention | Log becomes unavailable after expiry |
| Access | Private object absent from public view |
| Injection | Hostile instructions inside a synthetic comment |
| Local state | Stash, notes, unresolved-conflict snapshot, rerere resolution |
| Future | Real future-dated Git commit and clock-gated API event |
| Network | Directed follow edges, including a reciprocal pair |

Additional Git shapes include an annotated tag, binary blob, executable file,
packed refs, commit-graph, and linked worktree. `transport-clone` lacks the source
stash, rerere records, and amended-away object; notes are not fetched by default.

The manifest contains development/holdout assignments for testing evaluation
workflows. Because source and expected answers will be public, this is **not a
secret held-out benchmark**. Genuine generalization tests need separately
maintained scenarios unseen during prompt or rule tuning.

## Virtual timeline

```mermaid
flowchart LR
    A[2019: initial project] --> B[2020 Feb: feature, comments and CI]
    B --> C[2020 Mar: rewrite and squash]
    C --> D[2020 Apr: backport with extra change]
    D --> E[2020 May-Jul: rename, rebase, revert, conflict]
    E --> F[2040: future fixture]
```

At `2020-02-01T00:08:00Z` there are eight comments. At 00:09 C8 is edited.
At 00:15 C2 is deleted. On February 5 the failed-run log expires.
Advancing `at` changes evidence visibility without rewriting generated files.

## API contract

All responses are explicitly synthetic. The server binds to localhost only.

| Endpoint | Behavior |
|---|---|
| `GET /health` | Health and synthetic marker |
| `GET /objects` | Filter with `kind`, `pr`; paginate with `first`, `after` |
| `GET /objects/ID` | A visible entity at the requested `at` timestamp |
| `POST /graphql` | Named operations `Object` and `Objects`; GitHub-shaped error envelope |

Common parameters: `at` (timezone-aware ISO-8601), `role=public|member`.
The role parameter is a fixture control, **not authentication**.
Default time is `2020-02-01T00:08:00Z`.

The `/graphql` route is intentionally a small named-operation protocol, **not a
GraphQL parser**. It rejects query text instead of pretending arbitrary GitHub
queries are supported:

```json
{
  "operationName": "Objects",
  "variables": {
    "at": "2020-02-01T00:08:00Z",
    "kind": "comment",
    "pr": "PR1",
    "first": 3
  }
}
```

Pages contain `nodes`, `totalCount`, and `pageInfo`. Cursors are scoped to the
corpus, time, filters and role. Reusing one in a different view returns 409.
That is this simulator's explicit consistency policy, not a promise of GitHub's
cursor behavior. Use ETags and `If-None-Match` to test unchanged 304 responses.

`fault=rate_limit` on GET returns 429 with `Retry-After: 1`;
`fault=unavailable` returns 503. These are deterministic injected faults, not
a production quota model. Expired direct log requests return 410. Private and
absent objects both return 404 to a public view. Exact status semantics are
fixture contracts, not universal claims about live GitHub endpoints.

## Reproducibility and verification

Git author/committer dates and identities are controlled. User/global Git
configuration, signing and template hooks are excluded. Same seed and generator
version produce identical tested commit IDs, oracle data and event bytes on the
tested Git implementation. Absolute paths and filesystem metadata differ, so
this is not a byte-identical filesystem image. Git versions/platforms may also
affect derived caches; pin the runtime for long-lived reference runs.

The test suite generates two independent corpora and compares their object IDs
and event streams, then checks real history relationships and HTTP behavior.
It opens a temporary localhost socket for HTTP tests. No remote services are used.

## Public-repository preparation

Publish the generator, docs and tests. Generated fixtures are intentionally
gitignored; regenerate them with recorded version/seed. This source repository
contains no collected developer profiles, API credentials, or scraped histories.

Publishing this source does not create synthetic events on GitHub. A later
live adapter should validate real API semantics using a dedicated sandbox,
with publication explicitly separated from local generation. GitHub-managed
event timestamps cannot be backdated by this simulator.

See [CONTRIBUTING.md](CONTRIBUTING.md) for extending scenarios.
