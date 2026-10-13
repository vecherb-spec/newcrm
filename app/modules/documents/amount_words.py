from decimal import Decimal

_ONES = (
    "ноль",
    "один",
    "два",
    "три",
    "четыре",
    "пять",
    "шесть",
    "семь",
    "восемь",
    "девять",
)
_TEENS = (
    "десять",
    "одиннадцать",
    "двенадцать",
    "тринадцать",
    "четырнадцать",
    "пятнадцать",
    "шестнадцать",
    "семнадцать",
    "восемнадцать",
    "девятнадцать",
)
_TENS = (
    "",
    "",
    "двадцать",
    "тридцать",
    "сорок",
    "пятьдесят",
    "шестьдесят",
    "семьдесят",
    "восемьдесят",
    "девяносто",
)
_HUNDREDS = (
    "",
    "сто",
    "двести",
    "триста",
    "четыреста",
    "пятьсот",
    "шестьсот",
    "семьсот",
    "восемьсот",
    "девятьсот",
)


def _triplet_to_words(value: int, feminine: bool = False) -> str:
    if value == 0:
        return ""
    hundreds = _HUNDREDS[value // 100]
    remainder = value % 100
    if 10 <= remainder <= 19:
        tail = _TEENS[remainder - 10]
    else:
        tens = _TENS[remainder // 10]
        ones_value = remainder % 10
        if feminine and ones_value == 1:
            ones = "одна"
        elif feminine and ones_value == 2:
            ones = "две"
        else:
            ones = _ONES[ones_value]
        tail = " ".join(part for part in (tens, ones if remainder % 10 or not tens else "") if part)
    return " ".join(part for part in (hundreds, tail) if part)


def rubles_in_words(amount: Decimal | float | int) -> str:
    value = Decimal(str(amount)).quantize(Decimal("0.01"))
    rubles = int(value)
    kopecks = int((value - rubles) * 100)
    parts: list[str] = []
    millions = rubles // 1_000_000
    thousands = (rubles % 1_000_000) // 1000
    rest = rubles % 1000
    if millions:
        parts.append(_triplet_to_words(millions))
        parts.append("миллионов")
    if thousands:
        parts.append(_triplet_to_words(thousands, feminine=True))
        parts.append("тысяч")
    if rest or not parts:
        parts.append(_triplet_to_words(rest))
    ruble_word = "рубль" if rubles % 10 == 1 and rubles % 100 != 11 else "рублей"
    if rubles % 10 in {2, 3, 4} and rubles % 100 not in {12, 13, 14}:
        ruble_word = "рубля"
    return f"{' '.join(parts).strip()} {ruble_word} {kopecks:02d} копеек"
