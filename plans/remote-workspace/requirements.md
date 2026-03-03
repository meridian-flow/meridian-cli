# Remote Workspace Integration Requirements (Draft)

## Document Status
- Status: Draft
- Date: 2026-03-01
- Goal: Define requirements only for integrating a web workspace viewer into Meridian workflows.
- Non-goal: No implementation design, no framework selection, no migration steps.
- Implementation state (2026-03-03): requirements-only; no production implementation tracked in `src/` yet.

## Scope
This document defines:
- Bare requirements (minimum outcomes)
- Functional requirements (user-visible behaviors)
- Non-functional requirements (security, reliability, maintainability, performance, UX quality)
- Refactor vs rewrite decision gate

This document does not define:
- API endpoint shape
- CLI flag contract
- Frontend component architecture
- Rollout plan

## Bare Requirements
- `BR-01` Access mode must be explicit: local-only, tailnet-only, or internet-exposed with password protection.
- `BR-02` Users must be able to upload images into repository-managed storage.
- `BR-03` Users must be able to create copy-ready mention snippets for uploaded assets.
- `BR-04` Users must be able to browse repository files in a readable interface.
- `BR-05` Markdown content must be rendered as first-class content.
- `BR-06` Mermaid diagrams inside markdown must be rendered and reviewable.
- `BR-07` Meridian plan files must be easy to discover and review.
- `BR-08` Desktop and mobile must have intentionally different interaction models.
- `BR-09` Viewer functionality must be launchable from Meridian CLI workflows.

## Functional Requirements

### Navigation and Shells
- `FR-01` Desktop UI must not use a bottom tab bar.
- `FR-02` Desktop UI must provide persistent navigation for core areas (plans, project, assets).
- `FR-03` Mobile UI must provide top-level mode switching and full-screen detail views.
- `FR-04` Mobile and desktop shells must be independently controllable without shared layout constraints forcing parity.

### Project and File Viewing
- `FR-05` File explorer must support directory expansion, file open, and search.
- `FR-06` Viewer must support text preview, markdown rendering, image preview, and binary fallback.
- `FR-07` Markdown viewer must render Mermaid diagrams and allow diagram inspection (zoom/fullscreen/lightbox equivalent).
- `FR-08` Plan-focused view must prioritize plan/task markdown files over generic file listing.

### Asset Workflow
- `FR-09` Image upload must support local file picker.
- `FR-10` Image upload must support clipboard paste where browser permissions allow.
- `FR-11` Uploaded assets must support preview, delete, and copy-reference actions.
- `FR-12` Mention helper must support at least:
  - markdown image embed snippet
  - meridian-friendly reference snippet

### Integration and Runtime
- `FR-13` Viewer launch status must be visible (running, failed, stopped) through Meridian CLI output.
- `FR-14` Auth/protection mode must be visible to the operator at launch time.
- `FR-15` Viewer failure must not silently fail; user-visible error is required.

## Non-Functional Requirements

### Security
- `NFR-01` Mutating operations must enforce CSRF/origin protections regardless of whether password auth is enabled.
- `NFR-02` Password handling must avoid accidental exposure in shell history/process list by default.
- `NFR-03` Hidden and excluded repository paths must remain non-readable unless explicitly allowed.
- `NFR-04` Brute-force protections must not rely on untrusted client-provided IP headers.

### Reliability
- `NFR-05` Launch behavior must be deterministic with clear exit semantics for parent and child processes.
- `NFR-06` Upload/list/delete behavior must be resilient to retries and partial failures.
- `NFR-07` File preview failures must degrade gracefully with actionable messages.

### Performance
- `NFR-08` Initial UI load must remain responsive for typical repository sizes.
- `NFR-09` Markdown and Mermaid rendering must avoid blocking the UI for common plan file sizes.
- `NFR-10` Search and tree browsing must remain usable under large file trees with bounded work per interaction.

### Maintainability and Testability
- `NFR-11` Core flows (browse, markdown/mermaid, upload, mention) must be modular and separable.
- `NFR-12` No single "god file" should orchestrate all state, rendering, and network logic.
- `NFR-13` Desktop/mobile shell changes must not require invasive backend changes.
- `NFR-14` Core workflows must be covered by automated tests at behavior level.

### UX Quality and Accessibility
- `NFR-15` Desktop and mobile experiences must optimize for their form factor instead of sharing one compromised navigation model.
- `NFR-16` Keyboard navigation and focus visibility must be supported for primary actions.
- `NFR-17` Text and UI controls must maintain adequate contrast in supported themes.

## Refactor vs Rewrite Decision Gate
Use this gate after current-state assessment and before implementation planning.

Choose **rewrite** if at least 3 conditions are true:
- More than 50% of UI surfaces/components need replacement.
- Current state/routing architecture cannot cleanly support independent desktop and mobile shells.
- Security hardening requires deep backend contract changes across most endpoints.
- Plan-centric IA cannot be introduced without heavy coupling debt.
- Estimated refactor effort is within 20% of rewrite effort.

Otherwise choose targeted **refactor**.

## Open Questions (To Resolve Before Implementation Plan)
- `Q-01` Should viewer runtime be Node-based, Python-based, or dual-mode during transition?
- `Q-02` Should viewer launch be a dedicated command only, or also a sidecar option during space lifecycle commands?
- `Q-03` What is the minimum viable mention snippet set for Meridian workflows?
- `Q-04` What repository scale should be treated as "typical" for performance acceptance?
