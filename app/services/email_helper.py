import re
import unicodedata
from typing import Tuple

def normalize_and_validate_email(raw_email: str) -> Tuple[str, bool, bool]:
    """
    Normalizes email:
    - Converts full-width characters (＠, 。, ．, ａ-ｚ, Ａ-Ｚ, ０-９) to standard half-width ASCII
    - Trims whitespace & full-width spaces
    - Converts to lowercase
    Returns: (normalized_email, is_valid, had_fullwidth)
    """
    if not raw_email:
        return "", False, False

    original = raw_email.strip()
    had_fullwidth = False

    # Check for full-width @, full-width dot, or other fullwidth chars
    fullwidth_patterns = ['＠', '。', '．', '﹒', '　', '＿', '－']
    if any(c in original for c in fullwidth_patterns):
        had_fullwidth = True

    # Normalize unicode to NFKC (converts full-width English/symbols to standard ASCII)
    normalized = unicodedata.normalize('NFKC', original)
    
    # Replace Chinese full-stop 。 with . if present
    if '。' in normalized:
        had_fullwidth = True
        normalized = normalized.replace('。', '.')

    normalized = normalized.replace(' ', '').replace('　', '').strip().lower()

    # Standard email regex check
    email_regex = r"^[\w\.-]+@[\w\.-]+\.\w+$"
    is_valid = bool(re.match(email_regex, normalized))

    return normalized, is_valid, had_fullwidth
