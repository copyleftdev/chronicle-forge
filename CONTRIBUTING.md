# Extending Chronicle Forge

Each scenario should include observable evidence, oracle facts, expected
observations, and claims that must remain unknown. All identities must be
fictional. Keep personal data and credentials out of fixtures.

1. Add a Git operation in `generate.py` or an event in `api_fixtures`.
2. Specify known facts in `oracle`; do not leak expected labels into evidence.
3. Add a test that would fail if the collector or generator mishandled the case.
4. Document the access surface: shared Git, local metadata, simulated API or oracle.
5. Test two independent generations before changing the generator version.

Keep mathematical counts, dates and provenance deterministic. Model inference
belongs in a separate evaluator, never in corpus construction.

Useful future expansions: interrupted rebases/cherry-picks, multiple repositories
with overlapping communities, sparse/shallow/partial clones, submodule and LFS
fixtures, webhook delivery/replay, realistic rate budgets, and a live GitHub
contract adapter. These are not implemented in v0.1.0.

The checked-in holdout assignment is a public partition for exercising the
evaluation workflow. Do not describe results on it as secret or independent
generalization evidence.
