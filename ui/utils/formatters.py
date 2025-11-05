"""共通の表示フォーマッタ群"""

import re
from html import escape


def display_with_overline(expr: str) -> str:
    """条件式中の `!` トークンを上線付きで表示する HTML を返す"""

    if not expr:
        return ""

    safe = escape(expr)

    def _repl(match):
        full = match.group(0)
        token = match.group(1)
        has_open = "(" in full
        has_close = ")" in full
        replaced = f"<span style='text-decoration: overline;'>{token}</span>"
        if has_open:
            replaced = "(" + replaced
        if has_close:
            replaced = replaced + ")"
        return replaced

    pattern = r"!\s*\(?(QL\d{3}|Q\d{3}|X\d{3})\)?(?=[\s\^v,)]|$)"
    return re.sub(pattern, _repl, safe)

