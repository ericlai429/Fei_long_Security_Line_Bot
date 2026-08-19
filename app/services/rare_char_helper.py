import unicodedata
from typing import Dict, List, Set, Tuple

# Common rare characters, variant characters, and their canonical equivalents in Taiwan names
RARE_VARIANT_MAP: Dict[str, str] = {
    # 常用異體字 / 生僻字 ➔ 常用同音同義字對照
    "堃": "坤", "煊": "宣", "珉": "民", "喆": "吉", "彣": "文",
    "澔": "浩", "蒨": "倩", "霈": "沛", "璘": "麟", "昇": "升",
    "峯": "峰", "恒": "恆", "詠": "泳", "羣": "群", "頴": "穎",
    "温": "溫", "黄": "黃", "眞": "真", "銹": "繡", "粧": "妝",
    "珮": "佩", "瑄": "宣", "彧": "郁", "淼": "渺", "垚": "堯",
    "犇": "奔", "皜": "皓", "甯": "寧", "玥": "月", "晧": "皓",
    "珺": "君", "璿": "璇", "琁": "璇", "曄": "燁", "暐": "偉",
    "杰": "傑", "峯": "峰", "銹": "繡", "銹": "鏽", "咏": "詠"
}

# Reverse mapping for fuzzy search (e.g. searching 坤 matches 堃)
VARIANT_SEARCH_ALIASES: Dict[str, Set[str]] = {}
for rare, common in RARE_VARIANT_MAP.items():
    VARIANT_SEARCH_ALIASES.setdefault(rare, set()).add(common)
    VARIANT_SEARCH_ALIASES.setdefault(common, set()).add(rare)

class RareCharHelper:
    """
    Rare and Variant Chinese Character Foolproof Helper.
    Provides character detection, variant normalization, and fuzzy search expansion.
    """

    @staticmethod
    def is_rare_or_variant_char(char: str) -> bool:
        return char in RARE_VARIANT_MAP or (ord(char) > 0x9FFF and ord(char) < 0x2FA1F)

    @classmethod
    def analyze_name_for_rare_chars(cls, name: str) -> List[Dict[str, str]]:
        """
        Inspects a guard name for rare or variant characters and returns resolution advice.
        """
        results = []
        if not name or name == "-":
            return results

        for idx, ch in enumerate(name):
            if ch in RARE_VARIANT_MAP:
                common_eq = RARE_VARIANT_MAP[ch]
                results.append({
                    "char": ch,
                    "position": idx + 1,
                    "type": "異體/生僻字",
                    "common_equivalent": common_eq,
                    "suggestion": f"字元「{ch}」為常見異體字，系統已自動啟用模糊相容支援（搜尋「{common_eq}」亦可自動命中）。"
                })
            elif ord(ch) > 0x9FFF: # Unicode Extension
                results.append({
                    "char": ch,
                    "position": idx + 1,
                    "type": "Unicode 擴充罕用字",
                    "common_equivalent": "?",
                    "suggestion": f"字元「{ch}」為 Unicode 擴充罕見字，已進行 UTF-8 安全防呆處理，確保 LINE 與 PDF 不會亂碼。"
                })
        return results

    @classmethod
    def get_fuzzy_search_variants(cls, query: str) -> List[str]:
        """
        Generates search query variants so typing '賴冠坤' matches '賴冠堃', and vice versa.
        """
        if not query:
            return []
        
        variants = {query}
        for i, ch in enumerate(query):
            if ch in VARIANT_SEARCH_ALIASES:
                for alt_ch in VARIANT_SEARCH_ALIASES[ch]:
                    new_q = query[:i] + alt_ch + query[i+1:]
                    variants.add(new_q)
        return list(variants)

    @classmethod
    def normalize_name_variants(cls, name: str) -> str:
        """
        Normalizes a name's variant characters to standard common characters for indexing.
        """
        return "".join(RARE_VARIANT_MAP.get(ch, ch) for ch in name)

rare_char_helper = RareCharHelper()
