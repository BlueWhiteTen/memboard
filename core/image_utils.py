"""
Image compression helpers, run at upload time (in form clean_* methods) so
that only the compressed version ever touches storage — important now that
storage is billed/limited (R2) and photos come straight from phone cameras.
"""
import io
from PIL import Image, ImageOps
from django.core.files.uploadedfile import InMemoryUploadedFile

# Anything larger than this (on the long edge) gets scaled down. 1920px is
# plenty for a full-bleed board photo or lightbox view on any screen.
MAX_DIMENSION = 1920
JPEG_QUALITY = 82


def compress_image(uploaded_file, max_dimension=MAX_DIMENSION, quality=JPEG_QUALITY):
    """
    Take a Django UploadedFile (from a form's cleaned photo field), resize it
    if needed, and re-encode it as an optimized JPEG (or PNG if the source
    has transparency). Returns a new InMemoryUploadedFile ready to assign
    back onto the field — or the original file untouched if it isn't a
    recognizable image (validation will catch that separately).
    """
    if uploaded_file is None:
        return uploaded_file

    try:
        uploaded_file.seek(0)
        image = Image.open(uploaded_file)
        image.load()
    except Exception:
        # Not a readable image — let normal field validation reject it.
        uploaded_file.seek(0)
        return uploaded_file

    # Respect the camera's orientation tag before we do anything else.
    image = ImageOps.exif_transpose(image)

    has_alpha = image.mode in ('RGBA', 'LA') or (image.mode == 'P' and 'transparency' in image.info)

    if max(image.size) > max_dimension:
        image.thumbnail((max_dimension, max_dimension), Image.LANCZOS)

    buffer = io.BytesIO()
    if has_alpha:
        image = image.convert('RGBA')
        image.save(buffer, format='PNG', optimize=True)
        content_type = 'image/png'
        new_name = _swap_ext(uploaded_file.name, 'png')
    else:
        image = image.convert('RGB')
        image.save(buffer, format='JPEG', quality=quality, optimize=True)
        content_type = 'image/jpeg'
        new_name = _swap_ext(uploaded_file.name, 'jpg')

    buffer.seek(0)
    return InMemoryUploadedFile(
        buffer, None, new_name, content_type, buffer.getbuffer().nbytes, None,
    )


def _swap_ext(filename, new_ext):
    base = (filename or 'upload').rsplit('.', 1)[0]
    return f"{base}.{new_ext}"
