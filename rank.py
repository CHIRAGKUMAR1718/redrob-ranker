#!/usr/bin/env python3
"""
Redrob Hackathon — Candidate Ranker
Author: Team Chirag
"""

import argparse
import gzip
import json
import csv
import os
import re
import math
from datetime import date, datetime
from tqdm import tqdm

# ─────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────

TODAY = date.today()
OUTPUT_DIR = "submission"

# ─────────────────────────────────────────
# ARGUMENT PARSER
# ─────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(description="Redrob Candidate Ranker")
    parser.add_argument("--candidates", required=True, help="Path to candidates.jsonl or candidates.jsonl.gz")
    parser.add_argument("--out", required=True, help="Output CSV path e.g. submission/team_001.csv")
    return parser.parse_args()

# ─────────────────────────────────────────
# STEP 2 — DATA LOADER
# ─────────────────────────────────────────

def load_candidates(path):
    """Load candidates from .jsonl or .jsonl.gz file"""
    candidates = []

    is_gzip = path.endswith(".gz")

    print("📂 Loading candidates...")

    if is_gzip:
        opener = gzip.open(path, "rt", encoding="utf-8")
    else:
        opener = open(path, "r", encoding="utf-8")

    with opener as f:
        for line in tqdm(f, desc="   Reading", unit=" candidates"):
            line = line.strip()
            if line:
                try:
                    candidates.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    print(f"✅ Loaded {len(candidates):,} candidates\n")
    return candidates

# ─────────────────────────────────────────
# STEP 3 — HONEYPOT FILTER
# ─────────────────────────────────────────

def is_honeypot(c):
    """Detect impossible/fake candidate profiles"""
    profile = c.get("profile", {})
    skills = c.get("skills", [])
    career = c.get("career_history", [])

    # Check 1: Expert skill + zero duration (3 ya zyada = honeypot)
    expert_zero = [
        s for s in skills
        if s.get("proficiency") == "expert" and s.get("duration_months", 0) == 0
    ]
    if len(expert_zero) >= 3:
        return True

    # Check 2: Total career months > (YOE + 4) * 12 — impossible timeline
    yoe = profile.get("years_of_experience", 0)
    total_career_months = sum(j.get("duration_months", 0) for j in career)
    if total_career_months > (yoe + 4) * 12:
        return True

    # Check 3: 5+ skills with expert/advanced but zero endorsements AND zero duration
    suspicious = [
        s for s in skills
        if s.get("proficiency") in ["expert", "advanced"]
        and s.get("duration_months", 0) == 0
        and s.get("endorsements", 0) == 0
    ]
    if len(suspicious) >= 5:
        return True

    # Check 4: Zero experience but has career history
    if yoe == 0 and len(career) > 2:
        return True

    return False


def filter_honeypots(candidates):
    print("🍯 Running honeypot filter...")
    clean = []
    removed = 0

    for c in tqdm(candidates, desc="   Checking", unit=" candidates"):
        if is_honeypot(c):
            removed += 1
        else:
            clean.append(c)

    print(f"   Removed  : {removed:,} honeypots")
    print(f"   Remaining: {len(clean):,} candidates")
    print(f"✅ Step 3 — Honeypot filter done!\n")
    return clean

# ─────────────────────────────────────────
# STEP 4 — HARD FILTERS
# ─────────────────────────────────────────

# IT Services companies jo JD ne explicitly reject ki hain
SERVICES_COMPANIES = {
    "tcs", "infosys", "wipro", "accenture", "cognizant",
    "hcl", "tech mahindra", "mindtree", "mphasis", "hexaware",
    "capgemini", "ibm", "l&t infotech", "ltimindtree", "niit",
    "patni", "mastech", "syntel", "persistent", "kpit"
}

# Wrong domain titles — clearly not AI/ML
WRONG_TITLES = {
    "hr manager", "human resources", "accountant", "civil engineer",
    "mechanical engineer", "content writer", "graphic designer",
    "sales executive", "marketing manager", "customer support",
    "operations manager", "supply chain", "teacher", "doctor",
    "lawyer", "chartered accountant", "financial analyst",
    "receptionist", "nurse", "pharmacist"
}

# Good AI/ML related keywords for title check
GOOD_TITLE_KEYWORDS = [
    "ml", "machine learning", "ai ", "artificial intelligence",
    "nlp", "natural language", "data scientist", "data science",
    "search engineer", "ranking", "retrieval", "recommendation",
    "applied scientist", "research engineer", "applied ml",
    "computer vision", "deep learning", "software engineer",
    "backend engineer", "data engineer", "platform engineer",
    "python developer", "developer", "engineer"
]


def is_hard_reject(c):
    """Hard disqualify candidates who clearly don't fit"""
    profile = c.get("profile", {})
    career = c.get("career_history", [])
    signals = c.get("redrob_signals", {})

    # Check 1: Outside India AND not willing to relocate
    country = profile.get("country", "").strip().lower()
    willing = signals.get("willing_to_relocate", False)
    if country != "india" and not willing:
        return True, "Outside India, not willing to relocate"

    # Check 2: Pure IT services career (every job = services company)
    if career:
        all_services = all(
            any(s in job.get("company", "").lower() for s in SERVICES_COMPANIES)
            for job in career
        )
        if all_services and len(career) >= 2:
            return True, "Pure IT services career"

    # Check 3: Clearly wrong title AND no good career history
    current_title = profile.get("current_title", "").lower()
    is_wrong_title = any(wt in current_title for wt in WRONG_TITLES)

    if is_wrong_title:
        career_titles = " ".join(
            job.get("title", "").lower() for job in career
        )
        has_good_career = any(
            kw in career_titles for kw in GOOD_TITLE_KEYWORDS
        )
        if not has_good_career:
            return True, f"Wrong title: {current_title}"

    # Check 4: Experience too low or too high
    yoe = profile.get("years_of_experience", 0)
    if yoe < 3 or yoe > 20:
        return True, f"Experience out of range: {yoe} years"

    # Check 5: Ghost candidate — inactive + not open to work
    last_active_str = signals.get("last_active_date", "")
    open_to_work = signals.get("open_to_work_flag", False)
    if last_active_str:
        try:
            last_active = datetime.strptime(last_active_str, "%Y-%m-%d").date()
            days_inactive = (TODAY - last_active).days
            if days_inactive > 180 and not open_to_work:
                return True, f"Ghost candidate: {days_inactive} days inactive"
        except ValueError:
            pass

    return False, ""


def apply_hard_filters(candidates):
    print("🚫 Applying hard filters...")
    clean = []
    removed = 0
    reasons = {}

    for c in tqdm(candidates, desc="   Filtering", unit=" candidates"):
        reject, reason = is_hard_reject(c)
        if reject:
            removed += 1
            reasons[reason.split(":")[0]] = reasons.get(reason.split(":")[0], 0) + 1
        else:
            clean.append(c)

    print(f"   Removed  : {removed:,} candidates")
    print(f"   Remaining: {len(clean):,} candidates")
    print(f"   Reasons  :")
    for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
        print(f"      {reason}: {count:,}")
    print(f"✅ Step 4 — Hard filters done!\n")
    return clean


# ─────────────────────────────────────────
# STEP 5 — SCORING ENGINE
# ─────────────────────────────────────────

# JD ke must-have skills
CORE_SKILLS = {
    # Vector DBs
    "pinecone": 1.0, "qdrant": 1.0, "weaviate": 1.0, "faiss": 1.0,
    "milvus": 1.0, "elasticsearch": 0.9, "opensearch": 0.9,
    "pgvector": 0.8, "chroma": 0.8, "redis": 0.6,

    # Embeddings
    "embeddings": 1.0, "sentence transformers": 1.0,
    "sentence-transformers": 1.0, "text embeddings": 1.0,
    "bge": 0.9, "e5": 0.9, "openai embeddings": 0.8,

    # Retrieval & Ranking
    "information retrieval": 1.0, "retrieval": 0.9,
    "ranking": 0.9, "learning to rank": 1.0, "ltr": 1.0,
    "bm25": 0.9, "hybrid retrieval": 1.0, "hybrid search": 1.0,
    "semantic search": 0.9, "vector search": 1.0,
    "recommendation systems": 0.8, "recommendation": 0.8,

    # Evaluation
    "ndcg": 1.0, "map": 0.8, "mrr": 0.8,
    "a/b testing": 0.9, "a/b test": 0.9,

    # ML Frameworks
    "pytorch": 0.8, "tensorflow": 0.7, "hugging face": 0.9,
    "hugging face transformers": 0.9, "transformers": 0.8,
    "scikit-learn": 0.7, "xgboost": 0.8,

    # LLMs
    "llm": 0.8, "fine-tuning llms": 0.9, "fine-tuning": 0.8,
    "lora": 0.8, "qlora": 0.8, "rag": 0.9,
    "langchain": 0.6, "llmops": 0.7,

    # Core
    "python": 0.9, "mlops": 0.8, "mlflow": 0.7,
    "docker": 0.6, "fastapi": 0.6,
    "nlp": 0.8, "natural language processing": 0.8,
}

# Indian product companies — explicitly recognized
PRODUCT_COMPANIES = {
    "swiggy", "zomato", "flipkart", "meesho", "razorpay", "paytm",
    "phonepe", "cred", "uber", "ola", "dunzo", "blinkit", "zepto",
    "groww", "zerodha", "upstox", "nykaa", "myntra", "bigbasket",
    "lenskart", "cars24", "spinny", "urban company", "urbanclap",
    "byju", "unacademy", "vedantu", "doubtnut", "physics wallah",
    "freshworks", "zoho", "browserstack", "postman", "hasura",
    "setu", "signzy", "khatabook", "ofbusiness", "moglix",
    "mad street den", "haptik", "senseforth", "vernacular.ai",
    "google", "microsoft", "amazon", "meta", "apple", "netflix",
    "adobe", "salesforce", "oracle", "atlassian", "gitlab",
    "pied piper", "hooli", "initech", "globex",  # fictional product cos in dataset
}

# Preferred locations
PREFERRED_LOCATIONS = {
    "pune": 1.0, "noida": 1.0, "gurugram": 1.0, "gurgaon": 1.0,
    "delhi": 0.95, "new delhi": 0.95,
    "bangalore": 0.9, "bengaluru": 0.9,
    "hyderabad": 0.9, "mumbai": 0.9,
    "chennai": 0.8, "kolkata": 0.75,
    "ahmedabad": 0.75, "jaipur": 0.7,
    "chandigarh": 0.7, "indore": 0.7,
    "coimbatore": 0.65, "trivandrum": 0.65,
    "kochi": 0.65, "bhubaneswar": 0.6,
}


# ── Component A: Career Trajectory (35%) ──

def score_career(c):
    profile = c.get("profile", {})
    career = c.get("career_history", [])

    if not career:
        return 0.0

    score = 0.0
    total_weight = 0.0

    for job in career:
        company = job.get("company", "").lower()
        title = job.get("title", "").lower()
        industry = job.get("industry", "").lower()
        duration = job.get("duration_months", 0)
        description = job.get("description", "").lower()

        # Job weight — recent aur longer jobs zyada important
        job_weight = min(duration / 12, 3.0) + 1.0

        job_score = 0.0

        # Product company check
        is_product = any(pc in company for pc in PRODUCT_COMPANIES)
        is_services = any(sc in company for sc in SERVICES_COMPANIES)

        if is_product:
            job_score += 0.5
        elif not is_services:
            job_score += 0.3  # unknown company — neutral
        else:
            job_score += 0.05  # services company

        # Title check
        good_titles = [
            "ml engineer", "machine learning", "ai engineer", "nlp engineer",
            "search engineer", "ranking engineer", "retrieval", "recommendation",
            "applied scientist", "research engineer", "applied ml",
            "data scientist", "software engineer", "backend engineer"
        ]
        if any(gt in title for gt in good_titles):
            job_score += 0.4

        # Description mein AI/ML proof words
        proof_words = [
            "shipped", "deployed", "production", "built", "designed",
            "embedding", "vector", "retrieval", "ranking", "search",
            "recommendation", "a/b test", "ndcg", "latency", "scale",
            "real-time", "pipeline", "model", "inference"
        ]
        proof_count = sum(1 for pw in proof_words if pw in description)
        job_score += min(proof_count * 0.02, 0.1)

        score += job_score * job_weight
        total_weight += job_weight

    # Stability bonus — longest tenure
    max_tenure = max((j.get("duration_months", 0) for j in career), default=0)
    if max_tenure >= 36:
        score += 0.1
    elif max_tenure >= 24:
        score += 0.05

    return min(score / max(total_weight, 1.0), 1.0)


# ── Component B: Skill Relevance (25%) ──

def score_skills(c):
    skills = c.get("skills", [])
    signals = c.get("redrob_signals", {})
    assessments = signals.get("skill_assessment_scores", {})

    if not skills:
        return 0.0

    total_score = 0.0
    matched = 0

    for skill in skills:
        name = skill.get("name", "").lower().strip()
        proficiency = skill.get("proficiency", "beginner")
        duration = skill.get("duration_months", 0)
        endorsements = skill.get("endorsements", 0)

        # Core skill match
        skill_weight = 0.0
        for core_skill, weight in CORE_SKILLS.items():
            if core_skill in name or name in core_skill:
                skill_weight = weight
                break

        if skill_weight == 0:
            continue

        matched += 1

        # Proficiency weight
        prof_map = {"expert": 1.0, "advanced": 0.8, "intermediate": 0.5, "beginner": 0.2}
        prof_score = prof_map.get(proficiency, 0.2)

        # Duration weight — keyword stuffer catcher
        if duration == 0:
            dur_score = 0.0  # Clear red flag
        elif duration >= 24:
            dur_score = 1.0
        elif duration >= 12:
            dur_score = 0.8
        elif duration >= 6:
            dur_score = 0.5
        else:
            dur_score = 0.2

        # Endorsement weight
        if endorsements >= 20:
            end_score = 1.0
        elif endorsements >= 10:
            end_score = 0.8
        elif endorsements >= 1:
            end_score = 0.5
        else:
            end_score = 0.6  # No endorsement — not always bad

        # Platform assessment override karta hai proficiency ko
        skill_display_name = skill.get("name", "")
        if skill_display_name in assessments:
            assess_score = assessments[skill_display_name] / 100.0
            prof_score = max(prof_score, assess_score)

        skill_total = skill_weight * prof_score * dur_score * end_score
        total_score += skill_total

    # Normalize — max possible ~5 matched skills
    return min(total_score / 3.0, 1.0)


# ── Component C: Experience Quality (20%) ──

def score_experience(c):
    profile = c.get("profile", {})
    career = c.get("career_history", [])

    yoe = profile.get("years_of_experience", 0)

    # YOE sweet spot: 5-9 years
    if 5 <= yoe <= 9:
        yoe_score = 1.0
    elif 4 <= yoe < 5 or 9 < yoe <= 12:
        yoe_score = 0.8
    elif 3 <= yoe < 4 or 12 < yoe <= 15:
        yoe_score = 0.6
    else:
        yoe_score = 0.3

    # Stability — job hopping check
    if career:
        tenures = [j.get("duration_months", 0) for j in career]
        short_stints = sum(1 for t in tenures if t < 12)
        stability_score = max(0.0, 1.0 - (short_stints * 0.2))
    else:
        stability_score = 0.5

    # Recency — last 2 jobs mein AI/ML hai?
    recent_jobs = career[:2]
    recent_titles = " ".join(j.get("title", "").lower() for j in recent_jobs)
    recent_desc = " ".join(j.get("description", "").lower() for j in recent_jobs)
    recent_text = recent_titles + " " + recent_desc

    recent_ai_keywords = [
        "ml", "machine learning", "ai", "nlp", "search", "ranking",
        "embedding", "vector", "retrieval", "recommendation", "data science"
    ]
    has_recent_ai = any(kw in recent_text for kw in recent_ai_keywords)
    recency_score = 1.0 if has_recent_ai else 0.5

    return (yoe_score * 0.4 + stability_score * 0.3 + recency_score * 0.3)


# ── Component D: Location (10%) ──

def score_location(c):
    profile = c.get("profile", {})
    signals = c.get("redrob_signals", {})

    location = profile.get("location", "").lower()
    willing = signals.get("willing_to_relocate", False)

    for city, loc_score in PREFERRED_LOCATIONS.items():
        if city in location:
            base = loc_score
            if willing:
                base = min(base + 0.05, 1.0)
            return base

    # India mein hai but unlisted city
    country = profile.get("country", "").lower()
    if country == "india":
        return 0.6 if willing else 0.5

    # Outside India but willing to relocate
    if willing:
        return 0.4

    return 0.1


# ── Component E: Education (10%) ──

def score_education(c):
    education = c.get("education", [])

    if not education:
        return 0.5

    best_score = 0.0

    for edu in education:
        field = edu.get("field_of_study", "").lower()
        tier = edu.get("tier", "unknown")
        degree = edu.get("degree", "").lower()

        # Field score
        if any(f in field for f in ["computer science", "cs", "artificial intelligence",
                                     "machine learning", "data science", "mathematics",
                                     "statistics", "information technology"]):
            field_score = 1.0
        elif any(f in field for f in ["electronics", "electrical", "ece", "eee"]):
            field_score = 0.7
        elif any(f in field for f in ["engineering", "physics"]):
            field_score = 0.6
        else:
            field_score = 0.4

        # Tier score
        tier_map = {"tier_1": 1.0, "tier_2": 0.85, "tier_3": 0.7,
                    "tier_4": 0.55, "unknown": 0.65}
        tier_score = tier_map.get(tier, 0.65)

        # Degree bonus
        degree_bonus = 0.0
        if any(d in degree for d in ["m.tech", "m.s", "ms", "mtech", "ph.d", "phd"]):
            degree_bonus = 0.05

        edu_score = (field_score * 0.6 + tier_score * 0.4) + degree_bonus
        best_score = max(best_score, edu_score)

    return min(best_score, 1.0)


# ── Master Scorer ──

def compute_base_score(c):
    a = score_career(c)      # 35%
    b = score_skills(c)      # 25%
    cc = score_experience(c) # 20%
    d = score_location(c)    # 10%
    e = score_education(c)   # 10%

    return (a * 0.35 + b * 0.25 + cc * 0.20 + d * 0.10 + e * 0.10)


def score_all_candidates(candidates):
    print("🎯 Scoring candidates...")
    scored = []

    for c in tqdm(candidates, desc="   Scoring", unit=" candidates"):
        base = compute_base_score(c)
        c["_base_score"] = base
        scored.append(c)

    scored.sort(key=lambda x: x["_base_score"], reverse=True)

    print(f"   Top score   : {scored[0]['_base_score']:.4f}")
    print(f"   Score @100  : {scored[99]['_base_score']:.4f}")
    print(f"   Score @1000 : {scored[999]['_base_score']:.4f}")
    print(f"✅ Step 5 — Scoring done!\n")
    return scored

# ─────────────────────────────────────────
# STEP 6 — BEHAVIORAL MULTIPLIER
# ─────────────────────────────────────────

def compute_behavioral_multiplier(c):
    signals = c.get("redrob_signals", {})

    multiplier = 1.0

    # 1. Days since last active
    last_active_str = signals.get("last_active_date", "")
    if last_active_str:
        try:
            last_active = datetime.strptime(last_active_str, "%Y-%m-%d").date()
            days_inactive = (TODAY - last_active).days
            if days_inactive <= 30:
                multiplier *= 1.0
            elif days_inactive <= 90:
                multiplier *= 0.85
            elif days_inactive <= 180:
                multiplier *= 0.65
            else:
                multiplier *= 0.35
        except ValueError:
            pass

    # 2. Open to work
    if signals.get("open_to_work_flag", False):
        multiplier *= 1.10

    # 3. Recruiter response rate
    response_rate = signals.get("recruiter_response_rate", 0.0)
    if response_rate >= 0.7:
        multiplier *= 1.10
    elif response_rate >= 0.3:
        multiplier *= 1.0
    elif response_rate >= 0.15:
        multiplier *= 0.8
    else:
        multiplier *= 0.5  # practically unreachable

    # 4. Notice period
    notice = signals.get("notice_period_days", 90)
    if notice <= 15:
        multiplier *= 1.08
    elif notice <= 30:
        multiplier *= 1.05
    elif notice <= 60:
        multiplier *= 1.0
    elif notice <= 90:
        multiplier *= 0.95
    else:
        multiplier *= 0.85

    # 5. GitHub activity
    github = signals.get("github_activity_score", -1)
    if github >= 60:
        multiplier *= 1.10
    elif github >= 30:
        multiplier *= 1.05
    elif github == -1:
        multiplier *= 0.97  # no github — small penalty
    else:
        multiplier *= 1.0

    # 6. Interview completion rate
    icr = signals.get("interview_completion_rate", 0.5)
    if icr >= 0.8:
        multiplier *= 1.05
    elif icr < 0.3:
        multiplier *= 0.85

    # 7. Verified contact
    if signals.get("verified_email", False) and signals.get("verified_phone", False):
        multiplier *= 1.05

    # 8. Skill assessment bonus
    assessments = signals.get("skill_assessment_scores", {})
    if assessments:
        avg_score = sum(assessments.values()) / len(assessments)
        if avg_score >= 70:
            multiplier *= 1.08
        elif avg_score >= 50:
            multiplier *= 1.04

    # Cap multiplier
    return min(max(multiplier, 0.3), 1.25)


def apply_behavioral_multiplier(candidates):
    print("🧠 Applying behavioral multiplier...")

    for c in tqdm(candidates, desc="   Processing", unit=" candidates"):
        base = c.get("_base_score", 0.0)
        multiplier = compute_behavioral_multiplier(c)
        c["_multiplier"] = multiplier
        c["_final_score"] = base * multiplier

    # Re-sort by final score
    candidates.sort(key=lambda x: x["_final_score"], reverse=True)

    print(f"   Top final score   : {candidates[0]['_final_score']:.4f}")
    print(f"   Final score @100  : {candidates[99]['_final_score']:.4f}")
    print(f"   Final score @1000 : {candidates[999]['_final_score']:.4f}")
    print(f"✅ Step 6 — Behavioral multiplier done!\n")
    return candidates

# ─────────────────────────────────────────
# STEP 7 — TEXT INTELLIGENCE LAYER
# ─────────────────────────────────────────

# Proof words — genuine shipper ke signs
PROOF_WORDS = [
    "shipped", "deployed", "production", "built", "launched",
    "designed", "led", "improved", "reduced", "increased",
    "a/b test", "a/b testing", "ndcg", "latency", "throughput",
    "real-time", "scale", "scalable", "pipeline", "end-to-end",
    "revenue", "recall", "precision", "inference", "serving",
    "owned", "drove", "architected", "optimized", "integrated"
]

# Vague words — marketing fluff ke signs
VAGUE_WORDS = [
    "passionate", "enthusiastic", "love to", "loves to",
    "quick learner", "fast learner", "team player",
    "hardworking", "self-motivated", "go-getter",
    "dynamic", "synergy", "leverage", "proactive",
    "detail-oriented", "think outside the box"
]

# JD specific phrases — direct alignment
JD_PHRASES = [
    "embedding", "embeddings", "vector search", "vector db",
    "semantic search", "hybrid search", "hybrid retrieval",
    "information retrieval", "learning to rank", "re-ranking",
    "reranking", "bm25", "dense retrieval", "sparse retrieval",
    "sentence transformer", "bi-encoder", "cross-encoder",
    "ndcg", "evaluation", "a/b test", "ranking system",
    "search relevance", "candidate retrieval", "faiss",
    "pinecone", "qdrant", "weaviate", "elasticsearch",
    "recommendation", "retrieval augmented", "rag"
]


def compute_text_score(c):
    career = c.get("career_history", [])
    profile = c.get("profile", {})

    # Saari text ek jagah combine karo
    all_descriptions = " ".join(
        job.get("description", "").lower() for job in career
    )
    summary = profile.get("summary", "").lower()
    headline = profile.get("headline", "").lower()
    full_text = all_descriptions + " " + summary + " " + headline

    # 1. Proof word count
    proof_count = sum(1 for pw in PROOF_WORDS if pw in full_text)
    proof_score = min(proof_count / 8.0, 1.0)  # 8+ proof words = max score

    # 2. Vague word penalty
    vague_count = sum(1 for vw in VAGUE_WORDS if vw in full_text)
    vague_penalty = min(vague_count * 0.1, 0.4)  # max 40% penalty

    # 3. JD phrase alignment
    jd_count = sum(1 for jp in JD_PHRASES if jp in full_text)
    jd_score = min(jd_count / 5.0, 1.0)  # 5+ JD phrases = max score

    # 4. Metrics detection — numbers in descriptions
    has_metrics = bool(re.search(
        r'\d+%|\d+x\b|\d+ms|\d+ ms|[₹$]\d+|\d+k\b|\d+m\b',
        all_descriptions
    ))
    metrics_bonus = 0.15 if has_metrics else 0.0

    # Combined text score (additive bonus — max 0.08)
    raw = (proof_score * 0.4 + jd_score * 0.5) - vague_penalty + metrics_bonus
    text_bonus = min(max(raw * 0.08, 0.0), 0.08)

    return text_bonus, {
        "proof_count": proof_count,
        "jd_count": jd_count,
        "vague_count": vague_count,
        "has_metrics": has_metrics
    }


def apply_text_intelligence(candidates):
    print("📝 Applying text intelligence...")

    for c in tqdm(candidates, desc="   Analyzing", unit=" candidates"):
        text_bonus, text_meta = compute_text_score(c)
        c["_text_bonus"] = text_bonus
        c["_text_meta"] = text_meta
        c["_final_score"] = c.get("_final_score", 0.0) + text_bonus

    # Re-sort
    candidates.sort(key=lambda x: x["_final_score"], reverse=True)

    # Stats on top 100
    top100 = candidates[:100]
    avg_proof = sum(c["_text_meta"]["proof_count"] for c in top100) / 100
    avg_jd = sum(c["_text_meta"]["jd_count"] for c in top100) / 100
    avg_vague = sum(c["_text_meta"]["vague_count"] for c in top100) / 100

    print(f"   Top 100 avg proof words : {avg_proof:.1f}")
    print(f"   Top 100 avg JD phrases  : {avg_jd:.1f}")
    print(f"   Top 100 avg vague words : {avg_vague:.1f}")
    print(f"   Top final score         : {candidates[0]['_final_score']:.4f}")
    print(f"   Final score @100        : {candidates[99]['_final_score']:.4f}")
    print(f"✅ Step 7 — Text intelligence done!\n")
    return candidates

# ─────────────────────────────────────────
# STEP 8 — REASONING GENERATOR + CSV OUTPUT
# ─────────────────────────────────────────

def get_top_skills(c, top_n=3):
    """Candidate ki top relevant skills nikalo"""
    skills = c.get("skills", [])
    signals = c.get("redrob_signals", {})
    assessments = signals.get("skill_assessment_scores", {})

    scored_skills = []
    for skill in skills:
        name = skill.get("name", "")
        name_lower = name.lower()
        duration = skill.get("duration_months", 0)
        endorsements = skill.get("endorsements", 0)
        proficiency = skill.get("proficiency", "beginner")

        # Core skill match check
        is_core = any(cs in name_lower for cs in CORE_SKILLS.keys())
        if not is_core:
            continue

        # Score for sorting
        prof_map = {"expert": 4, "advanced": 3, "intermediate": 2, "beginner": 1}
        skill_score = (
            prof_map.get(proficiency, 1) * 10 +
            min(duration, 60) +
            min(endorsements, 30)
        )

        # Assessment bonus
        if name in assessments:
            skill_score += assessments[name]

        scored_skills.append((skill_score, name, duration, proficiency, endorsements))

    scored_skills.sort(reverse=True)
    return scored_skills[:top_n]


def get_career_summary(c):
    """Career ka short summary"""
    career = c.get("career_history", [])
    if not career:
        return "No career history"

    # Last 2 jobs
    recent = career[:2]
    parts = []
    for job in recent:
        company = job.get("company", "")
        title = job.get("title", "")
        industry = job.get("industry", "")
        duration = job.get("duration_months", 0)
        years = round(duration / 12, 1)

        # Product ya services?
        company_lower = company.lower()
        is_product = any(pc in company_lower for pc in PRODUCT_COMPANIES)
        co_type = "product" if is_product else "services"

        parts.append(f"{title} at {company} ({co_type}, {years}yr)")

    return " → ".join(parts)


def get_honest_concern(c):
    """Ek honest concern identify karo"""
    profile = c.get("profile", {})
    signals = c.get("redrob_signals", {})
    career = c.get("career_history", [])

    yoe = profile.get("years_of_experience", 0)
    notice = signals.get("notice_period_days", 90)
    response_rate = signals.get("recruiter_response_rate", 0.5)
    github = signals.get("github_activity_score", -1)
    last_active_str = signals.get("last_active_date", "")
    open_to_work = signals.get("open_to_work_flag", False)

    # Days inactive
    days_inactive = 999
    if last_active_str:
        try:
            last_active = datetime.strptime(last_active_str, "%Y-%m-%d").date()
            days_inactive = (TODAY - last_active).days
        except ValueError:
            pass

    # Concerns priority order
    if notice > 90:
        return f"Long notice period ({notice} days)"
    if days_inactive > 60 and not open_to_work:
        return f"Not actively looking (inactive {days_inactive}d)"
    if response_rate < 0.3:
        return f"Low recruiter response rate ({response_rate:.0%})"
    if github == -1:
        return "No GitHub linked — work visibility limited"
    if yoe > 12:
        return f"Senior profile ({yoe}yr) — may expect Lead/Principal role"
    if len(career) > 0:
        tenures = [j.get("duration_months", 0) for j in career]
        if sum(1 for t in tenures if t < 12) >= 2:
            return "Multiple short stints — stability concern"

    # Vary concern by candidate to avoid template look
    salary_signals = [
        "Strong overall profile — compensation expectations to verify",
        "Top-tier profile — may have competing offers in pipeline",
        "Excellent fit — confirm salary range before outreach",
    ]
    idx = int(c.get("candidate_id", "CAND_0000000").split("_")[1]) % len(salary_signals)
    return salary_signals[idx]


def generate_reasoning(c):
    """Stage 4 ready specific reasoning generate karo"""
    profile = c.get("profile", {})
    signals = c.get("redrob_signals", {})

    # Basic info
    yoe = profile.get("years_of_experience", 0)
    title = profile.get("current_title", "")
    location = profile.get("location", "")
    open_to_work = signals.get("open_to_work_flag", False)
    notice = signals.get("notice_period_days", 90)
    response_rate = signals.get("recruiter_response_rate", 0.5)
    github = signals.get("github_activity_score", -1)

    # Days inactive
    last_active_str = signals.get("last_active_date", "")
    days_inactive = "unknown"
    if last_active_str:
        try:
            last_active = datetime.strptime(last_active_str, "%Y-%m-%d").date()
            days_inactive = (TODAY - last_active).days
        except ValueError:
            pass

    # Top skills
    top_skills = get_top_skills(c, top_n=3)
    if top_skills:
        skill_parts = []
        for score, name, duration, proficiency, endorsements in top_skills:
            skill_parts.append(f"{name} ({proficiency}, {duration}m)")
        skills_str = ", ".join(skill_parts)
    else:
        skills_str = "No core skills matched"

    # Career summary
    career_str = get_career_summary(c)

    # Availability
    otw = "open to work" if open_to_work else "not marked open"
    active_str = f"{days_inactive}d ago" if isinstance(days_inactive, int) else "unknown"
    github_str = f"GitHub={github}" if github != -1 else "no GitHub"

    # Honest concern
    concern = get_honest_concern(c)

    # Final reasoning — specific, Stage 4 ready
    reasoning = (
        f"{yoe:.1f}yr {title} in {location}; "
        f"Career: {career_str}; "
        f"Core skills: {skills_str}; "
        f"Active {active_str}, {otw}, response={response_rate:.0%}, "
        f"notice={notice}d, {github_str}. "
        f"Concern: {concern}."
    )

    return reasoning


def write_csv_and_finalize(candidates, out_path):
    print("📊 Generating top 100 + writing CSV...")

    top100 = candidates[:100]

    # Tie-break: equal score pe candidate_id ascending
    top100.sort(key=lambda x: (-x["_final_score"], x["candidate_id"]))

    # Assign ranks
    rows = []
    for rank, c in enumerate(top100, start=1):
        cid = c["candidate_id"]
        score = round(c["_final_score"], 6)
        reasoning = generate_reasoning(c)
        rows.append({
            "candidate_id": cid,
            "rank": rank,
            "score": score,
            "reasoning": reasoning
        })

    # Write CSV
    os.makedirs(os.path.dirname(out_path) if os.path.dirname(out_path) else ".", exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["candidate_id", "rank", "score", "reasoning"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n   📋 Top 10 Candidates:")
    print(f"   {'Rank':<5} {'ID':<15} {'Score':<8} {'Title':<35} {'Location'}")
    print(f"   {'─'*90}")
    for row in rows[:10]:
        cid = row["candidate_id"]
        candidate = next(c for c in top100 if c["candidate_id"] == cid)
        title = candidate["profile"].get("current_title", "")[:33]
        location = candidate["profile"].get("location", "")[:20]
        print(f"   {row['rank']:<5} {cid:<15} {row['score']:<8} {title:<35} {location}")

    print(f"\n✅ Step 8 — CSV written to: {out_path}")
    print(f"   Total rows: {len(rows)}")
    print(f"\n🎉 DONE! Submit: {out_path}\n")

# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────

def main():
    args = parse_args()

    print("\n🚀 Redrob Ranker Starting...")
    print(f"   Input  : {args.candidates}")
    print(f"   Output : {args.out}")
    print(f"   Today  : {TODAY}\n")

    # Output folder banao agar nahi hai
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("✅ Step 1 — Skeleton ready!\n")

    # Step 2 — Load candidates
    candidates = load_candidates(args.candidates)
    print(f"✅ Step 2 — Data loaded! Total: {len(candidates):,}\n")

    # Step 3 — Honeypot filter
    candidates = filter_honeypots(candidates)

    # Step 4 — Hard filters
    candidates = apply_hard_filters(candidates)

    # Step 5 — Score all candidates
    candidates = score_all_candidates(candidates)

    # Step 6 — Behavioral multiplier
    candidates = apply_behavioral_multiplier(candidates)

    # Step 7 — Text intelligence
    candidates = apply_text_intelligence(candidates)

    # Step 8 — Generate reasoning + write CSV
    write_csv_and_finalize(candidates, args.out)

if __name__ == "__main__":
    main()