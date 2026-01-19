import re

DANGEROUS_PATTERNS = [
    r"\brm\s+-rf\b",
    r"\bwipefs\b",
    r"\bmkfs\.",
    r"\bdd\s+if=",
    r":\(\)\s*\{\s*:\s*\|\s*:\s*;\s*\}\s*;\s*:",  # fork bomb
]

def is_command_dangerous(cmd: str) -> bool:
    c = (cmd or "").lower()
    for p in DANGEROUS_PATTERNS:
        if re.search(p, c):
            return True
    return False
