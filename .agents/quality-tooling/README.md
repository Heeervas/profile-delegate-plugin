# Quality CI trust boundary

This directory vendors a locally derived, hash-identified builder-assurance 1.1.0
snapshot. Algorithms and metric specifications are unchanged. The derivation separates
report orchestration, adapter execution, per-file analysis and artifact coverage;
exception validation and blocking decisions have independent owners. E702 edits
only expand statement separators. Both normalized schemas are included because
the canonical reporter loads them even for Python-only policies. `provenance.json`
identifies both original and current vendor bytes. No private checkout, credentials or skill installation
is needed. Dependency versions and distribution hashes are fixed in requirements.txt;
requirements.in records the complete explicit closure. Resolution used uv 0.12.3;
execution CI retains the existing pinned uv 0.11.6 contract.

CI checks out the actual PR head (not the synthetic merge) and an independently
selected trusted base: PR base SHA or push-before SHA. It installs only trusted-base
requirements in an isolated environment and executes only the trusted-base gate
and analyzer. Candidate policy must be semantically identical to the trusted policy;
thresholds, exclusions, adapters, exceptions and baseline cannot self-approve.
Protected workflow, gate, tests and tooling must be byte-identical. Measurements
always use `all`, TOP and the immutable policy baseline, which must be an ancestor.
Old reports are never inputs; fresh canonical JSON is emitted to job stdout.

## Adoption / governance changes

The existing committed base has neither quality.yaml nor this tooling. First
adoption therefore intentionally fails closed. A maintainer must separately review
and authorize the policy, immutable repair baseline, tooling hashes, dependency
closure and workflow, then establish them on the protected trusted branch. There is
NO candidate-controlled bypass, magic label or in-file approval switch. Subsequent
changes to protected governance likewise require separately reviewed adoption;
a normal candidate cannot make its changed enforcement pass itself. New branches
with a zero push-before SHA also fail closed; use a PR against an established base.

Repository-owned workflows cannot prevent an authorized workflow editor removing
the job. Required checks, protected governance ownership and adoption procedures
must be configured independently by maintainers. No remote controls are configured
by this implementation, and no GitHub run is claimed. Pinning a vendor snapshot
does not itself establish provenance authenticity: review is the initial trust root.

The policy baseline predates this vendor snapshot; full-scope measurement includes
the vendor itself. Local refactoring repairs its blocking findings without exclusions,
metric changes or a new exception. Exact report/exit equivalence against the original
hash-pinned reporter is exercised with `scripts/verify_analyzer_equivalence.py` over
real Git states, normalized evidence, failures and the complete candidate. This is
local preparation, not self-approval of governance or remote adoption. See
`.agents/validation.md` for executable checks and STATE.md for current evidence.

Gate tests use disposable real Git repositories and the isolated analyzer interpreter
specified by QUALITY_GATE_PYTHON. They use stdlib unittest, so the isolated lock
needs no test-only dependency. The dedicated quality job explicitly runs trusted
base tests with `python -I -B -m unittest discover -s trusted/.agents/quality-tooling/tests -v`
before candidate measurement. Locally, run `python -I -B -m unittest discover
-s .agents/quality-tooling/tests -v`, or explicitly select this independent test
file in pytest with `--confcutdir .agents/quality-tooling -o 'addopts='` to avoid
plugin runtime conftest requirements.
