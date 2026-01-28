import uvicorn
from fastapi import FastAPI

from messages.messages import messages_router
from users.users import users_router
from chats.chats import chats_router
from auth.auth import auth_router


app = FastAPI()
app.include_router(messages_router)
app.include_router(users_router)
app.include_router(chats_router)
app.include_router(auth_router)

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
