#!/usr/bin/env python3
"""Render a Mermaid flowchart to an atomically published, ELD-watermarked PNG."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Sequence


MERMAID_CLI_PACKAGE = "@mermaid-js/mermaid-cli@11.12.0"
MERMAID_TIMEOUT_SECONDS = 300
WATERMARK_TEXT = "ELD"
COPYRIGHT_TEXT = "© ELD · ALL RIGHTS RESERVED"
COPYRIGHT_METADATA = "Copyright (c) 2026 ELD. All Rights Reserved."
OUTPUT_VERSION_RE = re.compile(
    r"(?<![A-Za-z0-9])(?P<version>v\d+(?:\.\d+)*)(?![A-Za-z0-9])",
    re.IGNORECASE,
)


class RenderError(RuntimeError):
    """Raised when rendering cannot finish without risking a partial output."""


def _positive_scale(value: str) -> float:
    try:
        scale = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("scale 必须是数字") from exc
    if not math.isfinite(scale) or not 0.1 <= scale <= 8.0:
        raise argparse.ArgumentTypeError("scale 必须是 0.1 到 8.0 的有限数值")
    return scale


def _resolve_existing_file(path: Path, *, label: str) -> Path:
    resolved = path.expanduser().resolve(strict=False)
    if not resolved.is_file():
        raise RenderError(f"{label} 不存在或不是文件: {resolved}")
    return resolved


def _find_npx() -> str:
    executable = shutil.which("npx") or shutil.which("npx.cmd")
    if executable is None:
        raise RenderError("未找到 npx；请先安装 Node.js/npm 并确保 npx 位于 PATH")
    return executable


def _font_candidates() -> list[Path]:
    candidates: list[Path] = []
    windows_directory = os.environ.get("WINDIR")
    if windows_directory:
        font_root = Path(windows_directory) / "Fonts"
        candidates.extend(
            font_root / name
            for name in (
                "segoeui.ttf",
                "arial.ttf",
                "tahoma.ttf",
                "calibri.ttf",
            )
        )
    candidates.extend(
        Path(path)
        for path in (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/opentype/noto/NotoSans-Regular.ttf",
            "/usr/local/share/fonts/DejaVuSans.ttf",
        )
    )
    return candidates


def _load_font(image_font: Any, size: int) -> Any:
    for candidate in _font_candidates():
        if not candidate.is_file():
            continue
        try:
            return image_font.truetype(str(candidate), size=size)
        except OSError:
            continue
    try:
        return image_font.load_default(size=size)
    except TypeError:
        return image_font.load_default()


def _render_mermaid(
    *, input_path: Path, output_path: Path, config_path: Path | None, scale: float
) -> None:
    command = [
        _find_npx(),
        "--yes",
        MERMAID_CLI_PACKAGE,
        "--input",
        str(input_path),
        "--output",
        str(output_path),
        "--scale",
        format(scale, ".6g"),
    ]
    if config_path is not None:
        command.extend(("--puppeteerConfigFile", str(config_path)))
    environment = os.environ.copy()
    environment["NO_UPDATE_NOTIFIER"] = "1"
    environment["npm_config_update_notifier"] = "false"
    try:
        completed = subprocess.run(
            command,
            cwd=str(input_path.parent),
            env=environment,
            shell=False,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=MERMAID_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise RenderError(
            f"Mermaid 渲染超过 {MERMAID_TIMEOUT_SECONDS} 秒，已终止"
        ) from exc
    except OSError as exc:
        raise RenderError(f"无法启动 Mermaid CLI: {exc}") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "无错误输出").strip()
        raise RenderError(
            f"Mermaid CLI 失败（exit={completed.returncode}）: {detail[-4000:]}"
        )
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise RenderError("Mermaid CLI 未生成有效的临时 PNG")


def _skill_version_from_output(output_path: Path) -> str:
    match = OUTPUT_VERSION_RE.search(output_path.stem)
    return match.group("version")[1:] if match else "unknown"


def _watermark_png(
    source_path: Path, destination_path: Path, *, skill_version: str
) -> tuple[int, int]:
    try:
        from PIL import Image, ImageDraw, ImageFont
        from PIL.PngImagePlugin import PngInfo
    except ImportError as exc:
        raise RenderError("缺少 Pillow；请先安装 Pillow 后重试") from exc

    try:
        with Image.open(source_path) as source:
            source.load()
            image = source.convert("RGBA")
    except (OSError, ValueError) as exc:
        raise RenderError(f"Mermaid 临时 PNG 无法读取: {exc}") from exc

    width, height = image.size
    if width < 1 or height < 1:
        raise RenderError("Mermaid 临时 PNG 尺寸无效")

    watermark_size = max(22, min(54, int(min(width, height) * 0.032)))
    watermark_font = _load_font(ImageFont, watermark_size)
    probe = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    probe_draw = ImageDraw.Draw(probe)
    text_box = probe_draw.textbbox((0, 0), WATERMARK_TEXT, font=watermark_font)
    text_width = max(1, text_box[2] - text_box[0])
    text_height = max(1, text_box[3] - text_box[1])
    padding = max(8, watermark_size // 3)
    stamp = Image.new(
        "RGBA",
        (text_width + padding * 2, text_height + padding * 2),
        (0, 0, 0, 0),
    )
    stamp_draw = ImageDraw.Draw(stamp)
    stamp_draw.text(
        (padding - text_box[0], padding - text_box[1]),
        WATERMARK_TEXT,
        font=watermark_font,
        fill=(48, 58, 72, 18),
    )
    resampling = getattr(Image, "Resampling", Image).BICUBIC
    stamp = stamp.rotate(32, resample=resampling, expand=True)

    horizontal_step = max(stamp.width + 120, watermark_size * 6)
    vertical_step = max(stamp.height + 120, watermark_size * 5)
    row = 0
    for y in range(-stamp.height // 2, height, vertical_step):
        offset = -(horizontal_step // 2) if row % 2 else 0
        for x in range(offset - stamp.width // 2, width, horizontal_step):
            image.alpha_composite(stamp, dest=(x, y))
        row += 1

    copyright_size = max(11, min(18, width // 130))
    copyright_font = _load_font(ImageFont, copyright_size)
    draw = ImageDraw.Draw(image, "RGBA")
    copyright_box = draw.textbbox((0, 0), COPYRIGHT_TEXT, font=copyright_font)
    copyright_width = copyright_box[2] - copyright_box[0]
    copyright_height = copyright_box[3] - copyright_box[1]
    margin = max(10, copyright_size)
    copyright_position = (
        max(margin, width - copyright_width - margin - copyright_box[0]),
        max(margin, height - copyright_height - margin - copyright_box[1]),
    )
    draw.text(
        copyright_position,
        COPYRIGHT_TEXT,
        font=copyright_font,
        fill=(30, 36, 45, 105),
        stroke_width=1,
        stroke_fill=(255, 255, 255, 90),
    )

    try:
        png_metadata = PngInfo()
        png_metadata.add_text("ELD-Watermark", "visible")
        png_metadata.add_text("Skill-Version", skill_version)
        png_metadata.add_text("Copyright", COPYRIGHT_METADATA)
        image.save(
            destination_path,
            format="PNG",
            optimize=False,
            compress_level=9,
            pnginfo=png_metadata,
        )
        with Image.open(destination_path) as verification:
            verification.verify()
        with Image.open(destination_path) as verification:
            expected_metadata = {
                "ELD-Watermark": "visible",
                "Skill-Version": skill_version,
                "Copyright": COPYRIGHT_METADATA,
            }
            if any(
                verification.info.get(key) != value
                for key, value in expected_metadata.items()
            ):
                raise RenderError("带水印 PNG 缺少规范发布 metadata")
    except (OSError, ValueError) as exc:
        raise RenderError(f"带水印 PNG 写入或校验失败: {exc}") from exc
    return width, height


def render_flowchart(
    *, input_path: Path, output_path: Path, config_path: Path | None, scale: float
) -> dict[str, Any]:
    source = _resolve_existing_file(input_path, label="Mermaid 输入")
    config = (
        _resolve_existing_file(config_path, label="Puppeteer config")
        if config_path is not None
        else None
    )
    destination = output_path.expanduser().resolve(strict=False)
    if destination.suffix.casefold() != ".png":
        raise RenderError(f"输出必须使用 .png 扩展名: {destination}")
    if destination == source:
        raise RenderError("输入与输出路径不能相同")
    destination.parent.mkdir(parents=True, exist_ok=True)

    temporary_prefix = f".{destination.stem}-render-"
    with tempfile.TemporaryDirectory(
        prefix=temporary_prefix, dir=str(destination.parent)
    ) as temporary_directory:
        temporary_root = Path(temporary_directory)
        mermaid_png = temporary_root / "mermaid.png"
        final_png = temporary_root / "watermarked.png"
        _render_mermaid(
            input_path=source,
            output_path=mermaid_png,
            config_path=config,
            scale=scale,
        )
        skill_version = _skill_version_from_output(destination)
        width, height = _watermark_png(
            mermaid_png, final_png, skill_version=skill_version
        )
        os.replace(final_png, destination)

    return {
        "status": "rendered",
        "input": str(source),
        "output": str(destination),
        "width": width,
        "height": height,
        "scale": scale,
        "watermark": WATERMARK_TEXT,
        "copyright": COPYRIGHT_TEXT,
        "skill_version": skill_version,
        "mermaid_cli": MERMAID_CLI_PACKAGE,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="使用固定版本 Mermaid CLI 生成带 ELD 水印的 PNG"
    )
    parser.add_argument("--input", required=True, type=Path, help="输入 .mmd 文件")
    parser.add_argument("--output", required=True, type=Path, help="最终 .png 文件")
    parser.add_argument("--config", type=Path, help="可选 Puppeteer config JSON")
    parser.add_argument(
        "--scale",
        type=_positive_scale,
        default=1.0,
        help="Mermaid 输出缩放比例，默认 1.0，可选范围 0.1–8.0",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        result = render_flowchart(
            input_path=arguments.input,
            output_path=arguments.output,
            config_path=arguments.config,
            scale=arguments.scale,
        )
    except RenderError as exc:
        parser.exit(1, f"render_flowchart: {exc}\n")
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
