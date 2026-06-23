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
