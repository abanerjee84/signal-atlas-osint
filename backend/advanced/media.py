import asyncio
import hashlib
import io
import struct
import warnings
from pathlib import Path

from fastapi import HTTPException
from PIL import ExifTags, Image, UnidentifiedImageError

from ..models import Report, stamp
from .repository import identifier

Image.MAX_IMAGE_PIXELS = 20_000_000


def inspect(payload, content_type):
    mime = content_type.split(";")[0].lower()
    if mime in {"image/png", "image/jpeg"}:
        expected = "PNG" if mime == "image/png" else "JPEG"
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(payload)) as image:
                    if image.format != expected or image.width * image.height > 20_000_000:
                        raise ValueError("Image signature or pixel bounds invalid")
                    dimensions = {"width": image.width, "height": image.height, "format": image.format}
                    exif = {str(ExifTags.TAGS.get(k, k)): str(v)[:500] for k, v in image.getexif().items()}
                with Image.open(io.BytesIO(payload)) as validation_image:
                    validation_image.verify()
            return {
                **dimensions,
                "exif": exif,
                "metadata_authenticity": "unverified",
                "c2pa": {"status": "unsupported", "reason": "No Content Credentials verifier configured"},
            }
        except (
            ValueError,
            OSError,
            UnidentifiedImageError,
            Image.DecompressionBombWarning,
            Image.DecompressionBombError,
        ) as error:
            raise HTTPException(
                422, "Invalid image, unsupported signature or pixel limit exceeded"
            ) from error
    if mime == "video/mp4":
        # Inspect ISO BMFF framing without executing a codec or untrusted external utility.
        if len(payload) < 16 or payload[4:8] != b"ftyp":
            raise HTTPException(422, "MP4 signature missing")
        position, boxes = 0, []
        while position + 8 <= len(payload) and len(boxes) < 100:
            size, kind = struct.unpack_from(">I4s", payload, position)
            header = 8
            if size == 1:
                if position + 16 > len(payload):
                    raise HTTPException(422, "Truncated MP4 framing")
                size, header = struct.unpack_from(">Q", payload, position + 8)[0], 16
            if size == 0:
                size = len(payload) - position
            if size < header or position + size > len(payload):
                raise HTTPException(422, "Invalid MP4 box bounds")
            boxes.append({"type": kind.decode("ascii", errors="replace"), "bytes": size})
            position += size
        if position != len(payload):
            raise HTTPException(422, "MP4 exceeds box inspection limits or has invalid trailing bytes")
        return {
            "format": "MP4",
            "boxes": boxes,
            "major_brand": payload[8:12].decode("ascii", errors="replace"),
            "metadata_authenticity": "unverified",
            "c2pa": {"status": "unsupported"},
            "limitations": "Container framing inspected; no video decode or authenticity conclusion.",
        }
    raise HTTPException(415, "Supported media: PNG, JPEG and MP4")


async def upload(request, repo, settings, filename, original_url):
    if original_url:
        try:
            original_url = Report.safe_url(original_url)
        except ValueError:
            raise HTTPException(422, "Invalid original source URL") from None
    if (
        len(filename) > 200
        or Path(filename).name != filename
        or any(x in filename for x in ["/", "\\", "\x00"])
    ):
        raise HTTPException(422, "Use a filename without directories")
    payload = bytearray()
    try:
        async with asyncio.timeout(60):
            async for chunk in request.stream():
                if len(payload) + len(chunk) > settings.media_max_bytes:
                    raise HTTPException(413, "Media upload exceeds configured limit")
                payload.extend(chunk)
    except TimeoutError:
        raise HTTPException(408, "Upload timed out") from None
    content_type = request.headers.get("content-type", "")
    metadata = await asyncio.to_thread(inspect, payload, content_type)
    media_id = identifier()
    settings.evidence_directory.mkdir(parents=True, exist_ok=True)
    target = settings.evidence_directory / (media_id + ".bin")
    target.write_bytes(payload)
    try:
        result = repo.insert(
            "media_evidence",
            {
                "id": media_id,
                "filename": filename,
                "mime": content_type.split(";")[0],
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "original_url": original_url or None,
                "uploaded_at": stamp(),
                "metadata": metadata,
            },
        )
        repo.audit("media.upload", media_id, {"bytes": len(payload), "sha256": result["sha256"]})
        return result
    except Exception:
        target.unlink(missing_ok=True)
        raise
