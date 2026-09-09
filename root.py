from fastapi.responses import RedirectResponse
from fastapi import APIRouter, Request
from auth.validation import get_current_user
from fastapi import Depends
from core.core import templates
root_router = APIRouter()


@root_router.get("/")
async def root(user_id=Depends(get_current_user)):
    return RedirectResponse(url="/index.html", status_code=302)