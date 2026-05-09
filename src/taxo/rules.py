from __future__ import annotations

import fnmatch
import re

from taxo.config import RuleConfig
from taxo.models import FileItem

BUILTIN_RULES: dict[str, list[str]] = {
    "图片": [
        ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".ico",
        ".raw", ".cr2", ".nef", ".heic",
    ],
    "文档": [
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".odt", ".ods", ".odp", ".txt", ".md", ".rtf",
    ],
    "电子书": [".epub", ".mobi", ".azw3", ".fb2", ".djvu"],
    "代码": [
        ".py", ".js", ".ts", ".java", ".cpp", ".c", ".h", ".go",
        ".rs", ".rb", ".php", ".swift", ".kt", ".scala", ".sh", ".bash", ".zsh",
    ],
    "数据": [
        ".json", ".xml", ".yaml", ".yml", ".csv", ".tsv",
        ".sql", ".db", ".sqlite", ".parquet",
    ],
    "压缩包": [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".dmg", ".iso"],
    "安装包": [".exe", ".msi", ".pkg", ".deb", ".rpm", ".appimage"],
    "视频": [
        ".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv",
        ".webm", ".m4v", ".mpg", ".mpeg", ".mts", ".m2ts",
    ],
    "音频": [
        ".mp3", ".wav", ".flac", ".aac", ".ogg",
        ".m4a", ".wma", ".opus", ".aiff", ".m4p",
    ],
    "字体": [".ttf", ".otf", ".woff", ".woff2", ".eot"],
    "设计": [
        ".psd", ".ai", ".sketch", ".fig", ".xd",
        ".afdesign", ".afphoto", ".afpub",
    ],
}


class Rule:
    __slots__ = ("pattern_type", "pattern", "category", "_regex")

    def __init__(self, pattern_type: str, pattern: str, category: str) -> None:
        self.pattern_type = pattern_type
        self.pattern = pattern
        self.category = category
        self._regex: re.Pattern[str] | None = None
        if pattern_type == "regex":
            self._regex = re.compile(pattern)


def parse_rule(raw: str, category: str) -> Rule:
    if raw.startswith("ext:"):
        return Rule("ext", raw[4:], category)
    if raw.startswith("pattern:"):
        return Rule("pattern", raw[8:], category)
    if raw.startswith("regex:"):
        return Rule("regex", raw[6:], category)
    return Rule("ext", raw, category)


def _match_rule(rule: Rule, file: FileItem) -> bool:
    if rule.pattern_type == "ext":
        return file.ext == rule.pattern
    if rule.pattern_type == "pattern":
        return fnmatch.fnmatch(file.name + file.ext, rule.pattern)
    if rule.pattern_type == "regex":
        return bool(rule._regex and rule._regex.search(file.name + file.ext))
    return False


def _match_compound(rule: Rule, file: FileItem) -> bool:
    parts = rule.pattern.split(" AND ")
    if len(parts) < 2:
        return _match_rule(rule, file)
    for part in parts:
        sub = parse_rule(part.strip(), "")
        if not _match_rule(sub, file):
            return False
    return True


class RuleEngine:
    def __init__(self, config: RuleConfig) -> None:
        self._ext_map: dict[str, str] = {}
        self._custom_rules: list[Rule] = []

        if config.use_builtin:
            for category, exts in BUILTIN_RULES.items():
                for ext in exts:
                    self._ext_map[ext] = category

        for custom in config.custom:
            raw_pattern = custom["pattern"]
            cat = custom["category"]
            if " AND " in raw_pattern:
                self._custom_rules.append(Rule("compound", raw_pattern, cat))
            else:
                self._custom_rules.append(parse_rule(raw_pattern, cat))

    def match(self, file: FileItem) -> str | None:
        for rule in self._custom_rules:
            if rule.pattern_type == "compound":
                if _match_compound(rule, file):
                    return rule.category
            elif _match_rule(rule, file):
                return rule.category

        if file.ext in self._ext_map:
            return self._ext_map[file.ext]
        return None

    def classify(
        self, files: list[FileItem]
    ) -> tuple[dict[str, list[FileItem]], list[FileItem]]:
        matched: dict[str, list[FileItem]] = {}
        unmatched: list[FileItem] = []

        for file in files:
            category = self.match(file)
            if category is not None:
                matched.setdefault(category, []).append(file)
            else:
                unmatched.append(file)

        return matched, unmatched
