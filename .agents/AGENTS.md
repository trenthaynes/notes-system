# Project rules

## Documentation requirements

All agent-created working documentation for this multiroot project should be placed under `.agents/<feature>/`, using an appropriate sub-directory path. Ask for clarification if necessary.

Do not use `.agents/` for durable project documentation. Durable documentation such as `README.md`, `docs/`, and code-adjacent reference material should live in the tracked location appropriate to its purpose.

**Naming standards for `.agents/<feature>/` artifacts:**

- Store artifacts under a type-specific subdirectory such as `research/`, `specification/`, `plans/`, `summaries/`, `backups/`, `scripts/`, `prompts/`, or `samples/`.
- Prefer filenames that sort well and match the artifact type already used in this repo.
- Treat planning artifacts as immutable snapshots once they are reviewed, approved, or used to gate implementation.
- For substantive revisions, create a new file instead of overwriting the old one.
- Minor typo fixes or pre-approval clarifications may be edited in place.
- For dated working documents, prefer:
  - `YYYYMMDD_<topic>_<artifact>.md`
  - Example: `20260518_phase-0a-pulumi-eks-dependency-upgrade_spec.md`
- If you need multiple revisions of the same artifact on the same day, prefer:
  - `YYYYMMDD-rN_<topic>_<artifact>.md`
  - Example: `20260518-r2_phase-0a-pulumi-eks-dependency-upgrade_spec.md`
- For timestamped backups or captures, prefer:
  - `YYYYMMDDTHHMMSSZ-<topic>.<ext>`
  - Example: `20260519T202157Z-dev-aws-auth.raw.json`
- Use lowercase letters, numbers, and hyphens or underscores consistently within a filename.
- When extending an existing document series, follow the naming pattern already present in that directory rather than introducing a new one.
- When a newer artifact replaces an older one, add a short `Supersedes:` line near the top of the new file when useful.

## Shell command requirements

When running shell commands, request the appropriate permissions upfront.

Never self attribute or add AI attribution to documents, pull-requests, or commit messages.

## PHASED GATES for all work

Normative workflow for changes that touch code.

### Hard gates

1. Do not edit implementation files (Helm values, Pulumi that mutates cluster state, ingress YAML) until:
   - `.agents/<feature>/specification/<revision>_<slug>_spec.md` exists, Phase 2 verification passes, and the user approves the spec in chat.
   - `.agents/<feature>/plans/<revision>_<slug>_plan.md` exists, Phase 3 verification passes, and the user approves the plan in chat.

2. If this file is missing, restore or recreate it before claiming Phase work complete.

### Phases

| Phase | Artifact | Advance when |
|-------|-----------|--------------|
| 1 Research | `.agents/<feature>/research/<revision>_<slug>_research.md` | Gate in this doc passes |
| 2 Specification | `.agents/<feature>/specification/<revision>_<slug>_spec.md` | Gate passes + user approval |
| 3 Plan | `.agents/<feature>/plans/<revision>_<slug>_plan.md` | Gate passes + user approval |
| 4 Build | Code + verification record | Build gates pass |

### Evidence

Do not assert production readiness without static preview, rendered manifests, or post-deploy checks as required by the feature plan.
