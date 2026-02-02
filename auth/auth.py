from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from databases.databases import get_db, UserModel
from auth.crypto import verify_password, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES, get_password_hash
from datetime import timedelta

auth_router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterSchema(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=32)
    lastname: str = Field(min_length=1, max_length=32)
    pwd: str = Field(min_length=8, max_length=32)
    bio: None | str = Field(max_length=255)


@auth_router.post("/register")
async def register(schema: RegisterSchema, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(UserModel).where(UserModel.email == schema.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    hashed_pwd = get_password_hash(schema.pwd)
    new_user = UserModel(
        email=schema.email,
        hash_pwd=hashed_pwd,
        name=schema.name,
        lastname=schema.lastname,
        bio=schema.bio
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return {"ok": True, "user_id": new_user.id}


@auth_router.post("/login")
async def login(
        form_data: OAuth2PasswordRequestForm = Depends(),
        db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(UserModel).where(UserModel.email == form_data.username))
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
    return {"access_token": access_token, "token_type": "bearer"}
