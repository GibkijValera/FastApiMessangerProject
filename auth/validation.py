from fastapi import HTTPException, status, Request, WebSocket
from typing import Optional
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from auth.crypto import SECRET_KEY, ALGORITHM
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


class RedirectException(Exception):
    def __init__(self, url="/auth/login"):
        self.url = url


async def decode_temp_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("email")
        date = payload.get("exp")
        print(email, date)
        if email is None or date is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
        return email, date
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )


async def validate_jwt_token(token: str) -> int:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is missing",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )
        return int(user_id)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )


def extract_token_from_request(request: Request) -> Optional[str]:
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]

    return token


def extract_token_from_ws(websocket: WebSocket) -> Optional[str]:
    cookie_header = websocket.headers.get("cookie", "")
    if not cookie_header:
        return None
    import http.cookies
    cookies = http.cookies.SimpleCookie(cookie_header)
    token_cookie = cookies.get("access_token")

    return token_cookie.value if token_cookie else None


async def get_current_user(request: Request) -> int:
    token = extract_token_from_request(request)

    if not token:
        raise RedirectException(url="/auth/login")

    try:
        return await validate_jwt_token(token)
    except HTTPException:
        raise RedirectException(url="/auth/login")


async def get_current_user_ws(websocket: WebSocket) -> Optional[int]:
    token = extract_token_from_ws(websocket)
    if not token:
        return None

    try:
        return await validate_jwt_token(token)
    except HTTPException:
        return None
