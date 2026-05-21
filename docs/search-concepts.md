# Search Concepts

## Status

Current conceptual reference.

This document defines the core concepts used to reason about search in
PaleBlueSearch. It sits one layer above specific ranking policy or evaluation
rules.

## Core View

Search is the process of finding, ranking, and presenting targets that best
align with the user's current intent.

The query is an observable input.
Intent is the deeper concept the system is trying to approximate.

## Concept Groups

### User-Side Concepts

#### Query

`Query` is the observable input provided to the system.

It is evidence about intent, not intent itself.

#### Intent

`Intent` is the direction of the user's current search action.

Intent is a user-side concept.
The system does not observe it directly. It infers it from available evidence
such as query text and surrounding context.

#### Purpose

`Purpose` is the broader user-side outcome behind a search session.

It matters, but it is usually less immediate and less observable than intent.
For most search behavior in this repository, `intent` is the primary concept.

### Corpus Concepts

#### Target

`Target` is something that can potentially be presented to the user.

Targets exist before any specific query or intent is applied.

#### Target Representation

`Target representation` is the system's internal representation of a target.

It may include text, metadata, learned features, or derived features.
The target is the thing in the world. The target representation is how the
system reasons about it.

### Process Concepts

#### Retrieval

`Retrieval` is the process of collecting candidate targets for a query and
inferred intent.

Retrieval defines what later ranking stages can work with.

#### Candidate Set

`Candidate set` is the set of targets returned by retrieval for further
evaluation.

Ranking can only order candidates that exist in this set.

#### Scoring

`Scoring` is the process of evaluating candidates using signals.

Scoring may produce explicit numeric values, ordered categories, or other
comparable evidence used by ranking.

#### Ranking

`Ranking` is the process of ordering candidates for presentation.

Ranking uses scores and policy to decide which targets should appear before
others.

#### Reranking

`Reranking` is a later ranking pass over an already retrieved or initially
ranked candidate set.

Reranking can improve order, but it cannot recover targets that retrieval did
not include.

#### Presentation

`Presentation` is the act of showing ranked targets to the user or downstream
consumer.

Presentation includes result formatting, snippets, metadata exposure, and other
output choices. It is distinct from retrieval and ranking.

### Decision Concepts

#### Signal

`Signal` is any input used to estimate how well a target aligns with the user's
intent.

Signals are not the essence of search. They are ingredients used to approximate
intent-target alignment.

#### Policy

`Policy` is the explicit rule layer that decides how signals should be used.

Policy is not the same thing as a signal. It is the rule layer that decides how
signals matter.

## Search Process

Search should be understood as a multi-stage process:

1. observe the query
2. infer intent from available context
3. retrieve candidate targets
4. score candidates using signals
5. rank candidates under explicit policy
6. present ranked targets

These stages are related, but they are not interchangeable.

## Key Principles

### Retrieval Failure Cannot Be Fixed By Ranking

If the intended target is absent from the candidate set, ranking cannot recover
it.

That is a retrieval or coverage failure, not a scoring failure.

### Scoring And Ranking Are Related But Distinct

Scoring evaluates candidates.
Ranking orders candidates.

A ranking system may use scores, rules, or both, but those responsibilities
should stay conceptually separate.

### Signals Should Be Independent And Explainable

Signals should represent distinct evidence where possible.

Large ambiguous aggregates make it harder to understand, tune, or remove a
ranking behavior.

### Policy Should Combine Signals Explicitly

Policy should make the use of signals visible.

Hidden coupling between retrieval, scoring, and ranking makes quality failures
harder to diagnose.

## Explicit Signals and Vector Methods

Vector-based retrieval fits naturally into this framework.

It is one way to estimate intent-target alignment. It is not the definition of
search itself.

The same is true for explicit methods such as lexical retrieval, link-based
priors, freshness, and source-aware policy. These should be treated as
interoperable parts of one system, not as mutually exclusive worldviews.

For this repository, explicit signals remain important because they provide:

- control
- operational simplicity
- explanation
- easier tuning and removal

Vector-based methods may still be valuable, but they should be introduced as
complements rather than as the sole conceptual foundation.

## Implications For This Repository

The search stack should prefer:

- a clear target model
- a small set of explicit signals with well-defined meaning
- an explicit policy layer
- retrieval methods that can evolve without redefining the whole system
- ranking behavior that is explainable enough for operators and downstream
  agents

This implies a preference for:

- keeping signal definitions independent
- combining signals through explicit policy rather than hidden coupling
- making it easy to add, remove, or tune signals
- avoiding large ambiguous aggregate values when the underlying components have
  different meanings

## Relationship To Other Documents

- [search-ranking-policy.md](./search-ranking-policy.md): current ranking rules
- [search-evaluation.md](./search-evaluation.md): current evaluation workflow
- [search-signals.md](./search-signals.md): current document-signal strategy

This document defines the conceptual layer used to discuss those documents
consistently.
