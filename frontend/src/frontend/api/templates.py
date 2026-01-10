import os
from fastapi.templating import Jinja2Templates
from frontend.core.config import settings

# Templates are at src/web_search/templates
# This file is at src/web_search/api/templates.py -> parent.parent / templates
TEMPLATE_DIR = settings.BASE_DIR / "src" / "web_search" / "templates"
# Wait, BASE_DIR in config.py is project root.
# src/web_search/templates
TEMPLATE_DIR = settings.BASE_DIR / "src" / "web_search" / "templates"

# Fallback checking
if not os.path.exists(TEMPLATE_DIR):
    # Try relative path from this file
    TEMPLATE_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates"
    )

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
