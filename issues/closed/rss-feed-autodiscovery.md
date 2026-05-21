# RSS Feed Autodiscovery

## Status

Closed. HTML parsing now extracts standard RSS/Atom alternate links and admits
them through the normal URL discovery and frontier path.

## Problem

The crawler does not clearly support standard RSS/Atom autodiscovery from HTML
pages.

Today, HTML parsing admits normal anchor outlinks. Standard feed discovery is
usually expressed through `<link rel="alternate" type="application/rss+xml">`
or Atom equivalents, not through visible `<a href>` links.

## Evidence

`parse_page()` extracts links from `<a>` tags and returns them as outlinks.
There is no separate feed discovery output for alternate RSS/Atom links.

This means a feed can be discovered if the site exposes it as a normal anchor,
but not reliably through the conventional feed autodiscovery mechanism.

## Impact

Sites with useful feeds may be missed even when their HTML advertises those
feeds in a standard machine-readable way.

This is especially relevant for sources where article HTML is difficult to
fetch, but RSS/Atom feeds remain fetchable.

## Direction

Add explicit RSS/Atom alternate-link discovery to HTML parsing and admit those
feed URLs through the normal URL discovery path.

Keep feed URLs as normal discovered URLs. Do not create a separate RSS-only URL
ledger unless feed-specific state becomes necessary.

## Resolution

`parse_page()` now returns RSS/Atom alternate links separately from normal
outlinks.

The crawler admits those feed URLs with
`discovered_via="feed_autodiscovery"`.

The URL admission rules no longer reject `.rss`, `.atom`, `/rss`, or `/feed`
URLs globally.
