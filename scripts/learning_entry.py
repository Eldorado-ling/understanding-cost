"""Session-only learning-data choice and a narrow CLI access gate.

The plan is pure: it never discovers, opens, creates, or persists a database.
Confirmation references are supplied user-message references, not proof of
consent. The CLI checks paths after confirmation; it is not an OS sandbox.
"""

from __future__ import annotations

import os
from pathlib import Path
import stat
from typing import Any


DATA_MODES = ("create_boundary", "use_existing", "no_personal_data")
CHOICE_QUESTION = (
    "开始学习前，你希望怎样确认知识边界？请选择："
    "1. 由 Skill 和你对话，创建并维护知识边界档案；"
    "2. 使用你自己已有的数据库，默认只读；"
    "3. 不使用已有个人数据，也不保存学习档案，只围绕当前问题临时确认前提。"
)
_AMBIGUOUS_REFS = {
    "yes", "true", "ok", "confirmed", "confirmation", "unknown", "none",
    "null", "todo", "tbd", "1", "2", "3", "确认", "同意", "已确认", "是",
}


class EntryGateError(ValueError):
    """A blocked CLI operation, before any database content is consumed."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _reference(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if (not value or value.lower() in _AMBIGUOUS_REFS
            or "\n" in value or "\r" in value
            or value.startswith("<") or value.startswith("[")):
        return None
    return value


def _absolute_path(value: Any) -> Path | None:
    """Lexical validation only. No resolve/stat/cwd lookup or env expansion."""
    if not isinstance(value, (str, Path)) or not str(value).strip():
        return None
    raw = str(value)
    path = Path(raw)
    if (not path.is_absolute() or ".." in path.parts or "\x00" in raw
            or raw != raw.strip()):
        return None
    # A drive/filesystem root is not a precise learner database directory.
    if path == Path(path.anchor):
        return None
    return path


def build_entry_plan(
    data_mode: str | None = None,
    confirmation_ref: str | None = None,
    data_root: str | Path | None = None,
    write_confirmation_ref: str | None = None,
) -> dict[str, Any]:
    """Return a next-action plan, never a diagnosed boundary or saved choice."""
    plan: dict[str, Any] = {
        "schema": "uc-learning-entry/0.1", "status": "awaiting_choice",
        "data_mode": None, "confirmation_ref": None, "data_root": None,
        "write_confirmation_ref": None, "session_only": True,
        "boundary_status": "not_assessed", "can_read_personal_data": False,
        "can_write_personal_data": False, "next_action": "ask_data_mode",
        "user_prompt": CHOICE_QUESTION,
    }
    if data_mode is None:
        return plan
    if data_mode not in DATA_MODES:
        return {**plan, "status": "blocked", "reason": "invalid_data_mode"}
    plan["data_mode"] = data_mode
    reference = _reference(confirmation_ref)
    if reference is None:
        return {**plan, "status": "awaiting_confirmation",
                "next_action": "ask_mode_confirmation",
                "reason": "specific_user_message_reference_required"}
    plan["confirmation_ref"] = reference
    if data_mode == "no_personal_data":
        if data_root is not None or write_confirmation_ref is not None:
            return {**plan, "status": "blocked", "reason": "no_data_mode_rejects_data_scope",
                    "next_action": "remove_data_scope",
                    "user_prompt": "已选择不使用个人数据；请移除旧数据库路径和写入授权。"}
        return {**plan, "status": "ready", "next_action": "local_boundary_check",
                "user_prompt": None}
    root = _absolute_path(data_root)
    if root is None:
        return {**plan, "status": "awaiting_scope", "next_action": "ask_data_scope",
                "user_prompt": "请指定并确认本次可以使用的精确数据库绝对路径；确认前不访问该路径。"}
    if write_confirmation_ref is not None and _reference(write_confirmation_ref) is None:
        return {**plan, "status": "blocked", "next_action": "ask_write_confirmation",
                "reason": "specific_write_message_reference_required",
                "user_prompt": "如需写入，请提供你额外同意写入的具体消息引用；否则保持只读。"}
    return {
        **plan, "status": "ready", "data_root": str(root),
        "write_confirmation_ref": _reference(write_confirmation_ref),
        "can_read_personal_data": True,
        "can_write_personal_data": data_mode == "create_boundary" or write_confirmation_ref is not None,
        "next_action": ("diagnose_and_create_boundary" if data_mode == "create_boundary"
                        else "review_existing_boundary"),
        "user_prompt": None,
    }


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(str(left)) == os.path.normcase(str(right))


def _reject_link(path: Path) -> None:
    """Do not follow symlinks, Windows junctions, or other reparse points."""
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISLNK(info.st_mode) or (getattr(info, "st_file_attributes", 0)
                                  & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
        raise EntryGateError("linked_data_scope", "数据库范围含链接或 reparse point；请改用确认过的实际目录。")


def guard_operation(
    plan: dict[str, Any],
    target: str | Path,
    *,
    write: bool = False,
    initialize: bool = False,
    extra_paths: tuple[Path, ...] = (),
) -> Path:
    """Check mode and exact scope before inspecting filesystem metadata.

Only after all lexical/permission checks pass do we inspect the authorized
tree for links. Rechecking cannot defeat hostile concurrent filesystem edits;
callers must not describe this as full host isolation or an authorization API.
"""
    if plan.get("status") != "ready":
        raise EntryGateError("entry_not_confirmed", "请先完成学习开始选项及数据范围确认。")
    if not plan.get("can_read_personal_data"):
        raise EntryGateError("personal_data_disabled", "当前模式不读取或写入个人数据库；仅进行本轮临时前提确认。")
    if initialize and plan.get("data_mode") != "create_boundary":
        raise EntryGateError("existing_database_no_init", "使用已有数据库不能初始化、覆盖或填入合成 Demo。")
    if write and not plan.get("can_write_personal_data"):
        raise EntryGateError("readonly_database", "已有数据库默认只读；写入需要额外明确确认。")
    root = _absolute_path(plan.get("data_root"))
    selected = _absolute_path(target)
    if root is None or selected is None or not _same_path(root, selected):
        raise EntryGateError("data_scope_mismatch", "操作目录必须与确认过的精确绝对 data_root 相同。")
    scoped_paths = [root]
    for extra in extra_paths:
        path = _absolute_path(extra)
        if path is None or not path.is_relative_to(root):
            raise EntryGateError("file_outside_data_scope", "输入记录、教学内容和导出文件只能位于确认的数据目录内。")
        scoped_paths.append(path)
    # Permissions above are pure; do not move filesystem calls before them.
    for path in scoped_paths:
        # Inspect ancestors from the filesystem root downward, so a linked
        # parent is rejected before inspecting anything behind that link.
        for component in reversed((path, *path.parents)):
            _reject_link(component)
        if not _same_path(path, path.resolve()):
            raise EntryGateError("linked_data_scope", "路径经链接指向其他位置；请明确确认实际目录。")
    if root.exists():
        if not root.is_dir():
            raise EntryGateError("data_root_not_directory", "当前 Vault CLI 仅支持目录形式的数据库，不自动转格式。")
        for directory, dirs, files in os.walk(root, followlinks=False):
            for name in (*dirs, *files):
                _reject_link(Path(directory) / name)
    elif not initialize:
        raise EntryGateError("data_root_missing", "数据库不存在；不得静默新建或复制其他数据库。")
    elif not root.parent.is_dir():
        raise EntryGateError("parent_directory_missing", "新数据库的父目录必须已存在；不在确认范围外创建目录。")
    return root
