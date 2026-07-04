
# 1. Record architecture decisions

**Status:** Accepted

## Context
PlanTrack is moving from a single-file HTML/JavaScript prototype to a production APS
product. A number of foundational technology choices are being made early. These
decisions are expensive to reverse and their rationale is easy to lose as the team grows.

## Decision
We will record each significant architecture decision as a short Markdown file in
`docs/adr/`, using the Context → Decision → Consequences format, numbered sequentially.
A decision is changed not by editing history but by adding a new ADR that supersedes the
old one.

## Consequences
- New contributors can read the ADRs to understand why the system is shaped as it is.
- Decisions are revisited deliberately rather than drifting.
- A small ongoing discipline: meaningful choices should come with an ADR.
