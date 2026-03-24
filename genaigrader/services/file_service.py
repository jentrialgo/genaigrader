from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.utils.text import get_valid_filename


def save_uploaded_file(uploaded_file):
    upload_dir = Path(settings.MEDIA_ROOT)
    upload_dir.mkdir(parents=True, exist_ok=True)

    original_name = Path(uploaded_file.name).name
    safe_name = get_valid_filename(original_name) if original_name else "upload.txt"
    if not safe_name:
        safe_name = f"upload-{uuid4().hex}.txt"

    file_path = upload_dir / safe_name
    if file_path.exists():
        file_path = upload_dir / f"{file_path.stem}-{uuid4().hex[:8]}{file_path.suffix}"

    with open(file_path, "wb") as f:
        for chunk in uploaded_file.chunks():
            f.write(chunk)
    return str(file_path)
