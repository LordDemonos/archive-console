"""Non-fatal, yt-dlp-free heuristics for yt-dlp.conf (smoke only)."""

from __future__ import annotations

import re

_LINE_TOO_LONG = 65536
_BAD_LINE = re.compile(r"^[\s]*[^\s#][^#\n]*\s{2,}[^\n#]+$")


def conf_syntax_smoke(content: str) -> list[str]:
    warnings: list[str] = []
    if "\x00" in content:
        warnings.append("Null byte in file (unusual for text config).")
    if not content.endswith("\n") and content.strip():
        warnings.append("File does not end with a newline (style).")
    for i, line in enumerate(content.splitlines(), 1):
        if len(line) > _LINE_TOO_LONG:
            warnings.append(f"Line {i} is very long ({len(line)} chars).")
            break
        try:
            line.encode("utf-8")
        except UnicodeEncodeError:
            warnings.append(f"Line {i} is not valid UTF-8.")
            break
        if _BAD_LINE.match(line):
            warnings.append(
                f"Line {i}: possible stray spacing before an inline comment "
                "(soft check only)."
            )
    return warnings[:12]
