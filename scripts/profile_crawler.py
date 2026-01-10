"""
Crawler Performance Profiler

Tests each stage of the crawler to identify bottlenecks.
"""

import time
import requests
from web_search.crawler.parser import html_to_doc, extract_links

# Test URLs - try different sizes
TEST_URLS = [
    ("Small", "https://example.com"),
    ("Medium EN", "https://en.wikipedia.org/wiki/Python_(programming_language)"),
    ("Large EN", "https://en.wikipedia.org/wiki/Japan"),
    (
        "Japanese",
        "https://ja.wikipedia.org/wiki/%E3%83%A1%E3%82%A4%E3%83%B3%E3%83%9A%E3%83%BC%E3%82%B8",
    ),
]


def profile_stage(name, func, *args):
    """Profile a single stage."""
    start = time.time()
    result = func(*args)
    elapsed = time.time() - start
    print(f"[{name}] {elapsed:.3f}s")
    return result, elapsed


def main():
    print("Crawler Performance Profiler")
    print("=" * 50)

    for name, url in TEST_URLS:
        print(f"\n{'=' * 50}")
        print(f"Testing: {name} - {url}")
        print("=" * 50)

        test_url(url)


def test_url(TEST_URL):
    total_times = {}

    # Stage 1: Download HTML
    print("\n1. Downloading HTML...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    resp, t1 = profile_stage(
        "Download", lambda: requests.get(TEST_URL, timeout=10, headers=headers)
    )
    total_times["download"] = t1
    html = resp.text
    print(f"   Downloaded {len(html):,} bytes")

    # Stage 2: Parse HTML (html_to_doc)
    print("\n2. Parsing HTML (html_to_doc)...")
    result, t2 = profile_stage("html_to_doc", html_to_doc, html)
    total_times["html_to_doc"] = t2
    if result:
        title, content = result
        print(f"   Title: {title[:50]}")
        print(f"   Content: {len(content):,} chars")

    # Stage 3: Extract Links
    print("\n3. Extracting Links...")
    links, t3 = profile_stage("extract_links", extract_links, html, TEST_URL)
    total_times["extract_links"] = t3
    print(f"   Found {len(links)} links")

    # Summary
    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    total = sum(total_times.values())

    for stage, elapsed in sorted(total_times.items(), key=lambda x: -x[1]):
        pct = (elapsed / total) * 100
        print(f"{stage:20s}: {elapsed:6.3f}s ({pct:5.1f}%)")

    print(f"{'TOTAL':20s}: {total:6.3f}s")


if __name__ == "__main__":
    main()
