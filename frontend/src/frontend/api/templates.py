import os
from fastapi.templating import Jinja2Templates

TEMPLATE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates"
)

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
