# Documentation Guide

This directory contains current runtime documentation plus explicitly marked
design notes. Use this file as the entry point.

## Current Product and Runtime

- [architecture.md](./architecture.md): current system architecture, service boundaries, and crawler runtime state model
- [crawler-concepts.md](./crawler-concepts.md): conceptual vocabulary for crawler responsibilities, hot paths, and state boundaries
- [api.md](./api.md): current API surface across frontend, crawler, and indexer
- [setup.md](./setup.md): local development and environment setup
- [deployment.md](./deployment.md): deployment topology, CI/CD model, and release workflow

## Current Search Behavior

- [search-concepts.md](./search-concepts.md): conceptual vocabulary for intent, targets, retrieval, scoring, ranking, signals, and presentation
- [search-ranking-policy.md](./search-ranking-policy.md): current ranking policy and query classes
- [search-evaluation.md](./search-evaluation.md): golden-set policy, tiering, and evaluation workflow
- [search-signals.md](./search-signals.md): current extraction and document-signal strategy

## Operational Notes

- [deployment.md](./deployment.md): deployment topology, CI/CD model, release workflow, and recovery procedures

## Where To Start

- Current engineering tasks: start with [`../issues/`](../issues/)
- Runtime or service-boundary questions: start with [architecture.md](./architecture.md)
- Local development or startup flow: start with [setup.md](./setup.md)
- Release or production questions: start with [deployment.md](./deployment.md)
- Search-concept or terminology questions: start with [search-concepts.md](./search-concepts.md)
- Ranking or result-quality questions: start with [search-concepts.md](./search-concepts.md), [search-ranking-policy.md](./search-ranking-policy.md), and [search-evaluation.md](./search-evaluation.md)

## Source of Truth Rules

- Runtime behavior wins over older design notes.
- Config-driven search behavior lives in [`config/canonical_sources.json`](../config/canonical_sources.json) and [`config/search_eval_cases.json`](../config/search_eval_cases.json).
- If a document describes future work, it should say so explicitly near the top.
