from fastapi import UploadFile
from tempfile import NamedTemporaryFile
import puremagic
import os
ALLOWED_PICTURE_TYPE = {
    ".jpeg",
    ".png",
    ".webp"
}

FORBIDDEN_CONTENT_TYPE = {
    ".exe"
}


def get_ext(content_type):
    return content_type.split("/")[-1]


MAX_TOTAL_SIZE = 20 * 1024 * 1024
MAX_FILE_SIZE = 5 * 1024 * 1024


async def validate_file_type(file: UploadFile) -> str:
    with NamedTemporaryFile(delete=False) as temp_file:
        content = await file.read(3000)
        temp_file.write(content)
        temp_file.flush()
        temp_file.close()
        detected_extension = puremagic.from_file(temp_file.name)
        os.unlink(temp_file.name)
        return detected_extension

MEDIA_ROOT = "media"