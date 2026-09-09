from types import SimpleNamespace

from web_search_frontend.services.search_response import serialize_hit
from web_search_kernel.searcher import SearchHit


def test_serialize_hit_preserves_optional_fields(monkeypatch):
    import web_search_frontend.services.search_response as search_response

    monkeypatch.setattr(
        search_response,
        "generate_snippet",
        lambda content, search_terms: SimpleNamespace(
            text=f"<mark>{search_terms[0]}</mark>",
            plain_text=content,
        ),
    )

    hit = SearchHit(
        url="https://example.com",
        title="Example",
        content="Python content",
        score=1.0,
        page_rank=0.5,
        domain_rank=0.4,
    )

    payload = serialize_hit(hit, ["python"], include_content=True)

    assert payload["snip"] == "<mark>python</mark>"
    assert payload["snip_plain"] == "Python content"
    assert payload["score"] == 1.0
    assert "rank" not in payload
    assert payload["content"] == "Python content"
    assert payload["page_rank"] == 0.5
    assert payload["domain_rank"] == 0.4
