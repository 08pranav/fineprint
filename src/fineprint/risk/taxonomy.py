"""The 14 risk categories FinePrint knows about.

Each category has: a plain-language label, a default severity, a definition (used verbatim in the
language-model prompt, so rules and model share one definition), weighted regex cues for the
rule-based classifier, and "benign" patterns that mean the clause is actually in the user's favour.

Cue weights: 2 = strong signal on its own, 1 = supporting word. A clause is flagged by rules when
its cue score reaches RULE_THRESHOLD (so one strong cue, or a strong + weak pair, etc.).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

RULE_THRESHOLD = 2


@dataclass(frozen=True)
class Category:
    id: str
    label: str
    severity: str  # high | medium | low
    definition: str
    cues: list[tuple[str, int]]
    benign: list[str] = field(default_factory=list)
    template: str = ""  # offline explanation; {impact} is filled with the rupee headline

    @property
    def cue_patterns(self) -> list[tuple[re.Pattern[str], int]]:
        return [(re.compile(p, re.IGNORECASE), w) for p, w in self.cues]

    @property
    def benign_patterns(self) -> list[re.Pattern[str]]:
        return [re.compile(p, re.IGNORECASE) for p in self.benign]


NEG = r"(?:nil|none|no|not applicable|n\.?a\.?|waived|zero|free|₹\s*0\b|rs\.?\s*0\b)"

CATEGORIES: list[Category] = [
    Category(
        id="prepayment_penalty",
        label="Charge for paying early",
        severity="high",
        definition="A fee or penalty for repaying the loan early, closing it before the end of the tenure "
        "(foreclosure / pre-closure), or making a part-payment.",
        cues=[
            (r"fore-?clos\w*\s+(?:charges?|fees?|penalt\w*)", 2),
            (r"pre-?payment\s+(?:charges?|penalt\w*|fees?)", 2),
            (r"part[- ]?(?:pre)?-?payment\s+(?:charges?|fees?|penalt\w*)", 2),
            (r"pre-?closure\s+(?:charges?|fees?|penalt\w*)", 2),
            (r"interest for a minimum of|minimum (?:of )?\d+ days'? interest", 2),
            (r"(?:close|repay|settle)\w*\s+the\s+loan\s+(?:early|before|prior)", 1),
            (r"fore-?clos|pre-?pay|pre-?clos", 1),
            (r"\b(?:charges?|penalty|fee)\b", 1),
        ],
        benign=[
            rf"\b{NEG}\b[^.]{{0,40}}(?:fore-?clos|pre-?pay|pre-?clos|part[- ]?pay)",
            rf"(?:fore-?clos|pre-?pay|pre-?clos|part[- ]?pay)\w*\s*(?:charges?|fees?|penalty)?\s*[:\-]?\s*{NEG}\b",
            r"without\s+any\s+(?:charges?|penalty|fee)",
        ],
        template="You pay extra if you repay this loan early or close it before the end. {impact}",
    ),
    Category(
        id="floating_rate",
        label="Interest rate can change",
        severity="high",
        definition="The interest rate is floating, linked to a benchmark (repo rate, MCLR, EBLR), or can be "
        "reset or revised by the lender during the loan, so EMIs or tenure can go up.",
        cues=[
            (r"\bfloating\b", 2),
            (r"(?:reset|revis\w*|change|vary|varies|varied|linked)\b[^.]{0,60}\b(?:rate|ROI|interest|benchmark)", 2),
            (r"(?:rate of interest|interest rate|ROI)\b[^.]{0,60}\b(?:reset|revis\w*|subject to change|chang\w*|vary|varies)", 2),
            (r"\b(?:MCLR|repo rate|EBLR|RLLR|external benchmark)\b", 1),
            (r"\bspread\b", 1),
        ],
        benign=[r"\bfixed\b[^.]{0,40}\b(?:entire|full|whole)\s+(?:tenure|term)", rf"\b{NEG}\b[^.]{{0,100}}\bfloating\b"],
        template="Your interest rate is not locked. If it goes up, you pay more. {impact}",
    ),
    Category(
        id="late_payment",
        label="Late payment charges",
        severity="high",
        definition="Charges, penal charges or extra interest when an EMI, bill or premium is paid late or is overdue.",
        cues=[
            (r"(?:late\s+payment|delayed\s+payment|overdue|penal|default)\s+(?:charges?|fees?|interest)", 2),
            (r"penal\s+(?:charges?|interest)", 2),
            (r"(?:delay|late|overdue|default)\w*\b[^.]{0,60}(?:\d+(?:\.\d+)?\s*%|₹|\brs\b)", 2),
            (r"\b(?:late|delay\w*|overdue|default\w*|unpaid)\b", 1),
            (r"\bper\s+month\b|\bp\.?\s?m\.?(?=\W)", 1),
        ],
        benign=[r"\bavoids?\s+(?:any\s+)?(?:late\s+payment|penal)\s+(?:charges?|fees?)"],
        template="If you pay late, extra charges are added. {impact}",
    ),
    Category(
        id="bounce_charge",
        label="EMI bounce charge",
        severity="medium",
        definition="A fee when an auto-debit, NACH/ECS mandate, cheque or standing instruction fails, is "
        "dishonoured or bounces.",
        cues=[
            (r"(?:bounce|bounced|dishono\w*|return\w*)\b[^.]{0,40}\b(?:charges?|fees?)", 2),
            (r"(?:cheque|ECS|NACH|mandate|auto-?debit|standing instruction)\w*\b[^.]{0,60}\b(?:bounce\w*|dishono\w*|return\w*|fail\w*)", 2),
            (r"\b(?:NACH|ECS|mandate|cheque|auto-?debit)\b", 1),
        ],
        template="Each time an EMI auto-debit fails, a fixed charge is added. {impact}",
    ),
    Category(
        id="processing_fee",
        label="Upfront or processing fee",
        severity="medium",
        definition="A one-time processing, documentation, login, platform, convenience, joining or onboarding fee charged when the "
        "loan or product is given, often deducted from the amount you receive and usually non-refundable.",
        cues=[
            (r"(?:processing|origination|documentation|login|administrative|convenience|platform|onboarding|service|joining|activation|registration)\s+(?:fees?|charges?)", 2),
            (r"\bnon-?refundable\b", 1),
            (r"\bupfront\b|\bdeducted from the (?:loan|disburs)", 1),
        ],
        benign=[rf"(?:processing|documentation)\s+(?:fees?|charges?)\s*[:\-]?\s*{NEG}\b"],
        template="A fee is taken when you get this product. {impact}",
    ),
    Category(
        id="auto_renewal",
        label="Renews and charges automatically",
        severity="medium",
        definition="The plan, membership, cover or subscription renews on its own and charges you again unless "
        "you cancel in time.",
        cues=[
            (r"auto(?:matic(?:ally)?)?[- ]?renew\w*", 2),
            (r"renew\w*\s+(?:automatically|on its own)", 2),
            (r"(?:continue to be|will be)\s+(?:charged|debited)\b[^.]{0,80}\b(?:unless|until)\b", 2),
            (r"\bcancel\w*\b", 1),
            (r"\brecurring\b|\bstanding instruction\b", 1),
        ],
        template="This renews and charges you again unless you cancel in time. {impact}",
    ),
    Category(
        id="deferred_interest",
        label="'0% EMI' that is not free",
        severity="high",
        definition="An offer sold as no-cost, zero-cost or 0% EMI where interest is still charged (for example "
        "recovered through a fee or a removed discount), or where interest is charged from the purchase date on "
        "the full amount if a condition is missed.",
        cues=[
            (r"(?:no[- ]cost|zero[- ]cost|0\s*%)\s*EMI\b[^\n]{0,200}\b(?:interest|charged|fee)", 2),
            (r"interest\b[^.]{0,80}\b(?:from the date of (?:purchase|transaction|disbursal)|retrospective\w*|backdated)", 2),
            (r"\bsubvention\b|interest[^.]{0,30}(?:passed on|given|offered) as (?:an? )?(?:upfront )?discount", 2),
            (r"(?:not paid|unpaid|missed|miss)\b[^.]{0,80}\b(?:interest|charged)\b[^.]{0,60}\b(?:entire|full|whole|original)", 2),
            (r"\b(?:no[- ]cost|zero[- ]cost|0\s*%)\s*EMI\b", 1),
            (r"\bpay later\b", 1),
        ],
        template="The offer looks interest-free, but interest can still be charged. {impact}",
    ),
    Category(
        id="bundled_insurance",
        label="Insurance added to your loan",
        severity="medium",
        definition="Insurance or a protection plan that is compulsory, pre-selected, or whose premium is deducted "
        "from or added to the loan amount.",
        cues=[
            (r"(?:insurance|protection plan|credit shield|life cover|loan protect\w*)\b[^.]{0,80}\b(?:mandatory|compulsory|will be (?:added|deducted|included|financed)|deducted from|added to)", 2),
            (r"\bpremium\b[^.]{0,60}\b(?:deducted|financed|added to the loan|included in the loan|form part of the loan)", 2),
            (r"\bmandatory\b[^.]{0,40}\b(?:insurance|cover)", 2),
            (r"(?:bought|purchased|obtained|taken)\s+(?:only\s+)?(?:through|from)\s+the\s+(?:lender|bank|company)'?s?\s+(?:nominated|empanelled|partner)", 2),
            (r"\binsurance\b", 1),
        ],
        benign=[r"\b(?:optional|voluntary|not mandatory|at (?:your|the borrower'?s) option|you may opt out)\b"],
        template="An insurance product is bundled with this loan and you pay for it. {impact}",
    ),
    Category(
        id="unilateral_change",
        label="Terms can change without your consent",
        severity="high",
        definition="The lender or company can change fees, rates, limits or terms at its sole discretion, "
        "at any time, or without prior notice or your consent.",
        cues=[
            (r"(?:sole|absolute|own)\s+discretion", 2),
            (r"reserves?\s+the\s+right\s+to\s+(?:change|modify|amend|alter|revise|vary|reduce|cancel|withdraw)", 2),
            (r"(?:change|modify|amend|alter|revise|vary|reduce|cancel|suspend|withdraw|increase)\w*\b[^.]{0,80}\bwithout\s+(?:any\s+)?(?:prior\s+)?(?:notice|intimation|consent|reason)", 2),
            (r"\bwithout\s+(?:any\s+)?prior\s+(?:notice|intimation)", 2),
            (r"\bat any time\b", 1),
            (r"\bmay (?:change|modify|amend|revise)\b", 1),
        ],
        template="The company can change these terms on its own. Check how much notice you get.",
    ),
    Category(
        id="set_off_lien",
        label="Money can be taken from your other accounts",
        severity="high",
        definition="Right of set-off, lien, or the right to debit or recover dues from any other account, "
        "deposit or salary account you hold, or cross-default across loans.",
        cues=[
            (r"(?:right\s+(?:of|to)\s+)?set[- ]off", 2),
            (r"\blien\b", 2),
            (r"(?:debit|appropriate|adjust|recover)\w*\b[^.]{0,60}\b(?:any (?:other )?account|other accounts?|deposits?|fixed deposit|salary account)", 2),
            (r"cross[- ]?default", 2),
            (r"\brecover\w*\b", 1),
        ],
        template="If you owe money, it can be taken from your other accounts with this lender.",
    ),
    Category(
        id="data_sharing",
        label="Your data is shared",
        severity="medium",
        definition="Your personal data is shared with third parties, partners or affiliates beyond what the "
        "loan needs, used for marketing, or the app may read contacts, SMS, photos or location.",
        cues=[
            (r"(?:share|disclose|transfer|sell)\w*\b[^.]{0,100}\b(?:third[- ]part\w*|partners?|affiliates?|group (?:companies|entities)|marketing)", 2),
            (r"(?:contact|call|message|SMS|WhatsApp|email)\w*\b[^.]{0,60}\b(?:promotional|marketing|offers|cross-sell)", 2),
            (r"(?:access|read|collect)\w*\b[^.]{0,40}\b(?:contacts?|contact list|SMS|messages|location|photos|gallery|call logs?)", 2),
            (r"\bconsent\b", 1),
            (r"\b(?:personal )?data\b|\binformation\b", 1),
        ],
        template="Your personal details may be shared or used beyond this product. You can ask how to opt out.",
    ),
    Category(
        id="insurance_exclusion",
        label="Waiting period, co-pay or exclusion",
        severity="high",
        definition="Insurance terms that reduce or delay a payout: waiting periods, co-payment, sub-limits "
        "(for example on room rent), exclusions, or claims that will not be paid.",
        cues=[
            (r"waiting period", 2),
            (r"\bco-?pay\w*", 2),
            (r"sub-?limit", 2),
            (r"room rent\b[^.]{0,40}\b(?:limit|cap|restrict)\w*", 2),
            (r"(?:expenses|claims?|payout|bill)\b[^.]{0,30}\b(?:paid|reduced|settled)\s+proportionately", 2),
            (r"(?:not|shall not be|will not be)\s+(?:covered|payable|admissible|reimbursed)", 2),
            (r"\bexclu(?:ded|sions?)\b", 2),
            (r"pre-?existing", 1),
            (r"\bclaims?\b|\broom rent\b", 1),
        ],
        template="Your claim could be refused, delayed or only partly paid. {impact}",
    ),
    Category(
        id="recurring_fee",
        label="Annual or recurring fee",
        severity="low",
        definition="Annual, renewal, membership, maintenance or subscription fees charged again every month "
        "or year.",
        cues=[
            (r"(?:annual|renewal|membership|maintenance|subscription|account keeping)\s+(?:fees?|charges?)", 2),
            (r"(?<!penal )(?<!late )(?:fees?|charges?)\b[^.%]{0,30}\b(?:per (?:annum|year|month)|every (?:month|year)|annually|monthly)", 2),
            (r"\bwaived?\b[^.]{0,40}\bspend", 1),
        ],
        benign=[rf"(?:annual|joining|renewal)\s+fees?\s*[:\-]?\s*(?:{NEG}|lifetime free)\b"],
        template="You pay this fee again every period. {impact}",
    ),
    Category(
        id="minimum_due",
        label="Paying only the minimum due",
        severity="medium",
        definition="Credit card or credit line terms where paying only the minimum amount due keeps interest "
        "running on the full balance, often at a high monthly rate.",
        cues=[
            (r"minimum (?:amount )?due", 2),
            (r"(?:interest|finance charges?)\b[^.]{0,140}\b(?:entire|full|whole|total)\s+(?:outstanding|balance|amount)", 2),
            (r"(?:total|full)\s+amount\s+due\s+is\s+not\s+paid|not\s+paid\s+in\s+full", 2),
            (r"\bif (?:only )?(?:a )?part\w*\b[^.]{0,40}\bpaid", 1),
            (r"\brevolv\w*", 1),
        ],
        template="Paying only the minimum keeps the debt growing slowly. {impact}",
    ),
]

BY_ID: dict[str, Category] = {c.id: c for c in CATEGORIES}
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
