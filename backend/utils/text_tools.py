import re
from pymorphy3 import MorphAnalyzer

morph = MorphAnalyzer()

def correct_keyboard_layout(text: str) -> str | None:
    """
    Переключает текст с английской раскладки на русскую.
    """
    eng = "`" + "qwertyuiop[]asdfghjkl;'zxcvbnm,./" + '~' + 'QWERTYUIOP{}ASDFGHJKL:"ZXCVBNM<>' + '?'
    rus = "ё" + "йцукенгшщзхъфывапролджэячсмитьбю." + 'Ё' + 'ЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮ,'
    layout_map = str.maketrans(eng, rus)
    corrected_text = text.translate(layout_map)
    if corrected_text == text or not re.search(r'[а-яА-ЯёЁ]', corrected_text):
        return None
    return corrected_text

def is_plausible_name(name: str) -> bool:
    """Проверяет, является ли строка похожей на реальное имя."""
    name = name.strip()
    if not (2 <= len(name) <= 50): return False
    if not re.fullmatch(r'[а-яА-ЯёЁ\s\-]+', name): return False
    stop_words = ["тест", "проверка", "бот", "дурак", "абырвалг", "йцукен"]
    if name.lower() in stop_words: return False
    return True

def inflect_name(name: str, case: str) -> str:
    """
    Склоняет имя (или ФИО) в нужный падеж, сохраняя правильную капитализацию.
    Теперь функция защищена от None на входе.
    """
    # ---  Защита от пустого значения ---
    if not name or not isinstance(name, str):
        return ""

    try:
        words = name.split()
        inflected_parts = []
        for word in words:
            parses = morph.parse(word)
            name_parse = next((p for p in parses if 'Name' in p.tag or 'Surn' in p.tag or 'Patr' in p.tag), parses[0])
            inflected_word_obj = name_parse.inflect({case})
            inflected_parts.append(inflected_word_obj.word if inflected_word_obj else word)
        return " ".join(part.capitalize() for part in inflected_parts)
    except Exception:
        return " ".join(part.capitalize() for part in name.split())

