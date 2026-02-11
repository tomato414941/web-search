"""Vector search cache tests - skipped while hybrid search is disabled."""

import pytest

pytestmark = pytest.mark.skip(reason="Vector/hybrid search disabled for performance")
