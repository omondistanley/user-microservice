"""
Transaction classifier — three-tier pipeline:
  Tier 1  keyword        exact string match in merchant+note text        confidence 1.0
  Tier 2  fuzzy          RapidFuzz token_set_ratio vs canonical names    confidence 0.75-1.0
  Tier 3  embedding      sentence-transformers cosine similarity         confidence 0.60-0.85
  Tier 4  fallback       category_code=8 "Other"                         confidence 0.5

Sprint 2 additions:
  - Tier 3 embedding classifier uses all-MiniLM-L6-v2 (MIT, 80 MB, runs CPU).
  - Embeddings for the 8 category prototype sentences are computed once and
    cached in a module-level dict (thread-safe double-checked lock, same
    pattern as FinBERT singleton).
  - Cosine similarity threshold 0.40 — tuned conservatively to avoid
    cross-category confusion (e.g. "gym" vs "hospital" both map to health-ish).
  - If sentence-transformers is not installed the tier is silently skipped.
"""
import re
import threading
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


@dataclass(frozen=True)
class CategoryRule:
    hint: str
    category_code: int
    category_name: str
    keywords: tuple[str, ...]


@dataclass(frozen=True)
class ClassificationResult:
    flow_type: str
    category_hint: str
    category_code: Optional[int] = None
    category_name: Optional[str] = None
    income_type: Optional[str] = None
    confidence: float = 1.0   # 0.0–1.0; UI shows correction prompt when < 0.75
    source: str = "keyword"   # "keyword" | "fuzzy" | "user_override" | "plaid"


# Apple Pay / card network merchant name prefixes that carry no semantic meaning.
# Stripping these before keyword matching drastically improves accuracy.
# e.g. "SQ *BLUE BOTTLE COFFEE" → "BLUE BOTTLE COFFEE" → matches expense_lifestyle
_MERCHANT_PREFIX_RE = re.compile(
    r'^(?:'
    r'SQ\s*\*|'       # Square POS
    r'TST\*\s*|'      # Toast POS
    r'PP\*|'          # PayPal
    r'PAYPAL\s*\*|'
    r'SP\s*\*|'       # Shopify
    r'AUT\s*\*|'      # Authorize.net
    r'AMZN\s*MKTP\s*|'  # Amazon Marketplace
    r'AMZ\*|'
    r'AMZN\*|'
    r'WHOLEFDS\s*|'   # Whole Foods
    r'APL\*|'         # Apple
    r'GOOGLE\s*\*|'
    r'IN\s*\*|'       # "IN *" (various)
    r'DRI\*|'         # Digital River (software)
    r'DNH\*|'         # Domain/GoDaddy
    r'HTTP\S*\s*|'    # URL-like prefixes
    r'#\S+\s*'        # hash-tag codes (e.g. "#123456 STARBUCKS")
    r')',
    re.IGNORECASE,
)


def normalize_merchant(name: str) -> str:
    """Strip card-network and POS prefixes from a merchant name for better keyword matching."""
    return _MERCHANT_PREFIX_RE.sub("", name).strip()


# ---------------------------------------------------------------------------
# Fuzzy merchant → category mapping (Tier 1.5 — between prefix normalization
# and keyword rules).  Only activated when rapidfuzz is installed.
# Maps canonical merchant names to (category_code, category_name, hint).
# ---------------------------------------------------------------------------
_FUZZY_MERCHANT_MAP: tuple[tuple[str, int, str, str], ...] = (
    # (canonical_name, category_code, category_name, hint)
    ("whole foods", 1, "Food", "expense_groceries"),
    ("trader joes", 1, "Food", "expense_groceries"),
    ("costco wholesale", 1, "Food", "expense_groceries"),
    ("walmart supercenter", 1, "Food", "expense_groceries"),
    ("target store", 1, "Food", "expense_groceries"),
    ("kroger", 1, "Food", "expense_groceries"),
    ("safeway", 1, "Food", "expense_groceries"),
    ("publix", 1, "Food", "expense_groceries"),
    ("starbucks", 5, "Entertainment", "expense_lifestyle"),
    ("dunkin donuts", 5, "Entertainment", "expense_lifestyle"),
    ("mcdonalds", 5, "Entertainment", "expense_lifestyle"),
    ("burger king", 5, "Entertainment", "expense_lifestyle"),
    ("chipotle", 5, "Entertainment", "expense_lifestyle"),
    ("doordash", 5, "Entertainment", "expense_lifestyle"),
    ("uber eats", 5, "Entertainment", "expense_lifestyle"),
    ("grubhub", 5, "Entertainment", "expense_lifestyle"),
    ("netflix", 5, "Entertainment", "expense_lifestyle"),
    ("spotify", 5, "Entertainment", "expense_lifestyle"),
    ("hulu", 5, "Entertainment", "expense_lifestyle"),
    ("uber", 2, "Transportation", "expense_transport"),
    ("lyft", 2, "Transportation", "expense_transport"),
    ("waymo", 2, "Transportation", "expense_transport"),
    ("cvs pharmacy", 6, "Health", "expense_health"),
    ("walgreens", 6, "Health", "expense_health"),
    ("rite aid", 6, "Health", "expense_health"),
    ("verizon wireless", 4, "Utilities", "expense_housing_bills"),
    ("at&t", 4, "Utilities", "expense_housing_bills"),
    ("t-mobile", 4, "Utilities", "expense_housing_bills"),
    ("xfinity", 4, "Utilities", "expense_housing_bills"),
    ("con edison", 4, "Utilities", "expense_housing_bills"),
)

_FUZZY_THRESHOLD = 82  # score out of 100; tuned to avoid false positives


def _fuzzy_classify(text: str) -> Optional["ClassificationResult"]:
    """
    Fuzzy-match `text` against canonical merchant names using RapidFuzz token_set_ratio.
    Returns a ClassificationResult with source='fuzzy' and confidence proportional
    to the match score, or None if rapidfuzz is not installed or no match exceeds threshold.

    token_set_ratio handles word reordering and partial overlaps well
    (e.g. "WHOLEFDS MKT #123" vs "whole foods").
    """
    try:
        from rapidfuzz import fuzz
    except ImportError:
        return None

    best_score = 0.0
    best_entry = None
    for entry in _FUZZY_MERCHANT_MAP:
        canonical = entry[0]
        score = fuzz.token_set_ratio(text, canonical)
        if score > best_score:
            best_score = score
            best_entry = entry

    if best_entry is None or best_score < _FUZZY_THRESHOLD:
        return None

    canonical, category_code, category_name, hint = best_entry
    # Map score 82–100 → confidence 0.75–1.0
    confidence = round(0.75 + (best_score - _FUZZY_THRESHOLD) / (100 - _FUZZY_THRESHOLD) * 0.25, 4)
    return ClassificationResult(
        flow_type="expense",
        category_hint=hint,
        category_code=category_code,
        category_name=category_name,
        confidence=confidence,
        source="fuzzy",
    )


# ---------------------------------------------------------------------------
# Tier 3: sentence-transformer embedding classifier (Sprint 2)
# ---------------------------------------------------------------------------
# Uses all-MiniLM-L6-v2 (MIT licence, ~80 MB, CPU-friendly, 384-dim embeddings).
# One representative sentence per expense category is embedded once at startup
# and cached.  At inference we embed the merchant+note text and pick the
# category with highest cosine similarity above a threshold.
#
# Thread safety: double-checked lock (same pattern as FinBERT singleton).
# Graceful degradation: if sentence-transformers is not installed, this tier
# returns None and the pipeline falls through to the "Other" fallback.
# ---------------------------------------------------------------------------

_EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
_EMBEDDING_THRESHOLD = 0.40   # cosine similarity; below this → skip, don't guess

# One representative sentence per category — chosen to maximise separation.
# These are NOT merchant names; they describe what the category covers so the
# model's semantic space aligns well with everyday language.
_CATEGORY_PROTOTYPES: tuple[tuple[int, str, str, str], ...] = (
    (1, "Food",          "expense_groceries",      "grocery store supermarket food shopping fresh produce"),
    (2, "Transportation","expense_transport",       "ride share taxi bus train subway commute fuel parking"),
    (4, "Utilities",     "expense_housing_bills",  "rent electricity water internet phone bill utility mortgage"),
    (5, "Entertainment", "expense_lifestyle",      "restaurant coffee bar movie streaming music gym entertainment dining"),
    (6, "Health",        "expense_health",         "pharmacy hospital doctor dentist medical insurance prescription clinic"),
    (7, "Shopping",      "expense_shopping",       "clothing online shopping retail department store fashion accessories"),
    (8, "Other",         "expense_education",      "school tuition course online learning university books education"),
    (8, "Other",         "expense_fees_transfers", "bank fee wire transfer atm withdrawal service charge"),
)

_embedding_lock = threading.Lock()
_embedding_model = None          # SentenceTransformer instance or False (failed)
_prototype_embeddings = None     # np.ndarray shape (N, 384)


def _get_embedding_model():
    """Return the SentenceTransformer singleton, loading on first call."""
    global _embedding_model
    if _embedding_model is None:
        with _embedding_lock:
            if _embedding_model is None:
                try:
                    from sentence_transformers import SentenceTransformer
                    _embedding_model = SentenceTransformer(_EMBEDDING_MODEL_NAME)
                    _build_prototype_embeddings(_embedding_model)
                except Exception:
                    _embedding_model = False  # sentinel: tried and failed
    return _embedding_model if _embedding_model is not False else None


def _build_prototype_embeddings(model) -> None:
    """Encode all prototype sentences and store in module-level cache."""
    global _prototype_embeddings
    sentences = [p[3] for p in _CATEGORY_PROTOTYPES]
    _prototype_embeddings = model.encode(sentences, convert_to_numpy=True, normalize_embeddings=True)


def _embedding_classify(text: str) -> Optional["ClassificationResult"]:
    """
    Encode `text` and find the closest category prototype by cosine similarity.
    Returns ClassificationResult with source='embedding', or None if the model
    is unavailable or no prototype exceeds _EMBEDDING_THRESHOLD.

    Confidence is mapped linearly from [threshold, 1.0] → [0.60, 0.85].
    Capped at 0.85 (below keyword/fuzzy) to reflect that embedding similarity
    is less precise than exact matches.
    """
    model = _get_embedding_model()
    if model is None or _prototype_embeddings is None:
        return None
    if not text or not text.strip():
        return None
    try:
        import numpy as np
        vec = model.encode([text.strip()[:256]], convert_to_numpy=True, normalize_embeddings=True)
        # cosine similarity = dot product when both vectors are L2-normalised
        sims = (_prototype_embeddings @ vec.T).flatten()
        best_idx = int(np.argmax(sims))
        best_sim = float(sims[best_idx])
        if best_sim < _EMBEDDING_THRESHOLD:
            return None
        category_code, category_name, hint, _ = _CATEGORY_PROTOTYPES[best_idx]
        # Map [threshold, 1.0] → [0.60, 0.85]
        span = 1.0 - _EMBEDDING_THRESHOLD
        confidence = round(0.60 + (best_sim - _EMBEDDING_THRESHOLD) / span * 0.25, 4)
        confidence = min(0.85, confidence)
        return ClassificationResult(
            flow_type="expense",
            category_hint=hint,
            category_code=category_code,
            category_name=category_name,
            confidence=confidence,
            source="embedding",
        )
    except Exception:
        return None


INCOME_KEYWORDS: tuple[str, ...] = (
    "salary",
    "payroll",
    "paycheck",
    "bonus",
    "allowance",
    "stipend",
    "interest",
    "dividend",
    "refund",
    "rebate",
    "cashback",
    "cash back",
    "payout",
    "invoice paid",
    "direct deposit",
    "dd ",       # common UK bank abbreviation for Direct Deposit
    "zelle from",
    "venmo from",
    "ach credit",
    "wire credit",
    "wire transfer in",
)


EXPENSE_CATEGORY_RULES: tuple[CategoryRule, ...] = (
    CategoryRule(
        hint="expense_groceries",
        category_code=1,
        category_name="Food",
        keywords=(
            "supermarket",
            "grocery",
            "grocer",
            "quickmart",
            "carrefour",
            "naivas",
            "whole foods",
            "wholefds",
            "trader joe",
            "costco",
            "aldi",
            "walmart",
            "target",
            "food",
            "butcher",
            "deli",
            "market",
            "fresh market",
            "stop & shop",
            "stop and shop",
            "shoprite",
            "kroger",
            "safeway",
            "publix",
            "h-e-b",
            "wegmans",
            "sprouts",
            "fairway",
            "key food",
            "associated supermarket",
            "western beef",
        ),
    ),
    CategoryRule(
        hint="expense_transport",
        category_code=2,
        category_name="Transportation",
        keywords=(
            "uber",
            "lyft",
            "bolt",
            "fuel",
            "gas",
            "petrol",
            "diesel",
            "matatu",
            "bus",
            "taxi",
            "parking",
            "toll",
            "mta",
            "subway",
            "metro",
            "train",
            "path",
            "nj transit",
            "omny",
            "airtrain",
            "tram",
            "ferry",
            "via ride",
            "via transport",
            "rideshare",
            "waymo",
            "yellow cab",
            "juno",
            "curb",
            "e-zpass",
            "ezpass",
            "port authority",
            "njt",
            "lirr",
            "metro-north",
            "amtrak",
            "greyhound",
            "enterprise rent",
            "hertz",
            "avis",
            "budget car",
            "zipcar",
            "citibike",
            "lime",
            "bird scooter",
        ),
    ),
    CategoryRule(
        hint="expense_housing_bills",
        category_code=4,
        category_name="Utilities",
        keywords=(
            "rent",
            "landlord",
            "electricity",
            "power",
            "water",
            "internet",
            "wifi",
            "airtime",
            "utility",
            "utilities",
            "gas bill",
            "heat",
            "coned",
            "con ed",
            "national grid",
            "verizon",
            "att",
            "spectrum",
            "xfinity",
            "t-mobile",
            "tmobile",
            "sprint",
            "cricket wireless",
            "boost mobile",
            "metro pcs",
            "optimum",
            "cablevision",
            "pseg",
            "pge",
            "pg&e",
            "duke energy",
            "dominion energy",
            "consolidated edison",
            "mortgage",
            "hoa",
        ),
    ),
    CategoryRule(
        hint="expense_lifestyle",
        category_code=5,
        category_name="Entertainment",
        keywords=(
            "restaurant",
            "cafe",
            "coffee",
            "bar",
            "pub",
            "netflix",
            "spotify",
            "showmax",
            "movie",
            "cinema",
            "entertainment",
            "hulu",
            "disney+",
            "apple music",
            "hbo",
            "starbucks",
            "dunkin",
            "mcdonald",
            "burger king",
            "wendy",
            "chipotle",
            "panera",
            "chick-fil-a",
            "shake shack",
            "five guys",
            "panda express",
            "subway sandwiches",
            "domino",
            "pizza hut",
            "papa john",
            "doordash",
            "grubhub",
            "ubereats",
            "instacart",
            "seamless",
            "prime video",
            "paramount",
            "peacock",
            "apple tv",
            "youtube premium",
            "twitch",
            "steam",
            "playstation",
            "xbox",
            "nintendo",
            "audible",
            "kindle",
            "amazon prime",
            "gym",
            "fitness",
            "planet fitness",
            "equinox",
            "la fitness",
            "soulcycle",
            "peloton",
            "fandango",
            "amc theatre",
            "regal cinema",
        ),
    ),
    CategoryRule(
        hint="expense_health",
        category_code=6,
        category_name="Health",
        keywords=(
            "hospital",
            "pharmacy",
            "clinic",
            "doctor",
            "insurance",
            "medical",
            "med",
            "urgent care",
            "copay",
            "prescription",
            "cvs",
            "walgreens",
            "rite aid",
            "duane reade",
            "optometrist",
            "dentist",
            "dental",
            "orthodont",
            "vision",
            "lab",
            "quest diagnostics",
            "labcorp",
            "health",
            "aetna",
            "cigna",
            "united health",
            "blue cross",
            "anthem",
            "humana",
            "kaiser",
        ),
    ),
    CategoryRule(
        hint="expense_education",
        category_code=8,
        category_name="Other",
        keywords=(
            "school",
            "tuition",
            "books",
            "course",
            "udemy",
            "coursera",
            "edx",
            "training",
            "certification",
            "workshop",
            "university",
            "college",
            "student loan",
            "skillshare",
            "pluralsight",
            "linkedin learning",
            "khan academy",
        ),
    ),
    CategoryRule(
        hint="expense_fees_transfers",
        category_code=8,
        category_name="Other",
        keywords=(
            "transfer",
            "bank fee",
            "withdrawal",
            "atm fee",
            "wire fee",
            "service fee",
            "m-pesa charge",
            "processing fee",
            "monthly fee",
            "annual fee",
            "late fee",
            "overdraft",
            "zelle to",
            "venmo to",
            "cashapp",
            "western union",
            "moneygram",
            "paypal transfer",
        ),
    ),
)


def classify_transaction(
    amount: Decimal,
    merchant: Optional[str],
    note: Optional[str] = None,
    flow_type_hint: Optional[str] = None,
) -> ClassificationResult:
    clean_merchant = normalize_merchant(merchant or "")
    text = f"{clean_merchant} {note or ''}".strip().lower()
    hinted = (flow_type_hint or "").strip().lower()

    if amount < 0:
        return _classify_expense(text)

    if hinted in {"income", "expense"}:
        if hinted == "income":
            return _classify_income(text)
        return _classify_expense(text)

    if any(k in text for k in INCOME_KEYWORDS):
        return _classify_income(text)
    return _classify_expense(text)


def _classify_income(text: str) -> ClassificationResult:
    income_type = "other"
    if any(k in text for k in ("salary", "payroll", "allowance", "stipend", "bonus")):
        income_type = "salary"
    elif any(k in text for k in ("dividend",)):
        income_type = "dividend"
    elif any(k in text for k in ("interest",)):
        income_type = "interest"
    elif any(k in text for k in ("invoice", "freelance", "contract", "consulting", "gig")):
        income_type = "freelance"
    return ClassificationResult(
        flow_type="income",
        category_hint="income_salary_other",
        income_type=income_type,
        confidence=1.0,
        source="keyword",
    )


def _classify_expense(text: str) -> ClassificationResult:
    # Tier 1: exact keyword match (highest confidence)
    for rule in EXPENSE_CATEGORY_RULES:
        if any(keyword in text for keyword in rule.keywords):
            return ClassificationResult(
                flow_type="expense",
                category_hint=rule.hint,
                category_code=rule.category_code,
                category_name=rule.category_name,
                confidence=1.0,
                source="keyword",
            )

    # Tier 2: fuzzy merchant match (handles typos, truncated POS names)
    fuzzy_result = _fuzzy_classify(text)
    if fuzzy_result is not None:
        return fuzzy_result

    # Tier 3: sentence-transformer embedding (generalises to unseen merchants)
    embedding_result = _embedding_classify(text)
    if embedding_result is not None:
        return embedding_result

    # Tier 4: fallback
    return ClassificationResult(
        flow_type="expense",
        category_hint="expense_other",
        category_code=8,
        category_name="Other",
        confidence=0.5,
        source="keyword",
    )
