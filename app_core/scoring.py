"""Parsing, scores e estimativa financeira do app."""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

GIANT_DEVELOPER_KEYWORDS = {
    "google", "meta", "facebook", "instagram", "whatsapp", "microsoft", "amazon", "netflix", "spotify",
    "bytedance", "tiktok", "telegram", "snap", "disney", "samsung", "xiaomi", "uber", "booking",
    "airbnb", "duolingo", "roblox", "supercell", "king", "electronic arts", "activision", "mojang",
    "tencent", "garena", "epic games", "paypal", "nubank", "picpay", "mercado livre", "meli", "ifood",
    "shopee", "shein", "temu", "aliexpress", "openai", "anthropic", "c6 bank", "bradesco", "itau",
    "itaú", "santander", "banco do brasil", "caixa econômica", "globo", "magalu", "netshoes",
}

STOPWORDS = {
    "para", "com", "que", "uma", "por", "não", "sim", "mas", "dos", "das", "the", "and", "you", "app",
    "muito", "mais", "bom", "boa", "ele", "ela", "tem", "meu", "minha", "seu", "sua", "foi", "ser", "ter",
    "this", "that", "for", "not", "are", "but", "have", "has", "very", "really", "good", "great",
    "application", "aplicativo", "jogo", "game", "android", "play", "store", "google",
}

CATEGORY_ARPU_HINTS = {
    "FINANCE": 1.15,
    "BUSINESS": 1.05,
    "PRODUCTIVITY": 0.95,
    "HEALTH_AND_FITNESS": 0.75,
    "EDUCATION": 0.55,
    "DATING": 1.20,
    "GAME_CASINO": 1.35,
    "GAME_ROLE_PLAYING": 1.10,
    "GAME_STRATEGY": 1.00,
    "GAME_PUZZLE": 0.45,
    "GAME_CASUAL": 0.38,
}


def parse_num(valor: Any) -> Optional[float]:
    if valor is None or valor == "":
        return None
    if isinstance(valor, bool):
        return 1.0 if valor else 0.0
    if isinstance(valor, (int, float)):
        if math.isnan(float(valor)):
            return None
        return float(valor)
    s = str(valor).strip().replace("+", "")
    s = s.replace("R$", "").replace("US$", "").replace("€", "").replace("\xa0", " ")
    if s.count(",") == 1 and s.count(".") >= 1:
        s = s.replace(".", "").replace(",", ".")
    elif s.count(",") == 1:
        s = s.replace(",", ".")
    match = re.search(r"-?\d+(?:\.\d+)?", s)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def parse_installs(valor: Any) -> Optional[int]:
    if valor is None or valor == "":
        return None
    if isinstance(valor, bool):
        return 1 if valor else 0
    if isinstance(valor, (int, float)):
        return int(valor)
    s = str(valor).strip().lower().replace("+", "").replace("\xa0", " ")
    multiplicador = 1
    if "bil" in s or "bi" in s or re.search(r"\bb\b", s):
        multiplicador = 1_000_000_000
    elif "milh" in s or "mi" in s or re.search(r"\bm\b", s):
        multiplicador = 1_000_000
    elif "mil" in s or re.search(r"\bk\b", s):
        multiplicador = 1_000
    nums = re.sub(r"[^0-9,\.]+", "", s)
    if not nums:
        return None
    if nums.count(".") + nums.count(",") > 1:
        nums = re.sub(r"[^0-9]", "", nums)
    else:
        nums = nums.replace(",", ".")
    try:
        return int(float(nums) * multiplicador)
    except ValueError:
        return None


def date_from_google(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        try:
            return datetime.fromtimestamp(timestamp).strftime("%d/%m/%Y")
        except Exception:
            return str(value)
    return str(value)


def days_since_google_date(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    now = datetime.now(timezone.utc)
    dt: Optional[datetime] = None
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 10_000_000_000:
            ts /= 1000
        try:
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        except Exception:
            return None
    elif isinstance(value, str):
        value = value.strip()
        # O google-play-scraper geralmente retorna timestamp, mas deixo vários formatos aqui.
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%b %d, %Y", "%B %d, %Y", "%d de %B de %Y", "%d de %b. de %Y"):
            try:
                dt = datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
                break
            except ValueError:
                pass
    if not dt:
        return None
    return max(0, (now - dt).days)


def app_link(app_data: Dict[str, Any]) -> str:
    url = app_data.get("url")
    if url:
        return str(url)
    app_id = app_data.get("appId") or app_data.get("app_id")
    if app_id:
        return f"https://play.google.com/store/apps/details?id={app_id}"
    return "#"


def get_installs(app_data: Dict[str, Any]) -> int:
    for key in ("realInstalls", "real_installs", "minInstalls", "min_installs", "installs"):
        n = parse_installs(app_data.get(key))
        if n is not None:
            return n
    return 0


def get_score(app_data: Dict[str, Any]) -> float:
    for key in ("score", "rating"):
        n = parse_num(app_data.get(key))
        if n is not None:
            return n
    return 0.0


def get_ratings(app_data: Dict[str, Any]) -> int:
    for key in ("ratings", "reviews"):
        n = parse_installs(app_data.get(key))
        if n is not None:
            return n
    return 0


def boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "sim", "yes", "y", "s"}


def is_giant(app_data: Dict[str, Any]) -> bool:
    installs = get_installs(app_data)
    dev = str(app_data.get("developer") or "").lower()
    title = str(app_data.get("title") or "").lower()
    app_id = str(app_data.get("appId") or "").lower()
    giant_by_name = any(k in dev or k in title or k in app_id for k in GIANT_DEVELOPER_KEYWORDS)
    return installs >= 50_000_000 or giant_by_name


def extract_keywords(text: str, limit: int = 12) -> List[str]:
    words = re.findall(r"[A-Za-zÀ-ÿ0-9]{3,}", (text or "").lower())
    counts: Dict[str, int] = {}
    for w in words:
        if w in STOPWORDS or w.isdigit():
            continue
        counts[w] = counts.get(w, 0) + 1
    return [w for w, _ in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:limit]]


def compute_scores(app_data: Dict[str, Any]) -> Dict[str, Any]:
    installs = get_installs(app_data)
    ratings = get_ratings(app_data)
    score = get_score(app_data)
    updated_days = days_since_google_date(app_data.get("updated"))
    released_days = days_since_google_date(app_data.get("released"))
    giant = is_giant(app_data)

    # Indie: pouca escala + dev não gigante + sinais de app enxuto.
    indie = 100
    if installs >= 5_000_000:
        indie -= 55
    elif installs >= 1_500_000:
        indie -= 35
    elif installs >= 500_000:
        indie -= 20
    elif installs < 100_000:
        indie += 8
    if ratings >= 100_000:
        indie -= 30
    elif ratings < 5_000:
        indie += 8
    if giant:
        indie -= 70
    dev_site = str(app_data.get("developerWebsite") or app_data.get("developer_website") or "")
    dev_email = str(app_data.get("developerEmail") or app_data.get("developer_email") or "")
    if dev_site and not any(k in dev_site.lower() for k in GIANT_DEVELOPER_KEYWORDS):
        indie += 4
    if dev_email and any(p in dev_email.lower() for p in ("gmail.com", "outlook.com", "yahoo.com", "proton", "hotmail")):
        indie += 10
    indie_score = max(0, min(100, int(indie)))

    # Crescimento: app novo/atualizado + boa nota + reviews suficientes, sem gigante dominar.
    growth = 0
    if updated_days is not None:
        growth += max(0, 32 - min(updated_days, 365) / 365 * 32)
    if released_days is not None:
        if released_days < 365:
            growth += 24
        elif released_days < 900:
            growth += 12
    growth += min(18, math.log10(max(ratings, 1)) * 4)
    if score >= 4.6:
        growth += 16
    elif score >= 4.3:
        growth += 10
    elif score < 3.6 and score > 0:
        growth -= 10
    if giant:
        growth -= 20
    growth_score = max(0, min(100, int(growth)))

    # Oportunidade: monetização + boa nota + escala não absurda + sinais de dev menor.
    monetizes = boolish(app_data.get("containsAds")) or boolish(app_data.get("adSupported")) or boolish(app_data.get("offersIAP")) or not boolish(app_data.get("free", True))
    opportunity = 0
    opportunity += min(25, indie_score * 0.25)
    opportunity += min(22, growth_score * 0.25)
    if monetizes:
        opportunity += 18
    if score >= 4.4:
        opportunity += 18
    elif score >= 4.0:
        opportunity += 10
    if 20_000 <= installs <= 2_000_000:
        opportunity += 18
    elif installs < 20_000:
        opportunity += 8
    elif installs > 10_000_000:
        opportunity -= 20
    opportunity_score = max(0, min(100, int(opportunity)))

    if giant:
        perfil = "gigante"
    elif indie_score >= 70:
        perfil = "pequeno/indie"
    elif growth_score >= 65:
        perfil = "crescendo"
    elif opportunity_score >= 70:
        perfil = "oportunidade"
    else:
        perfil = "normal"

    return {
        "is_giant": giant,
        "indie_score": indie_score,
        "growth_score": growth_score,
        "opportunity_score": opportunity_score,
        "perfil_detectado": perfil,
        "updated_days_ago": updated_days,
        "released_days_ago": released_days,
    }


def passes_profile(app_data: Dict[str, Any], profile: str) -> bool:
    profile = (profile or "TODOS").upper()
    scores = app_data if "indie_score" in app_data else {**app_data, **compute_scores(app_data)}
    installs = get_installs(app_data)
    if profile == "TODOS":
        return True
    if profile == "SEM_GIGANTES":
        return not scores.get("is_giant")
    if profile == "PEQUENOS_INDIE":
        return not scores.get("is_giant") and installs <= 1_500_000 and scores.get("indie_score", 0) >= 45
    if profile == "CRESCENDO":
        return not scores.get("is_giant") and scores.get("growth_score", 0) >= 45
    if profile == "OPORTUNIDADE":
        return not scores.get("is_giant") and scores.get("opportunity_score", 0) >= 52
    return True


def parse_price_range(value: Any) -> float:
    if not value:
        return 0.0
    nums = re.findall(r"\d+(?:[\.,]\d+)?", str(value))
    parsed = [parse_num(n) for n in nums]
    parsed = [n for n in parsed if n is not None]
    return float(sum(parsed) / len(parsed)) if parsed else 0.0


def estimate_financials(app_data: Dict[str, Any], exchange_rate_brl: float = 5.40) -> Dict[str, Any]:
    """Estimativa aproximada. Não substitui dados internos, AppMagic/SensorTower etc."""
    installs = max(get_installs(app_data), 0)
    score = get_score(app_data)
    ratings = get_ratings(app_data)
    category = str(app_data.get("genreId") or app_data.get("category_code") or app_data.get("categoria_codigo") or "").upper()
    contains_ads = boolish(app_data.get("containsAds")) or boolish(app_data.get("adSupported"))
    offers_iap = boolish(app_data.get("offersIAP"))
    is_paid = boolish(app_data.get("free")) is False or boolish(app_data.get("paid"))
    price = parse_num(app_data.get("price")) or parse_price_range(app_data.get("inAppProductPrice")) or 0.0
    updated_days = days_since_google_date(app_data.get("updated")) or 365
    age_days = days_since_google_date(app_data.get("released")) or 720
    age_months = max(age_days / 30, 1)

    if installs <= 0:
        return {
            "financial_confidence": "baixa",
            "revenue_monthly_usd_low": 0,
            "revenue_monthly_usd_base": 0,
            "revenue_monthly_usd_high": 0,
            "profit_monthly_usd_base": 0,
            "revenue_monthly_brl_base": 0,
            "financial_notes": "Sem instalações suficientes para estimar.",
        }

    category_factor = CATEGORY_ARPU_HINTS.get(category, 0.55)
    score_factor = 0.75 if score and score < 3.7 else 1.0 if score < 4.4 else 1.12
    fresh_factor = 1.10 if updated_days <= 45 else 1.0 if updated_days <= 180 else 0.72
    giant_penalty = 0.85 if is_giant(app_data) else 1.0

    # MAU estimado: muito impreciso, mas útil para ordenar oportunidades.
    active_rate = 0.025 + min(0.10, math.log10(max(installs, 10)) / 100)
    if category.startswith("GAME"):
        active_rate *= 0.85
    if updated_days <= 30:
        active_rate *= 1.20
    if score >= 4.5:
        active_rate *= 1.10
    mau = installs * active_rate

    ad_revenue = 0.0
    if contains_ads:
        impressions_per_mau_month = 18 if category.startswith("GAME") else 10
        ecpm = 0.35 * category_factor * score_factor  # BR/latam tende a CPM baixo; conservador.
        ad_revenue = mau * impressions_per_mau_month * ecpm / 1000

    iap_revenue = 0.0
    if offers_iap:
        payer_rate = 0.004 if category.startswith("GAME") else 0.0025
        arppu = max(1.2, price or 3.49) * category_factor
        iap_revenue = mau * payer_rate * arppu

    paid_revenue = 0.0
    if is_paid:
        monthly_new_downloads = installs / age_months
        paid_revenue = monthly_new_downloads * max(price, 0.99) * 0.70

    base = (ad_revenue + iap_revenue + paid_revenue) * fresh_factor * giant_penalty
    low = base * 0.28
    high = base * 3.25
    profit_base = base * (0.62 if offers_iap or is_paid else 0.48)

    confidence_score = 0
    confidence_score += 20 if installs >= 100_000 else 8 if installs >= 10_000 else 2
    confidence_score += 20 if ratings >= 5_000 else 8 if ratings >= 500 else 2
    confidence_score += 15 if contains_ads or offers_iap or is_paid else 0
    confidence_score += 10 if updated_days <= 180 else 0
    confidence = "alta" if confidence_score >= 55 else "média" if confidence_score >= 30 else "baixa"

    notes = []
    if contains_ads:
        notes.append("tem anúncios")
    if offers_iap:
        notes.append("tem compras no app")
    if is_paid:
        notes.append("é pago")
    if not notes:
        notes.append("sem monetização explícita detectada")

    return {
        "estimated_mau": int(mau),
        "revenue_monthly_usd_low": round(low, 2),
        "revenue_monthly_usd_base": round(base, 2),
        "revenue_monthly_usd_high": round(high, 2),
        "profit_monthly_usd_base": round(profit_base, 2),
        "revenue_monthly_brl_base": round(base * exchange_rate_brl, 2),
        "profit_monthly_brl_base": round(profit_base * exchange_rate_brl, 2),
        "financial_confidence": confidence,
        "financial_notes": ", ".join(notes),
    }


def compact_num(value: Any, default: str = "N/A") -> str:
    n = parse_installs(value)
    if n is None:
        return default
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B".replace(".0", "").replace(".", ",")
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M".replace(".0", "").replace(".", ",")
    if n >= 1_000:
        return f"{n / 1_000:.1f}K".replace(".0", "").replace(".", ",")
    return str(n)


def money(value: Any, currency: str = "US$") -> str:
    n = parse_num(value)
    if n is None:
        return "N/A"
    return f"{currency} {n:,.0f}".replace(",", ".")


def safe_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except TypeError:
        return json.dumps(str(value), ensure_ascii=False)
