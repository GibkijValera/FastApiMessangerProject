from fastapi.responses import RedirectResponse
from fastapi import APIRouter
from auth.validation import get_current_user
from fastapi import Depends
root_router = APIRouter()

@root_router.get("/")
async def root(user_id=Depends(get_current_user)):
    return RedirectResponse(url="/chats", status_code=302)