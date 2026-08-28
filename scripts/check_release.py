#!/usr/bin/env python3
"""Deterministically gate versioned Understanding Cost Skill releases."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import struct
import sys
from typing import Sequence
import zlib


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
FLOW_PNG_TARGET_RE = re.compile(
    r"review-assets/understanding-cost-flow-v[^/\s)]+\.png\Z"
)
FLOW_MMD_TARGET_RE = re.compile(
    r"review-assets/understanding-cost-flow-v[^/\s)]+\.mmd\Z"
)
IMAGE_LINK_RE = re.compile(
    r"!\[[^\]\r\n]*\]\(\s*(?:<([^>\r\n]+)>|([^\s)]+))"
)
MARKDOWN_LINK_RE = re.compile(
    r"(?<!!)\[[^\]\r\n]*\]\(\s*(?:<([^>\r\n]+)>|([^\s)]+))"
)
SAFE_VERSION_RE = re.compile(r"[0-9][0-9A-Za-z]*(?:[._+-][0-9A-Za-z]+)*\Z")


class ReleaseCheckError(ValueError):
    """A deterministic, user-actionable release gate failure."""


class JsonArgumentParser(argparse.ArgumentParser):
    """Make invalid CLI input use the same JSON error channel as checks."""

    def error(self, message: str) -> None:
        raise ReleaseCheckError(f"CLI 参数错误: {message}")


def _json_result(payload: dict[str, object]) -> None:
    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def _read_text(path: Path, *, label: str, errors: list[str]) -> str | None:
    if not path.is_file():
        errors.append(f"缺少 {label}: {path}")
        return None
    try:
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        errors.append(f"无法读取 {label}: {path}: {exc}")
        return None


def _yaml_scalar(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return value.strip()


def _frontmatter_release_fields(text: str) -> tuple[str, str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ReleaseCheckError("SKILL.md 缺少起始 YAML frontmatter")
    try:
        closing = next(
            index
            for index, line in enumerate(lines[1:], start=1)
            if line.strip() == "---"
        )
    except StopIteration as exc:
        raise ReleaseCheckError("SKILL.md 的 YAML frontmatter 未闭合") from exc

    top_level: dict[str, str] = {}
    metadata: dict[str, str] = {}
    section: str | None = None
    for line in lines[1:closing]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indentation = len(line) - len(line.lstrip(" "))
        match = re.fullmatch(r"\s*([A-Za-z0-9_-]+)\s*:\s*(.*?)\s*", line)
        if match is None:
            continue
        key, raw_value = match.groups()
        if indentation == 0:
            if raw_value:
                top_level[key] = _yaml_scalar(raw_value)
                section = None
            else:
                section = key
        elif section == "metadata":
            metadata[key] = _yaml_scalar(raw_value)

    version = metadata.get("version", "")
    owner = metadata.get("owner", "")
    license_name = top_level.get("license", "")
    missing = [
        field
        for field, value in (
            ("metadata.version", version),
            ("metadata.owner", owner),
            ("license", license_name),
        )
        if not value
    ]
    if missing:
        raise ReleaseCheckError(
            "SKILL.md frontmatter 缺少非空字段: " + ", ".join(missing)
        )
    return version, owner, license_name


def _markdown_targets(text: str, *, images: bool) -> list[str]:
    pattern = IMAGE_LINK_RE if images else MARKDOWN_LINK_RE
    return [
        (match.group(1) or match.group(2)).strip()
        for match in pattern.finditer(text)
    ]


def _check_exact_flow_link(
    text: str,
    *,
    label: str,
    expected: str,
    pattern: re.Pattern[str],
    images: bool,
    exactly_once: bool = True,
    errors: list[str],
) -> None:
    flow_targets = [
        target
        for target in _markdown_targets(text, images=images)
        if pattern.fullmatch(target)
    ]
    valid = (
        flow_targets == [expected]
        if exactly_once
        else bool(flow_targets) and set(flow_targets) == {expected}
    )
    if not valid:
        kind = "图片" if images else "源文件"
        errors.append(
            f"{label} 必须且只能嵌入当前版本流程图{kind} {expected}; "
            f"实际={flow_targets}"
        )


def _mmd_header(text: str) -> str:
    header: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped and not header:
            continue
        if stripped.startswith("%%"):
            header.append(stripped)
            continue
        if not stripped and header:
            header.append(stripped)
            continue
        break
    return "\n".join(header)


def _check_mmd_header(text: str, *, version: str, errors: list[str]) -> None:
    header = _mmd_header(text)
    if not re.search(
        rf"(?im)^%%.*\brelease\s*:\s*v{re.escape(version)}\s*$", header
    ):
        errors.append(f"MMD 头缺少匹配版本声明: v{version}")
    if not (
        re.search(r"(?i)copyright", header)
        and "ELD" in header
        and re.search(r"(?i)all rights reserved", header)
    ):
        errors.append("MMD 头缺少 ELD Copyright / All Rights Reserved 声明")


def _split_null(data: bytes, *, label: str) -> tuple[bytes, bytes]:
    try:
        position = data.index(0)
    except ValueError as exc:
        raise ReleaseCheckError(f"PNG {label} chunk 缺少 NUL 分隔符") from exc
    return data[:position], data[position + 1 :]


def _decode_png_text(chunk_type: bytes, data: bytes) -> tuple[str, str]:
    if chunk_type == b"tEXt":
        keyword, value = _split_null(data, label="tEXt")
        return keyword.decode("latin-1"), value.decode("latin-1")
    if chunk_type == b"zTXt":
        keyword, remainder = _split_null(data, label="zTXt")
        if not remainder or remainder[0] != 0:
            raise ReleaseCheckError("PNG zTXt chunk 压缩方法非法")
        try:
            value = zlib.decompress(remainder[1:]).decode("latin-1")
        except (zlib.error, UnicodeError) as exc:
            raise ReleaseCheckError("PNG zTXt chunk 无法解压或解码") from exc
        return keyword.decode("latin-1"), value
    if chunk_type == b"iTXt":
        keyword, remainder = _split_null(data, label="iTXt keyword")
        if len(remainder) < 2:
            raise ReleaseCheckError("PNG iTXt chunk 缺少压缩字段")
        compression_flag, compression_method = remainder[0], remainder[1]
        if compression_method != 0:
            raise ReleaseCheckError("PNG iTXt chunk 压缩方法非法")
        language, remainder = _split_null(
            remainder[2:], label="iTXt language"
        )
        _translated, encoded_text = _split_null(
            remainder, label="iTXt translated keyword"
        )
        if compression_flag == 1:
            try:
                encoded_text = zlib.decompress(encoded_text)
            except zlib.error as exc:
                raise ReleaseCheckError("PNG iTXt chunk 无法解压") from exc
        elif compression_flag != 0:
            raise ReleaseCheckError("PNG iTXt chunk 压缩标志非法")
        if language and any(byte > 0x7F for byte in language):
            raise ReleaseCheckError("PNG iTXt language tag 非 ASCII")
        try:
            return keyword.decode("latin-1"), encoded_text.decode("utf-8")
        except UnicodeError as exc:
            raise ReleaseCheckError("PNG iTXt chunk 无法解码") from exc
    raise ReleaseCheckError(f"不支持的 PNG 文本 chunk: {chunk_type!r}")


def _png_text_metadata(path: Path) -> dict[str, list[str]]:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise ReleaseCheckError(f"无法读取 PNG: {path}: {exc}") from exc
    if not payload.startswith(PNG_SIGNATURE):
        raise ReleaseCheckError("流程图不是有效 PNG：签名不匹配")

    position = len(PNG_SIGNATURE)
    chunks: list[bytes] = []
    metadata: dict[str, list[str]] = {}
    saw_iend = False
    while position < len(payload):
        if len(payload) - position < 12:
            raise ReleaseCheckError("PNG chunk 被截断")
        length = struct.unpack(">I", payload[position : position + 4])[0]
        chunk_type = payload[position + 4 : position + 8]
        data_start = position + 8
        data_end = data_start + length
        crc_end = data_end + 4
        if crc_end > len(payload):
            raise ReleaseCheckError("PNG chunk 长度越界")
        chunk_data = payload[data_start:data_end]
        expected_crc = struct.unpack(">I", payload[data_end:crc_end])[0]
        actual_crc = zlib.crc32(chunk_type)
        actual_crc = zlib.crc32(chunk_data, actual_crc) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            name = chunk_type.decode("latin-1", errors="replace")
            raise ReleaseCheckError(f"PNG chunk CRC 不匹配: {name}")
        if not re.fullmatch(rb"[A-Za-z]{4}", chunk_type):
            raise ReleaseCheckError("PNG chunk type 非法")
        chunks.append(chunk_type)
        if chunk_type in {b"tEXt", b"zTXt", b"iTXt"}:
            key, value = _decode_png_text(chunk_type, chunk_data)
            metadata.setdefault(key, []).append(value)
        position = crc_end
        if chunk_type == b"IEND":
            if length != 0:
                raise ReleaseCheckError("PNG IEND chunk 必须为空")
            saw_iend = True
            break

    if not chunks or chunks[0] != b"IHDR":
        raise ReleaseCheckError("PNG 首个 chunk 必须是 IHDR")
    if not saw_iend:
        raise ReleaseCheckError("PNG 缺少 IEND chunk")
    if position != len(payload):
        raise ReleaseCheckError("PNG IEND 后存在额外二进制数据")
    return metadata


def _check_png_metadata(
    path: Path, *, version: str, errors: list[str]
) -> None:
    try:
        metadata = _png_text_metadata(path)
    except ReleaseCheckError as exc:
        errors.append(str(exc))
        return
    expected_exact = {
        "ELD-Watermark": "visible",
        "Skill-Version": version,
    }
    for key, expected in expected_exact.items():
        values = metadata.get(key, [])
        if values != [expected]:
            errors.append(
                f"PNG metadata {key} 必须唯一且等于 {expected!r}; 实际={values}"
            )
    copyright_values = metadata.get("Copyright", [])
    if len(copyright_values) != 1 or not (
        "ELD" in copyright_values[0]
        and re.search(r"(?i)all rights reserved", copyright_values[0])
    ):
        errors.append(
            "PNG metadata Copyright 必须唯一且包含 ELD / All Rights Reserved"
        )


def _check_restrictions(text: str, *, label: str, errors: list[str]) -> None:
    if not re.search(
        r"(?:禁止|不得)[\s\S]{0,180}(?:商用|商业使用|商业目的)", text
    ):
        errors.append(f"{label} 缺少禁止商业使用声明")
    for term in ("转载", "转发", "借用"):
        if term not in text:
            errors.append(f"{label} 缺少禁止{term}声明")
    if not re.search(r"(?i)all rights reserved", text):
        errors.append(f"{label} 缺少 All Rights Reserved 声明")


def check_release(root: Path) -> dict[str, object]:
    errors: list[str] = []
    skill_path = root / "SKILL.md"
    readme_path = root / "README.md"
    license_path = root / "LICENSE"
    skill_text = _read_text(skill_path, label="SKILL.md", errors=errors)
    readme_text = _read_text(readme_path, label="README.md", errors=errors)
    license_text = _read_text(license_path, label="LICENSE", errors=errors)

    version = ""
    if skill_text is not None:
        try:
            version, owner, license_name = _frontmatter_release_fields(skill_text)
        except ReleaseCheckError as exc:
            errors.append(str(exc))
        else:
            if not SAFE_VERSION_RE.fullmatch(version):
                errors.append(f"metadata.version 不能安全映射到版本化文件名: {version!r}")
            if owner != "ELD":
                errors.append(f"metadata.owner 必须精确等于 ELD; 实际={owner!r}")
            folded_license = license_name.casefold()
            if "proprietary" not in folded_license:
                errors.append("frontmatter license 必须包含 Proprietary")
            if "all rights reserved" not in folded_license:
                errors.append("frontmatter license 必须包含 All Rights Reserved")
        _check_restrictions(skill_text, label="SKILL.md", errors=errors)
    if license_text is not None:
        _check_restrictions(license_text, label="LICENSE", errors=errors)

    if version and SAFE_VERSION_RE.fullmatch(version):
        png_relative = f"review-assets/understanding-cost-flow-v{version}.png"
        mmd_relative = f"review-assets/understanding-cost-flow-v{version}.mmd"
        if skill_text is not None:
            _check_exact_flow_link(
                skill_text,
                label="SKILL.md",
                expected=png_relative,
                pattern=FLOW_PNG_TARGET_RE,
                images=True,
                errors=errors,
            )
            _check_exact_flow_link(
                skill_text,
                label="SKILL.md",
                expected=mmd_relative,
                pattern=FLOW_MMD_TARGET_RE,
                images=False,
                exactly_once=False,
                errors=errors,
            )
        if readme_text is not None:
            _check_exact_flow_link(
                readme_text,
                label="README.md",
                expected=png_relative,
                pattern=FLOW_PNG_TARGET_RE,
                images=True,
                errors=errors,
            )

        mmd_path = root / Path(mmd_relative)
        png_path = root / Path(png_relative)
        mmd_text = _read_text(mmd_path, label="版本化 MMD", errors=errors)
        if mmd_text is not None:
            _check_mmd_header(mmd_text, version=version, errors=errors)
        if not png_path.is_file():
            errors.append(f"缺少版本化 PNG: {png_path}")
        else:
            _check_png_metadata(png_path, version=version, errors=errors)
    elif skill_text is not None:
        errors.append("无法从有效 metadata.version 校验版本化流程图")

    if errors:
        return {"status": "error", "version": version or None, "errors": errors}
    return {"status": "ok", "version": version}


def main(argv: Sequence[str] | None = None) -> int:
    parser = JsonArgumentParser(description="检查 Understanding Cost 发布合同")
    parser.add_argument("--root", required=True, type=Path, help="Skill 根目录")
    try:
        args = parser.parse_args(argv)
        root = args.root.expanduser().resolve(strict=False)
        if not root.is_dir():
            raise ReleaseCheckError(f"Skill 根目录不存在或不是目录: {root}")
        result = check_release(root)
    except ReleaseCheckError as exc:
        result = {"status": "error", "version": None, "errors": [str(exc)]}
    _json_result(result)
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
