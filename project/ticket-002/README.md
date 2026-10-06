# Ticket 002: Persist scanner ingress and verified Lenovo intake deployment

- **ID**: ticket-002
- **Owner**: tom
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION
- **Created**: 2026-10-06

## Goal and scope

SESSION_EXECUTION_AUTHORIZATION: user requested scanner repair using existing ingress,
Lenovo scan-* intake, then "kontynuuj, scalaj". Preserve the deployed host configuration
as scanner-owned infrastructure source and tests under infra/scanner/**. Agent: codex.

## Acceptance criteria

- [x] AC-01: Existing Caddy ingress scripts, backend and delivery user units have reproducible source.
- [x] AC-02: Delivery verifies PDF/JSON read-back before .ready, preserves page rendering and metadata, retries without overwriting foreign files.
- [x] AC-03: Scoped tests and governance gate pass.
- [ ] AC-04: Independent OneDev/Validator publication observes the exact source head.

## Publication prerequisite

Protected preflight currently reports PUBLICATION_PROFILE_MISSING for this repository.
User publication authorization permits the trusted controller route, never direct merge.
The native allocator reserved 002 but index generation found missing marker pair;
repair the target-owned tracking index within this ticket's admitted tracking scope.
Runtime files, documents and foreign application/connector source remain preserved.
