import os
from django.conf import settings
from PIL import Image
from account.serializers import ImageUploadForm, FileUploadForm
from utils.shortcuts import rand_str
from utils.api import APIView
import logging

logger = logging.getLogger(__name__)

# Pillow format name -> stored suffix. The content decides the format, never the file name.
IMAGE_SUFFIXES = {"GIF": ".gif", "JPEG": ".jpg", "PNG": ".png", "BMP": ".bmp", "WEBP": ".webp"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024


class ImageUploadError(Exception):
    pass


def save_uploaded_image(request):
    """Store the request's "image" file under the public upload directory and return its URL path."""
    form = ImageUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        raise ImageUploadError("Upload failed")
    img = form.cleaned_data["image"]
    if img.size > MAX_IMAGE_BYTES:
        raise ImageUploadError("Image is larger than 10 MB")
    try:
        with Image.open(img) as picture:
            image_format = picture.format
            picture.verify()
    except Exception:
        raise ImageUploadError("Unsupported file format")
    suffix = IMAGE_SUFFIXES.get(image_format)
    if suffix is None:
        raise ImageUploadError("Unsupported file format")
    img.seek(0)
    img_name = rand_str(10) + suffix
    try:
        with open(os.path.join(settings.UPLOAD_DIR, img_name), "wb") as img_file:
            for chunk in img.chunks():
                img_file.write(chunk)
            os.fchmod(img_file.fileno(), 0o644)
    except IOError as e:
        logger.error(e)
        raise ImageUploadError("Upload Error")
    return f"{settings.UPLOAD_PREFIX}/{img_name}"


class SimditorImageUploadAPIView(APIView):
    request_parsers = ()

    def post(self, request):
        try:
            file_path = save_uploaded_image(request)
        except ImageUploadError as e:
            return self.response({"success": False, "msg": str(e), "file_path": ""})
        return self.response({"success": True, "msg": "Success", "file_path": file_path})


class SimditorFileUploadAPIView(APIView):
    request_parsers = ()

    def post(self, request):
        form = FileUploadForm(request.POST, request.FILES)
        if form.is_valid():
            file = form.cleaned_data["file"]
        else:
            return self.response({
                "success": False,
                "msg": "Upload failed"
            })

        suffix = os.path.splitext(file.name)[-1].lower()
        file_name = rand_str(10) + suffix
        try:
            with open(os.path.join(settings.UPLOAD_DIR, file_name), "wb") as f:
                for chunk in file:
                    f.write(chunk)
                os.fchmod(f.fileno(), 0o644)
        except IOError as e:
            logger.error(e)
            return self.response({
                "success": False,
                "msg": "Upload Error"})
        return self.response({
            "success": True,
            "msg": "Success",
            "file_path": f"{settings.UPLOAD_PREFIX}/{file_name}",
            "file_name": file.name})
