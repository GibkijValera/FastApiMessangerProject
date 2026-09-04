import time
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from databases.databases import get_db, UserModel
from auth.validation import decode_temp_token
from auth.crypto import verify_password, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES, get_password_hash, create_code
from datetime import timedelta, datetime
from redis_manager.redis import redis_manager as r
from core.core import templates


auth_router = APIRouter(prefix="/auth", tags=["auth"])

expire_delta = timedelta(minutes=10)


def mark_nonce_as_used(nonce, ttl_seconds=900):
    r.setex(f"nonce:{nonce}", ttl_seconds, "1")


def is_nonce_used(nonce):
    return r.exists(f"nonce:{nonce}")


@auth_router.get("/register")
async def register_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "title": "Регистрация"})


@auth_router.get("/login")
async def auth_page(request: Request):
    return templates.TemplateResponse("auth.html", {"request": request, "title": "Авторизация"})


class SendCodeSchema(BaseModel):
    email: EmailStr


@auth_router.post("/register/send_code")
async def send_code(schema: SendCodeSchema):
    date = datetime.now()
    code = create_code(schema.email, date)
    print(code)
    return {
        "ok": True,
        "date": date
    }


class CheckCodeSchema(BaseModel):
    email: EmailStr
    date: datetime
    code: int


@auth_router.post("/register/check_code")
async def check_code(schema: CheckCodeSchema):
    if datetime.now() - schema.date > expire_delta:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Code is expired"
        )
    code = create_code(schema.email, schema.date)
    if code != schema.code:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid code"
        )
    else:
        print("kkk")
        temp_token = create_access_token({"email": schema.email})
        return {"ok": True, "token": temp_token}


class RegisterSchema(BaseModel):
    email: EmailStr
    nickname: str = Field(min_length=2, max_length=32)
    name: str = Field(min_length=1, max_length=16)
    lastname: str = Field(min_length=1, max_length=16)
    pwd: str = Field(min_length=8, max_length=32)
    bio: None | str = Field(max_length=255)
    token: str


class NickSchema(BaseModel):
    nickname: str = Field(min_length=2, max_length=32)


@auth_router.post("/register/validate_nick")
async def validate(schema: NickSchema, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(UserModel).where(UserModel.nickname == schema.nickname))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Username is already used"
        )
    return {"ok": True}

@auth_router.post("/register/send_data")
async def register(schema: RegisterSchema, db: AsyncSession = Depends(get_db)):
    email, exp = await decode_temp_token(schema.token)
    if int(datetime.now().timestamp()) > exp:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Registration link is expired, please try again"
        )
    if email != schema.email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )
    result = await db.execute(select(UserModel).where(UserModel.email == schema.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    result = await db.execute(select(UserModel).where(UserModel.nickname == schema.nickname))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Username is already used"
        )
    hashed_pwd = get_password_hash(schema.pwd)
    if schema.bio is None:
        schema.bio = ""
    new_user = UserModel(
        email=schema.email,
        hash_pwd=hashed_pwd,
        name=schema.name,
        lastname=schema.lastname,
        nickname = schema.nickname,
        bio=schema.bio
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return {"ok": True, "user_id": new_user.id}


@auth_router.post("/login")
async def login(response: Response,
        form_data: OAuth2PasswordRequestForm = Depends(),
        db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(UserModel).where(UserModel.email == form_data.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(form_data.password, user.hash_pwd):
        result = await db.execute(select(UserModel).where(UserModel.nickname == form_data.username))
        user = result.scalar_one_or_none()
        if not user or not verify_password(form_data.password, user.hash_pwd):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=False,
        samesite="lax",
        path="/",
        max_age=3600
    )
    return {"access_token": access_token, "token_type": "bearer"}
