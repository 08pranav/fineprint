"""Ethical guardrails: FinePrint explains documents; it does not give personal financial advice."""
from __future__ import annotations

import re

ADVICE = re.compile(
    r"(?i)\b(should i|shall i|do you recommend|is (?:this|it) (?:a )?(?:good|safe|worth|better|bad)|"
    r"which (?:loan|card|policy|bank|plan|one) (?:is |should )?(?:better|best|good)|best (?:loan|card|policy)|"
    r"where (?:should|to) invest|invest in|worth (?:it|taking)|"
    r"(?:lena|leni|lu|loon|karna|karu|lagau) chahiye|accha hai kya|sahi hai kya|theek hai kya|le lu kya)\b"
    r"|लेना चाहिए|लूं क्या|सही है क्या|अच्छा है क्या|घ्यावे का|घ्यावा का|चांगले आहे का|योग्य आहे का"
)

MESSAGES = {
    "en": {
        "lead": "Here is what your document says about this:",
        "abstain": "I could not find anything about this in the document. Try other words, or confirm directly with the lender.",
        "advice": "FinePrint explains documents. It cannot tell you whether to take this product. For a recommendation for your situation, speak to a qualified financial adviser.",
        "disclaimer": "This is an explanation of the document, not financial advice.",
    },
    "hi": {
        "lead": "आपके दस्तावेज़ में इस बारे में यह लिखा है:",
        "abstain": "मुझे दस्तावेज़ में इसके बारे में कुछ नहीं मिला। दूसरे शब्दों में पूछें, या सीधे ऋणदाता से पुष्टि करें।",
        "advice": "FinePrint केवल दस्तावेज़ समझाता है। यह उत्पाद लेना है या नहीं, यह सलाह नहीं दे सकता। अपनी स्थिति के लिए किसी योग्य वित्तीय सलाहकार से बात करें।",
        "disclaimer": "यह दस्तावेज़ की व्याख्या है, वित्तीय सलाह नहीं।",
    },
    "mr": {
        "lead": "तुमच्या कागदपत्रात याबद्दल हे लिहिले आहे:",
        "abstain": "कागदपत्रात याबद्दल काहीही सापडले नाही. वेगळ्या शब्दांत विचारा किंवा थेट कर्जदात्याकडे खात्री करा.",
        "advice": "FinePrint फक्त कागदपत्र समजावून सांगते. हे उत्पादन घ्यावे की नाही, याचा सल्ला ते देऊ शकत नाही. तुमच्या परिस्थितीसाठी पात्र आर्थिक सल्लागाराशी बोला.",
        "disclaimer": "हे कागदपत्राचे स्पष्टीकरण आहे, आर्थिक सल्ला नाही.",
    },
    "hinglish": {
        "lead": "Aapke document mein iske baare mein yeh likha hai:",
        "abstain": "Document mein iske baare mein kuch nahi mila. Doosre shabdon mein poochiye, ya lender se seedha confirm kijiye.",
        "advice": "FinePrint sirf document samjhata hai. Yeh product lena chahiye ya nahi, iski salah nahi de sakta. Apni situation ke liye kisi qualified financial adviser se baat kijiye.",
        "disclaimer": "Yeh document ki explanation hai, financial advice nahi.",
    },
}


def is_advice_request(question: str) -> bool:
    return bool(ADVICE.search(question))


def message(language: str, key: str) -> str:
    return MESSAGES.get(language, MESSAGES["en"])[key]
