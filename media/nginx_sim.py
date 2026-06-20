from fastapi import Path, APIRouter
from fastapi.responses import FileResponse
from media.MediaInfo import MEDIA_ROOT
from pathlib import Path as PathLib
from media.pictures import ALLOWED_PICTURE_TYPE
media_router = APIRouter()


@media_router.get("/media/{filepath:path}")
async def serve_media(filepath: str):
    return FileResponse(path=PathLib(MEDIA_ROOT) / filepath,
                        media_type=ALLOWED_PICTURE_TYPE,
                        headers={"Content-Disposition": f'inline; filename="smth.webp"'})