"""Domain Adapter Service: Explicit @tag parsing, intelligent clinical intent classification,
and 512-token constrained MedGemma multi-adapter connector with seamless fallback.
"""

import logging
import re
from typing import Optional, Tuple
import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Canonical domain adapters with comprehensive clinical & natural language keyword mapping
CANONICAL_ADAPTERS: dict[str, dict] = {
    "radiology": {
        "display_name": "Radiology",
        "description": "Medical imaging, X-rays, CT scans, MRI, ultrasound, and radiological findings",
        "aliases": ["radiology", "rad", "imaging", "mri", "ct"],
        "keywords": [
            "x-ray", "xray", "x-rays", "ct scan", "ct scans", "mri", "mris", "ultrasound", "ultrasounds",
            "radiograph", "radiography", "radiological", "imaging", "tomography", "pet scan", "pet scans",
            "sonogram", "sonography", "mammogram", "mammography", "contrast scan", "opacity", "nodule",
            "nodules", "fracture", "fractured", "broken bone", "dislocation", "radiologist"
        ],
    },
    "dermatology": {
        "display_name": "Dermatology",
        "description": "Skin, hair, and nail conditions, rashes, lesions, moles, eczema, psoriasis, dermoscopy",
        "aliases": ["dermatology", "derma", "skin"],
        "keywords": [
            "skin", "rash", "rashes", "patch", "patches", "red patch", "red patches", "itch", "itching",
            "itchy", "dry skin", "flaking", "peeling", "scales", "scaling", "scaly", "bump", "bumps",
            "mole", "moles", "lesion", "lesions", "skin lesion", "hives", "blister", "blisters", "acne",
            "pimple", "pimples", "breakout", "breakouts", "boil", "boils", "cyst", "cysts", "abscess",
            "wart", "warts", "bruise", "bruising", "eczema", "psoriasis", "dermatitis", "urticaria",
            "melanoma", "dermoscopy", "erythema", "erythematous", "pruritus", "pruritic", "shingles",
            "rosacea", "alopecia", "hair loss", "scalp", "nail fungus", "onychomycosis"
        ],
    },
    "pathology": {
        "display_name": "Pathology",
        "description": "Tissue histology, biopsy interpretation, cell pathology, and laboratory specimens",
        "aliases": ["pathology", "path", "biopsy", "histology"],
        "keywords": [
            "biopsy", "biopsies", "histology", "histopathology", "tissue specimen", "tissue sample",
            "pathology", "pathological", "pathologist", "malignancy", "malignant", "benign",
            "cellular morphology", "carcinoma", "cytology", "cytopathology", "neoplasm", "tumor",
            "atypia", "atypical cells", "fine needle aspiration", "fna", "margins", "specimen",
            "immunohistochemistry", "ihc"
        ],
    },
    "ophthalmology": {
        "display_name": "Ophthalmology",
        "description": "Eye and vision conditions, retinal health, fundus imaging, OCT scans, ocular disease",
        "aliases": ["ophthalmology", "opht", "eye", "vision"],
        "keywords": [
            "eye", "eyes", "eyeball", "eyeballs", "eyelid", "eyelids", "vision", "seeing", "sight",
            "glassy", "glassy eyes", "burning eyes", "burning eye", "itchy eyes", "watery eyes", "tearing",
            "tears", "red eye", "red eyes", "pink eye", "blurred vision", "blurry vision", "blurry",
            "double vision", "dry eye", "dry eyes", "eye pain", "floaters", "flashes", "blind spot",
            "blindness", "stye", "cornea", "corneal", "retina", "retinal", "pupil", "pupils", "iris",
            "lens", "sclera", "conjunctiva", "conjunctivitis", "cataract", "cataracts", "glaucoma",
            "macular", "macula", "fundus", "fundoscopy", "oct scan", "visual acuity", "optometry",
            "photophobia", "blepharitis", "astigmatism", "myopia", "ocular"
        ],
    },
    "chest_xray": {
        "display_name": "Chest X-Ray",
        "description": "Chest radiographs and thoracic imaging, lung fields, pneumothorax, pulmonary opacities",
        "aliases": ["chest_xray", "chestxray", "cxr", "chest_rad"],
        "keywords": [
            "chest x-ray", "chest xray", "cxr", "lung", "lungs", "pulmonary", "pneumonia", "bronchitis",
            "cough", "coughing", "phlegm", "sputum", "coughing blood", "hemoptysis", "wheezing", "wheeze",
            "shortness of breath", "sob", "difficulty breathing", "breathless", "breathlessness",
            "asthma", "copd", "emphysema", "pneumothorax", "pleural effusion", "consolidation",
            "lung field", "lung fields", "cardiomegaly", "pulmonary opacity", "opacities", "infiltrate",
            "infiltrates", "atelectasis", "respiratory", "alveoli"
        ],
    },
    "cardiology": {
        "display_name": "Cardiology",
        "description": "Cardiovascular medicine, ECG interpretation, arrhythmias, heart failure, and coronary disease",
        "aliases": ["cardiology", "cardio", "heart", "ecg"],
        "keywords": [
            "heart", "cardiac", "cardiovascular", "heart racing", "racing heart", "heartbeat", "heart beat",
            "heart beats", "heart rate", "pulse", "rapid pulse", "pulse rising", "sweats", "sweating",
            "diaphoresis", "cold sweat", "palpitation", "palpitations", "chest pain", "chest tightness",
            "chest pressure", "angina", "ecg", "ekg", "arrhythmia", "atrial fibrillation", "afib",
            "tachycardia", "bradycardia", "troponin", "ejection fraction", "myocardial", "infarction",
            "heart attack", "heart failure", "chf", "hypertension", "high blood pressure", "murmur",
            "st-elevation", "stemi", "coronary", "artery", "pericarditis", "myocarditis", "aorta", "aortic"
        ],
    },
    "clinical_reasoning": {
        "display_name": "Clinical Reasoning",
        "description": "Structured differential diagnosis, symptom synthesis, and step-by-step diagnostic reasoning",
        "aliases": ["clinical_reasoning", "reasoning", "differential", "diagnosis"],
        "keywords": [
            "differential diagnosis", "step-by-step reasoning", "rule out", "clinical reasoning",
            "diagnostic workup", "etiology", "differential", "what could this be", "possible causes",
            "synthesize", "diagnostic reasoning", "workup", "investigations needed"
        ],
    },
    "general": {
        "display_name": "General Medicine",
        "description": "Standard multimodal medical LLM for general clinical queries and primary care",
        "aliases": ["general", "base", "primary_care"],
        "keywords": [],
    },
}

# Regex to detect explicit @adapter tag (e.g. @radiology, @derma, @pathology)
TAG_REGEX = re.compile(r"(?:^|\s)@([a-zA-Z0-9_]+)(?:\s|$)", re.IGNORECASE)


def parse_explicit_adapter_tag(message: str) -> Tuple[Optional[str], str]:
    """Extracts explicit @adapter tag and returns (adapter_key, clean_message).
    If no valid tag is found, returns (None, original_message).
    """
    match = TAG_REGEX.search(message)
    if not match:
        return None, message

    raw_tag = match.group(1).lower().strip()
    # Find matching canonical adapter by alias
    for key, meta in CANONICAL_ADAPTERS.items():
        if raw_tag in meta["aliases"] or raw_tag == key:
            # Strip the tag from the message
            clean_message = TAG_REGEX.sub(" ", message).strip()
            clean_message = re.sub(r"\s+", " ", clean_message)
            return key, clean_message

    return None, message


def score_adapter_keywords(message: str) -> Tuple[str, int, dict[str, int]]:
    """Scores message text against canonical specialty vocabulary using word-boundary matching."""
    lower_msg = message.lower()
    scores: dict[str, int] = {}

    for key, meta in CANONICAL_ADAPTERS.items():
        if key == "general":
            continue
        score = 0
        for kw in meta["keywords"]:
            pattern = r"\b" + re.escape(kw) + r"\b"
            matches = len(re.findall(pattern, lower_msg))
            if matches > 0:
                # Multi-word clinical phrases get higher weight than generic words
                weight = 3 if " " in kw else (2 if len(kw) > 5 else 1)
                score += matches * weight
        if score > 0:
            scores[key] = score

    if scores:
        best_adapter = max(scores, key=scores.get)
        return best_adapter, scores[best_adapter], scores

    return "general", 0, {}


def classify_implicit_adapter(message: str) -> str:
    """Synchronous keyword-based classifier for backwards compatibility."""
    best_adapter, _, _ = score_adapter_keywords(message)
    return best_adapter


async def classify_adapter_with_llm(query: str) -> Optional[str]:
    """Zero-shot AI clinical classifier for ambiguous queries or queries with missing keyword hits.
    Uses Gemini 2.5 Flash / Groq to accurately classify into canonical domain adapters.
    """
    from app.services import model_router

    prompt = f"""You are a medical specialty router. Classify the user clinical query into EXACTLY ONE of these categories:
- radiology (medical imaging, CT scan, MRI, ultrasound, bone scans)
- dermatology (skin, rash, red patch, itching, moles, eczema, acne, lesions)
- pathology (biopsy, tissue specimen, cytology, histology, lab specimen)
- ophthalmology (eyes, vision, burning eyes, glassy eyes, cataracts, retina)
- chest_xray (lungs, coughing, wheezing, shortness of breath, chest x-ray)
- cardiology (heart, chest pain, palpitations, heart racing, blood pressure, ECG)
- clinical_reasoning (complex differential diagnosis, diagnostic workup)
- general (primary care, wellness, vitamins, medication schedules, non-specialized)

Query: "{query}"
Return ONLY the category name in lowercase without any explanation or punctuation."""

    try:
        reply = await model_router.complete_gemini(user=prompt)
        cat = reply.strip().lower().replace("-", "_").replace(" ", "_")
        valid = {"radiology", "dermatology", "pathology", "ophthalmology", "chest_xray", "cardiology", "clinical_reasoning", "general"}
        for v in valid:
            if v in cat:
                return v
    except Exception as e:
        logger.warning(f"AI adapter classification error: {e}")

    return None


async def resolve_adapter(message: str, explicit_specialty: Optional[str] = None) -> Tuple[str, str, bool]:
    """Resolves adapter through:
    1. Explicit @tag in message text (e.g. "@dermatology Check this patch")
    2. Explicit UI specialty dropdown selection
    3. Fast clinical keyword pattern matching with word boundaries
    4. Fast Zero-Shot AI intent classification for ambiguous queries

    Returns: (adapter_key, clean_message, is_explicit)
    """
    # 1. Explicit @tag in message
    explicit_tag, clean_msg = parse_explicit_adapter_tag(message)
    if explicit_tag:
        return explicit_tag, clean_msg, True

    # 2. Explicit UI selection (only lock if user selected a specific non-general specialty)
    if explicit_specialty and explicit_specialty.lower().strip() not in (
        "general", "general medicine", "general_medicine", "auto", "default", "none", ""
    ):
        clean_spec = explicit_specialty.lower().replace(" ", "_").replace("-", "_")
        for key, meta in CANONICAL_ADAPTERS.items():
            if clean_spec in meta["aliases"] or clean_spec == key or explicit_specialty.lower() == meta["display_name"].lower():
                return key, message, True

    # 3. Fast keyword analysis
    best_adapter, top_score, all_scores = score_adapter_keywords(message)
    
    # If high-confidence keyword match (score >= 3 or unambiguous single candidate)
    if top_score >= 3:
        return best_adapter, message, False

    # 4. Zero-Shot AI Classification for ambiguous queries or queries with low/no keyword matches
    words = message.strip().split()
    if len(words) >= 3:
        ai_adapter = await classify_adapter_with_llm(message)
        if ai_adapter and ai_adapter in CANONICAL_ADAPTERS:
            return ai_adapter, message, False

    # Fallback to best keyword hit or general
    return best_adapter, message, False


async def call_remote_medgemma_adapter(
    adapter: str,
    question: str,
    timeout_seconds: float = 120.0,
) -> Optional[str]:
    """Sends payload to remote MedGemma multi-adapter ngrok service.
    Payload: {"adapter": adapter, "question": question}
    Returns response text or None on failure/unconfigured.
    """
    if not settings.medgemma_adapter_url:
        return None

    url = f"{settings.medgemma_adapter_url.rstrip('/')}/chat"
    payload = {
        "adapter": adapter,
        "question": question,
    }
    headers = {
        "ngrok-skip-browser-warning": "true",
        "User-Agent": "MedSysAI/1.0",
        "Content-Type": "application/json",
    }

    try:
        # 5s connect timeout to detect if tunnel is down, 60s read timeout for GPU model generation
        timeout = httpx.Timeout(timeout_seconds, connect=5.0)
        async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
            res = await client.post(url, json=payload)
            if res.status_code == 200:
                data = res.json()
                if isinstance(data, dict):
                    return data.get("response") or data.get("answer") or data.get("content") or data.get("generated_text") or str(data)
                elif isinstance(data, str):
                    return data
            else:
                logger.info(f"Remote MedGemma adapter returned status {res.status_code}, falling back.")
    except Exception as e:
        logger.info(f"Remote MedGemma adapter request failed or timed out: {e}")

    return None


def get_adapter_display_name(adapter_key: str) -> str:
    """Returns friendly display name for UI badge."""
    meta = CANONICAL_ADAPTERS.get(adapter_key)
    return meta["display_name"] if meta else "General Medicine"


def build_specialty_prompt_preamble(adapter_key: str) -> str:
    """Generates a compact, 512-token constrained domain specialty prompt."""
    if adapter_key == "general" or adapter_key not in CANONICAL_ADAPTERS:
        return (
            "DOMAIN: GENERAL MEDICINE & CLINICAL TRIAGE\n"
            "Provide high-density, actionable clinical guidance with clear explanations and safety cautions.\n"
            "Keep response concise and strictly within 512 tokens.\n\n"
        )

    meta = CANONICAL_ADAPTERS[adapter_key]
    name = meta["display_name"]
    desc = meta["description"]

    return (
        f"SPECIALTY ADAPTER: {name.upper()}\n"
        f"Domain Scope: {desc}.\n"
        f"Clinical Instructions:\n"
        f"1. Focus specifically through the lens of {name}.\n"
        f"2. Structure with: Key Findings/Differentials, Clinical Interpretation, and Recommended Next Steps.\n"
        f"3. Strict token budget: Deliver dense, high-yield answers fitting completely within 512 tokens without cut-off.\n\n"
    )
