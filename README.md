# TASE Intel — AI Trading Intelligence System for the Israeli Stock Market

> **Status:** Pre-implementation. Phase 1 (Data Layer) starting.
> **Spec Version:** V1.0.1
> **License:** All Rights Reserved. Private repository.

---

## Mission

Decision-support סטטיסטית ל-event-driven trading בשוק ההון הישראלי (TASE). זוהה אירועים תאגידיים, מציג התפלגויות תגובה היסטוריות, ומספק המלצת take/skip מבוססת מודל סטטיסטי דטרמיניסטי עם confidence intervals.

זו **לא** מערכת trading אוטומטית. זו **לא** מערכת ייעוץ השקעות. ראה `docs/spec/TECHNICAL_CONTRACT_V1.0.1.md` §7.10 ו-§1.

---

## ⚠️ Compliance Disclaimer

מערכת זו לשימוש אישי בלבד של ה-owner. **אין** להפיץ output, לחשוף ל-third parties, או להשתמש להחלטות השקעה של אחרים. שימוש כזה ייפול תחת חוק הסדרת העיסוק בייעוץ השקעות (תשנ"ה-1995) ויידרש רישוי שלא קיים ב-V1.

המערכת לא תפעיל live money trading עד שיתממשו תנאי promotion המפורטים ב-`TECHNICAL_CONTRACT_V1.0.1.md` §9.3 (12 חודשי paper trading + Sharpe ≥ 0.6 + compliance review).

---

## 🛑 Before You Code

**חובה לקרוא** `docs/spec/IMPLEMENTATION_GUARDRAILS_V1.0.1.md` לפני כל commit. הוא מגדיר:

- ערכים ש**אסור לשנות בשום מצב** (target formula, thresholds, embargo logic).
- SQL implementation rules (immutable raw, as-of discipline, no same-day close).
- 8 common pitfalls שגרמו לכישלון ב-projects דומים.
- 8 triggers שאומרים "תפסיק לכתוב קוד ותחזור לקרוא spec".

אם אתה מרגיש שאתה צריך לעקוף משהו — תעצור. תקרא את `IMPLEMENTATION_GUARDRAILS §7`.

---

## Spec Documents

הסט הקאנוני נמצא ב-`docs/spec/`. כל הקבצים גרסה V1.0.1. שינויים דורשים amendment formal:

| קובץ | תפקיד |
|---|---|
| `TECHNICAL_CONTRACT_V1.0.1.md` | Charter — מה המערכת ולמה. Frozen constraints. |
| `DATA_LAYER_SPEC_V1.0.1.md` | Foundation — schema, ingestion, bitemporal design, sources. |
| `DECISION_MODEL_SPEC_V1.0.1.md` | Structure — Logistic Regression Primary, walk-forward, calibration. |
| `IMPLEMENTATION_GUARDRAILS_V1.0.1.md` | Operational checklist for daily coding. |
| `AMENDMENT_V1.0.1.md` | Justification for changes from V1.0 → V1.0.1. |
| `V1_CROSS_DOCUMENT_REVIEW.md` | Historical: review that produced V1.0.1. |

**סדר קריאה מומלץ למפתח חדש:** README → IMPLEMENTATION_GUARDRAILS → TECHNICAL_CONTRACT → DATA_LAYER_SPEC → DECISION_MODEL_SPEC.

---

## Quick Start

**Prerequisites:** Docker, Docker Compose, Python 3.11+, Make.

```bash
# 1. Clone and enter
git clone <repo-url> && cd tase-intel

# 2. Setup local environment
cp .env.example .env
# Edit .env with your DB password etc.

# 3. Start Postgres + TimescaleDB
make up

# 4. Run migrations
make migrate

# 5. Run smoke tests (must all pass)
make smoke-test

# 6. Run forbidden-pattern lint
make lint
```

If any of steps 4-6 fails, **do not proceed**. Investigate the failure against the spec before any further code.

---

## Project State (V1.0.1)

### ✅ Complete
- V1.0.1 spec set (6 documents, frozen baseline).
- Cross-document consistency review (no open issues).

### 🚧 In Progress
- Phase 1: Data Layer Implementation.

### 📋 Not Started
- Phase 2: Ingestion (TASE EOD, MAYA scraper, news RSS).
- Phase 3: Event Intelligence (NLP tagger).
- Phase 4: Decision Model training pipeline.
- Phase 5: Memory layer.
- Paper trading deployment (earliest: month 4-5).

### 🔒 Frozen for V1
- Smart Money tracking (deferred to V2 — see Contract §7.6).
- Live money execution (deferred to V2 — see Contract §7.9, earliest after 12 months paper trading).
- LLM in decision path (forbidden — Contract §7.4).

---

## Tech Stack

| Component | Choice | Frozen? |
|---|---|---|
| Database | PostgreSQL 15 + TimescaleDB Community | ✓ V1.0.1 |
| Orchestration | Prefect 2.x | ✓ V1.0.1 |
| Migration | Alembic | ✓ V1.0.1 |
| Validation | Pydantic + Great Expectations | ✓ V1.0.1 |
| ML — Primary | scikit-learn (Logistic Regression) | ✓ V1.0.1 |
| ML — Challenger | LightGBM (benchmark only) | ✓ V1.0.1 |
| Monitoring | Grafana + postgres_exporter | ✓ V1.0.1 |

Stack changes = V2 bump.

---

## Decision Hierarchy

When in doubt about anything:

1. **Spec docs win.** If code disagrees with spec, code is wrong.
2. **TECHNICAL_CONTRACT wins** over DATA_LAYER_SPEC and DECISION_MODEL_SPEC.
3. **DATA_LAYER_SPEC wins** over DECISION_MODEL_SPEC (data layer is foundation).
4. **IMPLEMENTATION_GUARDRAILS** is summary, not authority — verify against full spec for any non-trivial decision.
5. If genuine spec contradiction discovered → halt code, write `AMENDMENT_V1.0.X.md`, get owner sign-off, then code.

---

## Repo Discipline

- `main` is protected. CI must pass for merge.
- Every PR must use the PR template (`.github/PULL_REQUEST_TEMPLATE.md`).
- Spec changes ≠ code changes. Spec changes go through amendment process.
- No `--no-verify` commits. No skipping of pre-commit hooks.
- No `xfail` to bypass failing tests. Either the code is wrong or the spec is wrong.

---

## Contact

```
Owner:  ____________________
Issues: GitHub issues (private repo)
```

---

**Last updated:** ____________
**Spec baseline:** V1.0.1 (signed ____________)
