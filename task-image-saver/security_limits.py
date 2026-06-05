"""
ZIP 展開（Zip Slip 対策）と画像読み込みのサイズ上限。

- 画像1ファイルあたり最大 10 GiB（圧縮前の ZIP メンバー / 展開後ファイル / デコード見積り）
- テキスト系 ZIP メンバー（info.txt 等）は 16 MiB
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from PIL import Image

MAX_IMAGE_BYTES = 10 * 1024 * 1024 * 1024
MAX_ZIP_TEXT_BYTES = 16 * 1024 * 1024
_MAX_RGB_PIXELS = MAX_IMAGE_BYTES // 3

_pillow_configured = False


class SecurityLimitError(Exception):
    """セキュリティ制限違反。"""


class ZipPathSecurityError(SecurityLimitError):
    """ZIP 内パスが展開先外へ脱出する場合。"""


class ZipMemberSizeError(SecurityLimitError):
    """ZIP メンバーまたは読み込みストリームがサイズ上限を超える場合。"""


class ImageSizeError(SecurityLimitError):
    """画像ファイルまたはデコード後サイズが上限を超える場合。"""


def configure_pillow_limits() -> None:
    """Pillow の DecompressionBomb 上限を 10 GiB 相当のピクセル数に設定する。"""
    global _pillow_configured
    Image.MAX_IMAGE_PIXELS = _MAX_RGB_PIXELS
    _pillow_configured = True


def _ensure_pillow_configured() -> None:
    if not _pillow_configured:
        configure_pillow_limits()


def _normalize_zip_member_path(name: str) -> str:
    return name.replace("\\", "/")


def is_safe_zip_member_path(member_name: str, dest_dir: Path) -> bool:
    """ZIP メンバーが dest_dir 配下にのみ展開されるか判定する。"""
    normalized = _normalize_zip_member_path(member_name).rstrip("/")
    if not normalized:
        return True
    if normalized.startswith("/") or normalized.startswith("\\"):
        return False
    first_part = normalized.split("/", 1)[0]
    if ":" in first_part:
        return False

    pure = PurePosixPath(normalized)
    if pure.is_absolute() or ".." in pure.parts:
        return False

    dest = dest_dir.resolve()
    target = (dest / Path(*pure.parts)).resolve()
    try:
        target.relative_to(dest)
    except ValueError:
        return False
    return True


def check_zip_member_size(
    info: zipfile.ZipInfo,
    max_bytes: int = MAX_IMAGE_BYTES,
) -> None:
    """ZIP ヘッダ上の file_size が上限を超える場合は拒否する。"""
    size = info.file_size
    if size < 0:
        return
    if size > max_bytes:
        raise ZipMemberSizeError(
            f"ZIPメンバーが上限を超えています: {info.filename} "
            f"({size} bytes > {max_bytes} bytes)"
        )


def read_stream_bounded(stream: BinaryIO, max_bytes: int) -> bytes:
    """ストリームを読み、max_bytes を超えたら ZipMemberSizeError。"""
    chunks: list[bytes] = []
    total = 0
    block = 1024 * 1024
    while True:
        chunk = stream.read(block)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise ZipMemberSizeError(
                f"読み込み上限を超えました ({total} > {max_bytes} bytes)"
            )
        chunks.append(chunk)
    return b"".join(chunks)


def read_zip_member(
    zip_ref: zipfile.ZipFile,
    member_name: str,
    *,
    max_bytes: int = MAX_IMAGE_BYTES,
) -> bytes:
    """ZIP メンバーを上限付きで読み込む。"""
    info = zip_ref.getinfo(member_name)
    check_zip_member_size(info, max_bytes)
    with zip_ref.open(info) as member_stream:
        return read_stream_bounded(member_stream, max_bytes)


def safe_zip_extractall(
    zip_ref: zipfile.ZipFile,
    output_folder: str | Path,
    *,
    max_member_bytes: int = MAX_IMAGE_BYTES,
) -> None:
    """Zip Slip と巨大メンバーを拒否しながら ZIP を展開する。"""
    dest = Path(output_folder).resolve()
    dest.mkdir(parents=True, exist_ok=True)

    for info in zip_ref.infolist():
        if not is_safe_zip_member_path(info.filename, dest):
            raise ZipPathSecurityError(
                f"安全でないZIPパスです: {info.filename}"
            )

        normalized = _normalize_zip_member_path(info.filename)
        is_directory = normalized.endswith("/") or info.is_dir()

        if not is_directory:
            check_zip_member_size(info, max_member_bytes)

        rel = PurePosixPath(normalized.rstrip("/"))
        if not rel.parts:
            continue
        target = (dest / Path(*rel.parts)).resolve()

        if is_directory:
            target.mkdir(parents=True, exist_ok=True)
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        with zip_ref.open(info) as src, open(target, "wb") as dst:
            remaining = max_member_bytes
            block = 1024 * 1024
            while True:
                chunk = src.read(min(block, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                if remaining < 0:
                    raise ZipMemberSizeError(
                        f"展開中に上限を超えました: {info.filename} "
                        f"(>{max_member_bytes} bytes)"
                    )
                dst.write(chunk)


def validate_decoded_image_size(
    width: int,
    height: int,
    bands: int = 4,
) -> None:
    """デコード後のバイト見積りが 10 GiB を超えないか検証する。"""
    if width <= 0 or height <= 0:
        raise ImageSizeError("無効な画像サイズです")
    try:
        estimated = width * height * max(bands, 1)
    except OverflowError as exc:
        raise ImageSizeError("画像サイズが大きすぎます") from exc
    if estimated > MAX_IMAGE_BYTES:
        raise ImageSizeError(
            f"画像のデコードサイズが上限を超えています "
            f"({estimated} > {MAX_IMAGE_BYTES} bytes)"
        )


def open_image_from_bytes(data: bytes) -> Image.Image:
    """バイト列から画像を開く（10 GiB 上限）。"""
    if len(data) > MAX_IMAGE_BYTES:
        raise ImageSizeError(
            f"画像データが上限を超えています ({len(data)} > {MAX_IMAGE_BYTES} bytes)"
        )
    _ensure_pillow_configured()
    img = Image.open(io.BytesIO(data))
    bands = len(img.getbands()) if hasattr(img, "getbands") else 3
    validate_decoded_image_size(img.width, img.height, bands)
    return img


def open_image_file(path: str | Path) -> Image.Image:
    """ローカル画像ファイルを開く（10 GiB 上限）。"""
    file_path = Path(path)
    size = file_path.stat().st_size
    if size > MAX_IMAGE_BYTES:
        raise ImageSizeError(
            f"画像ファイルが上限を超えています: {file_path.name} "
            f"({size} > {MAX_IMAGE_BYTES} bytes)"
        )
    _ensure_pillow_configured()
    img = Image.open(file_path)
    bands = len(img.getbands()) if hasattr(img, "getbands") else 3
    validate_decoded_image_size(img.width, img.height, bands)
    return img


def write_file_sha256(path: Path) -> str:
    """ファイルの SHA256 を計算し、<path>.sha256 に1行で書き出す。"""
    import hashlib

    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    hash_path = path.with_suffix(path.suffix + ".sha256")
    hash_path.write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return digest


def verify_file_sha256(path: Path, hash_path: Path | None = None) -> bool:
    """<path>.sha256 と実ファイルの SHA256 が一致するか。"""
    import hashlib

    if hash_path is None:
        hash_path = path.with_suffix(path.suffix + ".sha256")
    if not path.is_file() or not hash_path.is_file():
        return False
    expected = hash_path.read_text(encoding="utf-8").strip().split()[0].lower()
    actual = hashlib.sha256(path.read_bytes()).hexdigest().lower()
    return expected == actual
