from fastapi.templating import Jinja2Templates
from pathlib import Path as PathLib
TEMPLATES_PATH = PathLib(r"FastApiFront")
templates = Jinja2Templates(directory=str(TEMPLATES_PATH))