from fastapi import APIRouter, Request
from auth.validation import get_current_user
from fastapi import Depends
from core.core import templates
html_router = APIRouter()


@html_router.get("/index.html")
async def index(request: Request, user_id=Depends(get_current_user)):
    return templates.TemplateResponse("index.html", {"request": request, "title": ""})

@html_router.get("/chats.html")
async def chats(request: Request, user_id=Depends(get_current_user)):
    return templates.TemplateResponse("chats.html", {"request": request, "title": ""})

@html_router.get("/profile.html")
async def chats(request: Request, user_id=Depends(get_current_user)):
    return templates.TemplateResponse("profile.html", {"request": request, "title": ""})


@html_router.get("/settings.html")
async def settings(request: Request, user_id=Depends(get_current_user)):
    return templates.TemplateResponse("settings.html", {"request": request, "title": ""})