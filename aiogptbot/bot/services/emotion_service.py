import re

BAD_WORDS = [
    'блять', 'сука', 'хуй', 'пизд', 'еба', 'ебл', 'гандон', 'мудак', 'долбоёб', 'долбаёб', 'идиот', 'тварь',
    'сволочь', 'чмо', 'мразь', 'ублюдок', 'гнида', 'шлюха', 'проститутка', 'сучка', 'гавно', 'говно', 'дерьмо'
]
BAD_WORDS_RE = re.compile(r'(' + '|'.join(BAD_WORDS) + r')', re.IGNORECASE)

SAD_KEYWORDS = [
    'грустно', 'печально', 'тяжело', 'депрессия', 'плохо', 'одиноко', 'устал', 'нет сил', 'разочарован',
    'тоска', 'слёзы', 'слезы', 'плакать', 'не хочу жить', 'безнадежно', 'безнадёжно', 'боль', 'страх', 'тревога'
]

# Фильтрация мата: возвращает (отфильтрованный текст, был ли мат)
def filter_bad_words(text):
    replaced = False
    def repl(match):
        nonlocal replaced
        replaced = True
        return "[цензурно]"
    filtered = BAD_WORDS_RE.sub(repl, text)
    return filtered, replaced

# Определение эмоции: возвращает 'sad', 'neutral'
def detect_emotion(text):
    text = text.lower()
    if any(word in text for word in SAD_KEYWORDS):
        return 'sad'
    return 'neutral'
