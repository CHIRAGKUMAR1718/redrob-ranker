# Redrob Hackathon — Intelligent Candidate Ranker

A rule-based candidate ranking system that ranks 100,000 candidates against a Senior AI Engineer job description.

## How It Works

- **Honeypot detection** — removes fake profiles
- **Hard filters** — location, title, experience, services-only career
- **5-component scoring engine** — career trajectory (35%), skill relevance (25%), experience quality (20%), location (10%), education (10%)
- **Behavioral multiplier** — activity, response rate, GitHub, notice period
- **Text intelligence layer** — proof words, JD alignment, metrics detection

## Setup

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```bash
python rank.py --candidates candidates.jsonl --out submission/team_001.csv
```

## Requirements

- Python 3.9+
- CPU only
- Runs in ~3 minutes
- 16GB RAM


REDROB RANKER — ARCHITECTURE
═══════════════════════════════════════════════════════════════

INPUT
  candidates.jsonl (100,000 candidates)
        │
        ▼
┌───────────────────────────────────────────────────────┐
│  STEP 1 — DATA LOADER                                 │
│  • gzip / jsonl dono support                          │
│  • 100,000 candidates load                            │
└───────────────────────────────────────────────────────┘
        │
        │  100,000 candidates
        ▼
┌───────────────────────────────────────────────────────┐
│  STEP 2 — HONEYPOT FILTER                    -38      │
│  • Expert skill + 0 duration months                   │
│  • Career months > (YOE + 4) × 12                    │
│  • 5+ advanced skills, 0 endorsements, 0 duration     │
│  • 0 experience but 2+ jobs                           │
└───────────────────────────────────────────────────────┘
        │
        │  99,962 candidates
        ▼
┌───────────────────────────────────────────────────────┐
│  STEP 3 — HARD FILTERS                    -61,705     │
│  • Wrong title (HR, Content Writer, etc.)  -24,921   │
│  • Outside India + not willing to relocate -17,748   │
│  • Ghost candidate (180d inactive)          -8,105   │
│  • Experience out of range (<3 or >20yr)    -7,854   │
│  • Pure IT services career                  -3,077   │
└───────────────────────────────────────────────────────┘
        │
        │  38,257 candidates
        ▼
┌───────────────────────────────────────────────────────┐
│  STEP 4 — SCORING ENGINE                              │
│                                                       │
│  A. Career Trajectory ──────────────────── 35%       │
│     • Product co vs services co                       │
│     • AI/ML title in career history                   │
│     • Proof words in job description                  │
│     • Tenure stability                                │
│                                                       │
│  B. Skill Relevance ────────────────────── 25%       │
│     • Core skills match (Pinecone, FAISS etc.)        │
│     • Proficiency × Duration × Endorsements           │
│     • Platform assessment score override              │
│     • duration=0 → score=0 (keyword stuffer catch)   │
│                                                       │
│  C. Experience Quality ─────────────────── 20%       │
│     • YOE sweet spot (5-9 yrs = full marks)          │
│     • Job stability (no hopping)                      │
│     • Recent jobs mein AI/ML work hai?                │
│                                                       │
│  D. Location ───────────────────────────── 10%       │
│     • Pune/Noida/Gurgaon = 1.0                       │
│     • Hyderabad/Bangalore/Mumbai = 0.9               │
│     • Willing to relocate = bonus                     │
│                                                       │
│  E. Education ──────────────────────────── 10%       │
│     • CS/AI/ML field = full marks                    │
│     • Institution tier (tier_1 > tier_2 > ...)       │
│     • M.Tech/PhD = small bonus                        │
│                                                       │
│  BASE SCORE = A×0.35 + B×0.25 + C×0.20              │
│                       + D×0.10 + E×0.10              │
└───────────────────────────────────────────────────────┘
        │
        │  38,257 scored candidates
        ▼
┌───────────────────────────────────────────────────────┐
│  STEP 5 — BEHAVIORAL MULTIPLIER (0.30 to 1.25)       │
│                                                       │
│  • Last active date    → inactive penalty             │
│    <30d=1.0  90d=0.85  180d=0.65  >180d=0.35        │
│  • Open to work        → +10% boost                  │
│  • Recruiter response  → >70%=+10%  <15%=-50%        │
│  • Notice period       → <15d=+8%   >90d=-15%        │
│  • GitHub activity     → >60=+10%   none=-3%         │
│  • Interview rate      → >80%=+5%   <30%=-15%        │
│  • Verified email+phone→ +5%                         │
│  • Skill assessments   → avg>70=+8%                  │
│                                                       │
│  FINAL SCORE = BASE SCORE × MULTIPLIER               │
└───────────────────────────────────────────────────────┘
        │
        │  38,257 final scored
        ▼
┌───────────────────────────────────────────────────────┐
│  STEP 6 — TEXT INTELLIGENCE (additive bonus +0-8%)   │
│                                                       │
│  • Proof words detection                              │
│    "shipped" "deployed" "production" "A/B test" etc. │
│  • JD phrase alignment                                │
│    "vector search" "NDCG" "hybrid retrieval" etc.    │
│  • Vague word penalty                                 │
│    "passionate" "quick learner" "team player" etc.   │
│  • Metrics detection                                  │
│    numbers like "12%" "3x" "50ms" in descriptions    │
└───────────────────────────────────────────────────────┘
        │
        │  sort by final score
        ▼
┌───────────────────────────────────────────────────────┐
│  STEP 7 — TOP 100 + REASONING GENERATOR              │
│                                                       │
│  Per candidate reasoning includes:                    │
│  • YOE + current title + location                     │
│  • Last 2 jobs (company type + duration)              │
│  • Top 3 core skills (proficiency + months)           │
│  • Availability signals (active, notice, response)    │
│  • One honest concern                                 │
└───────────────────────────────────────────────────────┘
        │
        ▼
OUTPUT
  submission/team_001.csv
  ✅ 100 rows | Validated | Stage 4 ready reasoning

═══════════════════════════════════════════════════════════════
RUNTIME:  ~3 minutes | CPU only | 16GB RAM | No internet
LANGUAGE: Python 3.13 | Zero heavy dependencies
═══════════════════════════════════════════════════════════════
