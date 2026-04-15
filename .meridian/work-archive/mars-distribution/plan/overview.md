# Implementation Plan — Mars Distribution

All work happens in the `mars-agents` repo (`../mars-agents/`).

## Phase Ordering

```
Phase 1: npm package scaffolding     (foundation — all other phases need this)
Phase 2: release workflow             (needs phase 1 files to exist)
Phase 3: smoke test                   (validates phases 1+2 end-to-end)
```

Phases are sequential — each depends on the prior.

## Phases

### Phase 1: npm Package Scaffolding

Create the `npm/` directory structure with all package.json files and the bin shim.

**Blueprint**: [phase-1-npm-scaffolding.md](phase-1-npm-scaffolding.md)

### Phase 2: Release Workflow

Create `.github/workflows/release.yml` — the complete CI pipeline from tag push to published artifacts.

**Blueprint**: [phase-2-release-workflow.md](phase-2-release-workflow.md)

### Phase 3: Smoke Test

Validate the setup locally: verify package.json files are valid, shim script has correct syntax, workflow YAML parses correctly. Document manual verification steps for the first real release.

**Blueprint**: [phase-3-smoke-test.md](phase-3-smoke-test.md)

## Setup Steps (Before Implementation)

These are manual one-time steps the repo owner needs to do:

1. **Create `@mars-agents` npm org** — `npm org create mars-agents` or via npmjs.com
2. **Create npm automation token** — npmjs.com → Access Tokens → Granular Token with publish to `@mars-agents/*`
3. **Add `NPM_TOKEN` repo secret** — GitHub → mars-agents → Settings → Secrets → Actions
4. **Verify GitHub Actions permissions** — Settings → Actions → General → Workflow permissions → Read and write

These are documented but not automated — they require human credentials and org ownership decisions.
