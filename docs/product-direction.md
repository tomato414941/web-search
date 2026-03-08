# Product Direction

## Core Problem Statement

Help AI agents and small teams reach source-grounded public information without getting buried in SEO noise and secondary aggregation.

## What PaleBlueSearch Is

PaleBlueSearch is a quality-focused web search engine for AI agents.

It is not just a search UI. It is a full pipeline that:

- crawls public web content
- extracts and scores content quality signals
- indexes documents and metadata
- serves search results through an API and web interface

The core goal is to return information that an LLM or autonomous agent can use with more confidence than a generic search result page.

## Mission

Deliver trustworthy public information in a form that is fast, simple, and sustainable to operate.

## Vision

Build a search system that helps agents and small teams find clear, source-grounded information without depending on ad-heavy or SEO-distorted discovery surfaces.

## Product Principles

1. Relevance over raw coverage.
   A smaller result set is acceptable if it is cleaner and more useful.

2. Transparency over black-box ranking.
   Results should expose enough signals that users and agents can understand why something ranked well.

3. Primary sources over aggregation.
   When possible, rank original reporting, official docs, and direct evidence above reposts and summaries.

4. Operability over feature count.
   Features that increase maintenance cost without clear search quality gains should be avoided.

5. Reliability over cleverness.
   Fallbacks and safeguards are acceptable when they protect availability, but complexity should not accumulate without a clear reason.

6. Agent usability is a first-class requirement.
   Output shape, metadata, and response quality should help downstream automated consumers, not only humans in a browser.

## Anti-Goals

- Do not try to be a general-purpose web search engine at Google scale.
- Do not optimize for ad-tech, engagement loops, or infinite surface area.
- Do not build complex infrastructure unless it clearly improves quality or reliability.
- Do not over-invest in admin features that do not materially improve search or operations.
- Do not keep compatibility layers, fallback paths, or ranking logic that no longer justify their maintenance cost.

## What This Means In Practice

When deciding whether to add, keep, remove, or deploy something, prefer changes that improve one or more of:

- search quality
- source trustworthiness
- response speed
- operational simplicity
- reliability in production

Be skeptical of changes that mostly add:

- maintenance burden
- hidden coupling
- difficult-to-verify ranking behavior
- operational steps that are easy to forget

## Current Strategic Focus

The current priority is not feature sprawl.

The current priority is to make the existing system:

- trustworthy
- fast enough in production
- easy to operate
- clear about what it ranks and why

New features should be judged against that bar.
