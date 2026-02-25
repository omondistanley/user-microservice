"""
Receipt file storage abstraction.
Local backend: filesystem. DB backend uses expense_data_service (file_bytes column).
"""
from abc import ABC, abstractmethod
from pathlib import Path


class ReceiptStorageBackend(ABC):
    @abstractmethod
    def save(self, key: str, content: bytes) -> None:
        pass

    @abstractmethod
    def get(self, key: str) -> bytes:
        pass

    @abstractmethod
    def delete(self, key: str) -> None:
        pass


def _ensure_under_base(base: Path, key: str) -> Path:
    """Resolve path and ensure it is under base (no path traversal)."""
    full = (base / key).resolve()
    base_resolved = base.resolve()
    if not str(full).startswith(str(base_resolved)):
        raise ValueError("Invalid storage key")
    return full


class LocalReceiptStorage(ReceiptStorageBackend):
    def __init__(self, base_path: str | Path):
        self.base = Path(base_path)

    def save(self, key: str, content: bytes) -> None:
        path = _ensure_under_base(self.base, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def get(self, key: str) -> bytes:
        path = _ensure_under_base(self.base, key)
        if not path.exists():
            raise FileNotFoundError(f"Receipt file not found: {key}")
        return path.read_bytes()

    def delete(self, key: str) -> None:
        path = _ensure_under_base(self.base, key)
        if path.exists():
            path.unlink()


# Allowed content types and max size for upload validation
RECEIPT_ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/pdf",
}
RECEIPT_MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB


def ext_from_content_type(content_type: str) -> str:
    m = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "application/pdf": ".pdf",
    }
    return m.get(content_type.split(";")[0].strip().lower(), ".bin")


def sanitize_ext(filename: str) -> str:
    """Extract safe extension from filename (alphanumeric and one dot)."""
    if not filename or "." not in filename:
        return ".bin"
    ext = "." + filename.rsplit(".", 1)[-1].lower()
    if all(c.isalnum() or c == "." for c in ext):
        return ext if len(ext) <= 5 else ".bin"
    return ".bin"
