"""Language identification for English, Hindi, Marathi and code-mixed Hinglish, plus query expansion.

Hinglish is Hindi typed in Roman letters and mixed with English ("mera EMI bounce hua toh kitna lagega?").
Standard language detectors call this English, so retrieval over an English document fails on the Hindi
words. We detect it with a function-word lexicon, then expand the query with English synonyms so BM25
can match the document. This is a small, explicit form of cross-lingual retrieval.
"""
from __future__ import annotations

import re

DEVANAGARI = re.compile(r"[ऀ-ॿ]")
ROMAN_WORD = re.compile(r"[a-z]+")

HINGLISH_WORDS = {
    "hai", "hain", "kya", "kab", "kitna", "kitni", "kitne", "mera", "meri", "mere", "mujhe", "agar", "toh",
    "hoga", "hogi", "lagega", "lagegi", "lagta", "karna", "karu", "karoon", "nahi", "nahin", "kaise", "kaisa", "ka",
    "ki", "ke", "ho", "jaldi", "paisa", "paise", "bhar", "bharna", "chukana", "band", "kar", "hua", "hui", "gaya",
    "gayi", "wala", "wali", "kyun", "kyon", "sakta", "sakti", "sakte", "chahiye", "lena", "dena", "dene", "pehle",
    "baad", "abhi", "bhi", "aur", "ya", "sirf", "kuch", "koi", "yeh", "ye", "woh", "wo", "isme", "ismein", "iska",
    "iski", "aapko", "mujhse", "kitnaa", "byaj", "kist", "bima", "shulk", "batao", "bataiye", "samjhao", "kaun",
    "kahan", "milega", "milegi", "katega", "kategi", "jayega", "jaayega", "padega", "padegi", "ek", "teen",
}
MARATHI_MARKERS = {"आहे", "नाही", "काय", "कसे", "कसा", "माझ्या", "माझे", "मला", "होईल", "किती", "का", "आणि", "जर", "तर", "लागेल", "भरले", "भरला"}
HINDI_MARKERS = {"है", "नहीं", "क्या", "मेरा", "मेरी", "मुझे", "होगा", "कितना", "कितनी", "और", "अगर", "तो", "लगेगा", "किस्त"}

# Hinglish / Hindi / Marathi word -> English terms used in loan documents.
EXPANSIONS: dict[str, str] = {
    "bounce": "bounce dishonour nach ecs mandate return charges",
    "der": "late delay overdue penal charges", "deri": "late delay overdue penal", "late": "late delay overdue penal",
    "jaldi": "prepayment foreclosure early close", "pehle": "prepayment foreclosure early", "band": "foreclosure close closure",
    "chukana": "repay prepayment foreclosure", "close": "foreclosure closure prepayment",
    "byaj": "interest rate", "sood": "interest rate", "rate": "interest rate floating reset", "badh": "increase floating reset revise",
    "fees": "fee charges", "fee": "fee charges", "charge": "charges fee", "shulk": "fee charges",
    "kist": "emi instalment", "emi": "emi instalment", "bima": "insurance premium", "insurance": "insurance premium",
    "renew": "renewal auto-renew", "cancel": "cancel cancellation renewal", "radd": "cancel cancellation",
    "data": "data share third party", "jankari": "information data share", "minimum": "minimum amount due",
    "claim": "claim waiting period exclusion", "dawa": "claim",
    "देर": "late delay overdue penal", "जल्दी": "prepayment foreclosure early", "बंद": "foreclosure close", "शुल्क": "fee charges",
    "ब्याज": "interest rate", "किस्त": "emi instalment", "बीमा": "insurance premium", "दावा": "claim", "प्रतीक्षा": "waiting period",
    "बाउंस": "bounce dishonour", "उशीर": "late delay overdue", "उशिरा": "late delay overdue", "व्याज": "interest rate",
    "हप्ता": "emi instalment", "हप्ते": "emi instalment", "विमा": "insurance premium", "फी": "fee charges", "दंड": "penal charges penalty",
    "जुर्माना": "penal charges penalty", "penalty": "penal charges penalty", "jurmana": "penal charges penalty",
}


def detect_language(text: str) -> str:
    deva = len(DEVANAGARI.findall(text))
    letters = len(re.findall(r"[A-Za-zऀ-ॿ]", text)) or 1
    if deva / letters > 0.3:
        words = set(re.findall(r"[ऀ-ॿ]+", text))
        return "mr" if len(words & MARATHI_MARKERS) > len(words & HINDI_MARKERS) else "hi"
    words = ROMAN_WORD.findall(text.lower())
    if not words:
        return "en"
    hits = sum(1 for w in words if w in HINGLISH_WORDS)
    return "hinglish" if hits >= 2 or hits / len(words) >= 0.25 else "en"


def expand_query(text: str) -> str:
    extra = []
    for token in re.findall(r"[a-z]+|[ऀ-ॿ]+", text.lower()):
        for key, value in EXPANSIONS.items():
            if token == key or (len(key) > 3 and token.startswith(key)):
                extra.append(value)
    return text + (" " + " ".join(extra) if extra else "")
