import uvicorn
from fastapi import FastAPI, Depends, Request
from fastapi.responses import RedirectResponse
from contextlib import asynccontextmanager
from users.users import users_router
from chats.chats import chats_router
from auth.auth import auth_router
from auth.validation import RedirectException
from friends.friends import friends_router
from media.nginx_sim import media_router
from redis_manager.redis import redis_manager
from root import root_router
from websocket.ws import ws_router
@asynccontextmanager
async def lifespan(app: FastAPI()):
    await redis_manager.connect()
    yield
    await redis_manager.disconnect()


app = FastAPI(lifespan=lifespan)
app.include_router(users_router)
app.include_router(chats_router)
app.include_router(auth_router)
app.include_router(friends_router)
app.include_router(media_router)
app.include_router(root_router)
app.include_router(ws_router)

@app.exception_handler(RedirectException)
async def redirect_to_auth_handler(request: Request, exc: RedirectException):
    return RedirectResponse(url=exc.url, status_code=302)

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
