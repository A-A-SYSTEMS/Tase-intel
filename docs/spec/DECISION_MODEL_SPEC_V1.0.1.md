# DECISION MODEL SPECIFICATION V1.0.1 — AI Trading Intelligence System for TASE

> **Status:** ACTIVE — V1.0.1
> **Effective Date:** ____________
> **Owner:** ____________
> **Companion to:** `TECHNICAL_CONTRACT_V1.0.1.md`, `DATA_LAYER_SPEC_V1.0.1.md`
> **Last Amended:** V1.0 → V1.0.1 (see `AMENDMENT_V1.0.1.md`)

---

## 0. Document Status & Authority

מסמך זה מגדיר את **שכבת ההחלטה הסטטיסטית** של המערכת. הוא subordinate ל-`TECHNICAL_CONTRACT_V1.md` — כל סתירה → ה-Contract מנצח.

**כללי שינוי:**

1. שינוי **architecture choice** (Primary model selection, פרק 1) דורש major bump (V1 → V2).
2. שינוי **frozen hyperparameters** (פרק 11) דורש major bump + restart validation.
3. שינוי **anti-leakage tests** (פרק 9) **אסור** ב-V1.x.
4. שינוי **decision threshold** (פרק 7) דורש major bump.
5. שינוי **calibration procedure** (פרק 6) דורש minor bump + justification.
6. שינוי **metrics or failure criteria** (פרק 10, 12) דורש minor bump.
7. כיוונון **regularization parameter `C`** ב-validation לכל refit הוא חלק מה-procedure ולא דורש bump (זה הfeature, לא bug).

**עיקרון מנחה:** המודל הזה הוא decision-support, לא decision-maker. הוא מציג probabilities calibrated עם confidence intervals. משתמש אנושי מקבל את ההחלטה הסופית. כל החלטה אוטומטית — ב-paper trading או live — חייבת לעבור את ה-thresholds המוגדרים פה ללא יוצא מן הכלל.

---

## 1. Model Architecture

### 1.1 Primary Model: Logistic Regression with Elastic Net

**רציונל לבחירה:**
1. Sample-to-feature ratio של 25:1 לא מצדיק מודל מורכב.
2. Overfitting הוא הסיכון העיקרי, לא underfitting.
3. Logistic regression נותן coefficients interpretable + p-values per feature.
4. רגולריזציה Elastic Net משלבת L1 (sparsity) ו-L2 (smoothness).
5. ניתן לbootstrap CIs בעלות חישובית סבירה.
6. אם linear model לא מוצא edge — שום מודל מורכב לא ימצא אמיתי.

**Implementation:**

```python
from sklearn.linear_model import LogisticRegression

primary_model = LogisticRegression(
    penalty='elasticnet',
    solver='saga',
    l1_ratio=0.5,                      # FROZEN
    C=<tuned per refit on validation>,  # see §11
    max_iter=5000,
    class_weight='balanced',           # FROZEN — handles slight imbalance
    fit_intercept=True,
    random_state=42,                   # FROZEN
    n_jobs=-1
)
```

### 1.2 Challenger Model: LightGBM

**Role:** השוואה בלבד. **לא** מקבל החלטות מסחר ב-V1.

**Purpose:**
- אם Challenger > Primary באופן עקבי ב-OOS → signal שייתכן שיש pattern non-linear ש-Primary מפספס. **זה לא מצדיק החלפה**, אלא הצדקה לדיון amendment ב-V2.
- אם Primary > Challenger → תיקוף שהבחירה ב-linear model נכונה לdata size.
- אם שניהם דומים (Δ-AUC < 0.02) → Primary נשאר משום פשטות והסבירה.

**Implementation:**

```python
import lightgbm as lgb

challenger_model = lgb.LGBMClassifier(
    objective='binary',
    metric='binary_logloss',
    max_depth=3,                       # FROZEN
    min_data_in_leaf=50,               # FROZEN
    learning_rate=0.03,                # FROZEN
    n_estimators=500,                  # FROZEN (early stopping enforces)
    early_stopping_rounds=50,          # FROZEN
    colsample_bytree=0.7,              # FROZEN
    subsample=0.7,                     # FROZEN
    subsample_freq=1,                  # FROZEN
    reg_alpha=0.1,                     # FROZEN
    reg_lambda=1.0,                    # FROZEN
    class_weight='balanced',           # FROZEN
    random_state=42,                   # FROZEN
    n_jobs=-1,
    verbosity=-1
)
```

**הערה:** LightGBM hyperparameters **כולם מוקפאים**, בניגוד ל-`C` של LogReg. זה כדי לוודא שה-Challenger לא מקבל יתרון לא הוגן דרך tuning שה-Primary לא מקבל.

### 1.3 Forbidden Architectures (V1)

לא ייכנסו ל-V1, ולא יוערכו אפילו offline:

- ❌ Deep neural networks (MLP, LSTM, Transformers).
- ❌ Ensemble stacking (logistic + lgb stacked).
- ❌ Random Forest (Bagging without boosting — חוקי אך לא נחוץ).
- ❌ XGBoost (חופף עם LightGBM, מיותר).
- ❌ AutoML / hyperparameter search ברוחב.
- ❌ Reinforcement learning.

הגבלה זו היא שריקה לסיבה אחת: **כל מודל נוסף = surface area נוסף ל-overfitting.** השוואה לוקחת זמן, משאיב את ה-test window, ולא מספקת ערך ב-MVP.

---

## 2. Feature Preprocessing

### 2.1 Input Specification

ה-input vector מגיע מ-`features_at_event` (ראה Data Layer Spec 4.4). מכיל בדיוק את 12 הפיצ'רים מ-`TECHNICAL_CONTRACT_V1.md` פרק 3, בתוספת missing flags.

```python
RAW_FEATURE_NAMES = [
    'event_type_l1',           # categorical (6)
    'event_type_l2',           # categorical (~30)
    'event_magnitude',         # continuous
    'event_source_tier',       # ordinal (1-4)
    'market_cap_log',          # continuous
    'sector',                  # categorical (8)
    'liquidity_score',         # continuous
    'vix_level',               # continuous
    'ta35_trend',              # continuous
    'usdils_5d_change',        # continuous
    'recent_return_20d',       # continuous
    'volatility_20d',          # continuous
]

MISSING_FLAGS = [
    'event_magnitude_missing',  # binary, 0/1
]
```

**אסור** להוסיף features אחרים. אסור interaction features (Contract 7.1).

### 2.2 Preprocessing Pipeline (Frozen)

```python
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import StandardScaler

# CONTINUOUS FEATURES
continuous = [
    'event_magnitude', 'market_cap_log', 'liquidity_score',
    'vix_level', 'ta35_trend', 'usdils_5d_change',
    'recent_return_20d', 'volatility_20d'
]

# ORDINAL — kept as integer
ordinal = ['event_source_tier']

# CATEGORICAL — target encoded with smoothing (custom transformer, see 2.3)
categorical = ['event_type_l1', 'event_type_l2', 'sector']

# BINARY FLAGS — pass through
binary = ['event_magnitude_missing']

preprocessor = ColumnTransformer(
    transformers=[
        ('cont', StandardScaler(), continuous),
        ('ord', 'passthrough', ordinal),
        ('cat', BayesianTargetEncoder(smoothing=30), categorical),
        ('bin', 'passthrough', binary)
    ],
    remainder='drop'
)
```

**Critical:**
- `StandardScaler` fit על **training fold בלבד** — לעולם לא על validation/test.
- `BayesianTargetEncoder` (custom, ראה 2.3) fit על training fold בלבד.

### 2.3 Bayesian Target Encoder

```python
class BayesianTargetEncoder:
    """
    Replaces categorical value with smoothed mean of target.
    
    encoded(category) = (sum_target_in_category + global_mean * smoothing) /
                        (count_in_category + smoothing)
    
    This shrinks rare categories toward global mean.
    Smoothing parameter k=30 is FROZEN per Contract 3.1.
    """
    def __init__(self, smoothing=30):
        self.smoothing = smoothing
        self.encodings_ = {}
        self.global_mean_ = None
        
    def fit(self, X, y):
        self.global_mean_ = y.mean()
        for col in X.columns:
            stats = pd.DataFrame({'cat': X[col], 'y': y}).groupby('cat')['y'].agg(['sum', 'count'])
            stats['encoded'] = (stats['sum'] + self.global_mean_ * self.smoothing) / \
                               (stats['count'] + self.smoothing)
            self.encodings_[col] = stats['encoded'].to_dict()
        return self
    
    def transform(self, X):
        result = X.copy()
        for col in X.columns:
            result[col] = X[col].map(self.encodings_[col]).fillna(self.global_mean_)
        return result.values
```

**אסור** לשנות את הסיגנטורה או הפרמטר `smoothing` ב-V1.x.

### 2.4 Missing Value Handling (Recap)

מ-Contract 6.3, ב-event ingestion רוב הfeatures חסרים → drop event. החריגים שמגיעים למודל:

| Feature | Missing handling at model |
|---|---|
| `event_type_l2` | Imputed with `__missing__` token; treated as separate category |
| `event_magnitude` | Imputed with `0.0`; flag `event_magnitude_missing = 1` |
| `liquidity_score` (partial) | Already recomputed at ingestion; no model-level handling |
| `usdils_5d_change` (forward-filled) | Already handled at ingestion |
| `vix_level` (forward-filled) | Already handled at ingestion |

**Critical:** המודל לא מקבל `NaN` values אף פעם. אם NaN מגיע → bug ב-data layer, abort training.

### 2.5 Feature Vector Validation Before Training

לפני כל ריצת אימון:

```python
def validate_feature_matrix(X, y):
    assert X.isnull().sum().sum() == 0, "NaN values in features"
    assert len(X) == len(y), "Length mismatch"
    assert len(X) >= 300, f"Insufficient training data: {len(X)} < 300"
    assert y.nunique() == 2, "Target must be binary"
    assert 0.05 <= y.mean() <= 0.95, f"Class imbalance extreme: {y.mean()}"
    
    # Feature-level checks
    for col in continuous + ['event_magnitude_missing']:
        assert X[col].notna().all(), f"NaN in {col}"
    
    # Cardinality sanity
    for col in categorical:
        n_unique = X[col].nunique()
        assert 2 <= n_unique <= 50, f"{col} has {n_unique} unique values"
    
    return True
```

Failure → abort training, log to `model_training_failures` table.

---

## 3. Target Construction

### 3.1 Definition

```
forward_return_5d(event) = adj_close(t+5) / adj_close(t-1) - 1

target(event) = 1 if forward_return_5d > total_costs × 1.5 else 0

total_costs = commission_round_trip + slippage_round_trip + (spread_pct × 2)
            = 0.0020 + 0.0010 + (spread_pct × 2)
            = 0.0030 + (spread_pct × 2)
```

זהה לContract §5.4 (V1.0.1).

הסבר:
- `t-1`: סגירת ה-trading day האחרון שלפני `event_observable_at` (מחיר knowable בעת ההחלטה). מחושב דרך `subtract_trading_days(date(event_observable_at), 1)`.
- `t+5`: סגירת ה-trading day החמישי אחרי `event_observable_at` (holding horizon ה-MVP).
- `× 1.5`: margin of safety מעל transaction costs.
- `spread_pct`: נלקח מ-`features_at_event.features.spread_pct` (Data Layer §4.4).

### 3.2 Why 5d horizon

חלון של 5 ימי מסחר נבחר כי:
- מספיק קצר כדי שהסיגנל רלוונטי לאירוע (לא נבלע ברעש שוק ארוך-טווח).
- מספיק ארוך כדי לאפשר reaction לא מיידית (institutional accumulation, news propagation).
- מתאים ל-Contract 1.3 (1-10 ימי מסחר holding).

### 3.3 Alternative Target — `forward_return_10d`

נבנה ב-features_at_event במקביל אך **לא משמש** לאימון Primary Model ב-V1. נשמר ל-Memory output (Contract 4.8) ול-evaluation analysis בלבד.

### 3.4 Target Computation Rules

**Anti-leakage:** target נחשב **רק** מ-`prices_daily` עם `recorded_at <= calculation_time` ו-`as_of_query` של הזמן. לא משתמשים ב-corrections רטרואקטיביות שהגיעו אחר כך.

**Corporate action handling:**
- אם split/dividend בין t-1 ל-t+5 → `adj_close` לוקח את זה בחשבון.
- אם delisting בין t-1 ל-t+5 → מקרה מיוחד (3.5).

### 3.5 Edge Cases

| Scenario | Action |
|---|---|
| Stock halted full window (volume=0 for all 5 days) | Drop from training |
| Delisting between t-1 and t+5 | Use last available adj_close as t+5; flag |
| Less than 5 trading days available (recent events) | Drop event (cannot compute target) |
| Spread data missing at t-1 | Use sector median spread × 1.5 (conservative) |

### 3.6 Target Distribution Validation

לפני אימון:
```python
target_rate = y_train.mean()
assert 0.20 <= target_rate <= 0.55, \
    f"Target rate {target_rate} outside expected range"
```

אם < 0.20: סף costs גבוה מדי או holding horizon לא תואם. אם > 0.55: כנראה look-ahead bug.

### 3.7 Cost Model (Frozen V1)

```python
COST_MODEL = {
    'commission_per_side': 0.0010,  # 10 bps
    'commission_round_trip': 0.0020,
    'slippage_per_side': 0.0005,    # 5 bps assumption
    'slippage_round_trip': 0.0010,
    'spread_multiplier': 2.0,        # cross spread once entering, once exiting
    'safety_margin': 1.5             # require 1.5x costs for take label
}
```

`spread` נלקח מ-`features_at_event` (mean 20-day daily avg spread של המניה ב-t-1).

**שינוי COST_MODEL = bump גרסה.** זה משפיע על labels, ולכן על כל training.

---

## 4. Train / Validation / Test Split

### 4.1 Walk-Forward Setup (Frozen)

```
Train window:         5 שנים rolling
Validation window:    1 שנה consecutive
Test window:          1 שנה consecutive
Embargo:              5 trading days between train end & test start
Refit cadence:        Every 6 months
```

### 4.2 Visualization

```
Year:    [-7][-6][-5][-4][-3][-2][-1][ 0]
                                              ↑ now (refit point)
Train:    ████████████████████████
                                Val:  ████
                            Embargo:  ▓
                                Test:      ████
                                            ↑ this is where we report performance
```

### 4.3 Embargo Implementation

Embargo מחושב **בימי מסחר**, לא בימי לוח. שימוש בfunction `subtract_trading_days` של Data Layer (§5.4):

```python
from datetime import date, timedelta
import psycopg  # or db connector of choice

def subtract_trading_days(end_date: date, n_trading_days: int) -> date:
    """
    Returns the date that is n_trading_days strictly before end_date,
    using the TASE trading calendar.
    
    Implementation: query Data Layer's subtract_trading_days() PostgreSQL function.
    Local Python fallback for testing only.
    """
    return db.execute(
        "SELECT subtract_trading_days(%s, %s)",
        (end_date, n_trading_days)
    ).fetchone()[0]


def apply_embargo(events_df, train_end: date, embargo_trading_days: int = 5):
    """
    Remove events from validation/test window that fall within the trading-day
    embargo immediately following train_end.
    """
    # Compute embargo end date by adding trading days (not calendar days)
    embargo_end_date = add_trading_days(train_end, embargo_trading_days)
    embargo_start = pd.Timestamp(train_end) + pd.Timedelta(seconds=1)
    embargo_end = pd.Timestamp(embargo_end_date) + pd.Timedelta(hours=23, minutes=59, seconds=59)
    
    return events_df[~events_df['event_observable_at'].between(embargo_start, embargo_end)]


def add_trading_days(start_date: date, n_trading_days: int) -> date:
    """Inverse of subtract_trading_days. Implemented via Data Layer SQL function."""
    return db.execute(
        "SELECT add_trading_days(%s, %s)",  # see Data Layer §5.4
        (start_date, n_trading_days)
    ).fetchone()[0]
```

**Critical:** `timedelta(days=N)` is **forbidden** for embargo computation. Always use trading-day math.

### 4.4 Sample Weighting

Exponential decay על סדר זמן:

```python
def compute_sample_weights(events_df, ref_date, half_life_years=3.0):
    years_ago = (ref_date - events_df['event_observable_at']).dt.total_seconds() / (365.25 * 86400)
    weights = 0.5 ** (years_ago / half_life_years)
    return weights.values
```

**Frozen:** `half_life_years = 3.0`. זהה ל-Memory recency weight (Contract 4.6).

### 4.5 Stratification — Forbidden

**אסור** לעשות stratified split על: company, sector, event_type, או כל feature אחר. הסיבה: הtemporal ordering הוא הקובע. stratified split יכניס דגימות עתידיות לtrain.

### 4.6 Cross-Validation — Forbidden in V1

K-fold CV לא תואם לdata temporally ordered. **אסור** ב-V1.

חלופה (V2 considered): Combinatorial Purged Cross-Validation (CPCV) של López de Prado. דורש implementation careful לpurging ו-embargoing. ב-V1 — walk-forward simple מספיק.

### 4.7 Test Set Sanctity (CRITICAL)

ה-test window נחשף **רק** אחרי שכל ההחלטות של feature engineering, hyperparameter tuning, ו-model selection נסגרו על training + validation.

**אכיפה:**
- DB-level: `tests_window_views.log` מתעדת כל query על test data.
- Code review: כל code שאוקלים ל-`is_test=True` flag דורש 2-eyes approval.
- Auto-warning: אם test window נסקר > 3 פעמים בתוך validation cycle אחד → freeze, investigate.

### 4.8 First Refit Date (Cold Start)

ה-training הראשון של V1 דורש ≥ 7 שנים של clean data ב-curated layer:
- 5 שנים train + 1 שנה val + 1 שנה test = 7 שנים.

לפני שיש 7 שנים → **המודל לא רץ ב-paper trading**. דאטה collection בלבד.

---

## 5. Training Procedure

### 5.1 Per-Refit Procedure (Run Every 6 Months)

```python
def refit_decision_model(refit_date):
    # 1. Define windows — embargo in TRADING DAYS via Data Layer helper
    test_end = refit_date
    test_start = test_end - timedelta(days=365)
    val_end = subtract_trading_days(test_start, 5)         # 5 trading days embargo
    val_start = val_end - timedelta(days=365)
    train_end = subtract_trading_days(val_start, 5)        # 5 trading days embargo
    train_start = train_end - timedelta(days=365 * 5)
    
    # 2. Fetch data via as-of queries (Data Layer §5.4)
    train_events = fetch_events_as_of(train_start, train_end, as_of=refit_date)
    val_events = fetch_events_as_of(val_start, val_end, as_of=refit_date)
    
    # 3. Build feature matrices
    X_train, y_train = build_features_targets(train_events)
    X_val, y_val = build_features_targets(val_events)
    
    # 4. Validate inputs (§2.5)
    validate_feature_matrix(X_train, y_train)
    validate_feature_matrix(X_val, y_val)
    
    # 5. Compute sample weights
    w_train = compute_sample_weights(train_events, ref_date=train_end)
    
    # 6. Tune C on validation only
    best_C = tune_C(X_train, y_train, w_train, X_val, y_val)
    
    # 7. Fit Primary Model on train (with chosen C)
    primary = train_primary(X_train, y_train, w_train, C=best_C)
    
    # 8. Calibrate on validation (§6)
    primary_calibrated = calibrate(primary, X_val, y_val)
    
    # 9. Fit Challenger Model (LightGBM) — frozen hparams
    challenger = train_challenger(X_train, y_train, w_train, X_val, y_val)
    challenger_calibrated = calibrate(challenger, X_val, y_val)
    
    # 10. Bootstrap CIs (§6) — Primary only
    bootstrap_models = train_bootstrap_ensemble(X_train, y_train, w_train, C=best_C, n=100)
    
    # 11. Run anti-leakage tests (§9)
    leakage_results = run_leakage_tests(X_train, y_train, X_val, y_val, primary)
    assert leakage_results.passed, f"Leakage detected: {leakage_results}"
    
    # 12. Persist model artifacts
    save_model_version(
        primary=primary_calibrated,
        challenger=challenger_calibrated,
        bootstrap=bootstrap_models,
        metadata={
            'refit_date': refit_date,
            'train_window': (train_start, train_end),
            'val_window': (val_start, val_end),
            'test_window': (test_start, test_end),
            'best_C': best_C,
            'feature_set_version': 'v1.0',
            'train_size': len(X_train),
            'val_size': len(X_val),
            'leakage_tests': leakage_results,
        }
    )
    
    # 13. Test set evaluation (LAST — only after model frozen)
    X_test, y_test = build_features_targets(fetch_events_as_of(test_start, test_end, as_of=refit_date))
    test_metrics = evaluate(primary_calibrated, X_test, y_test)
    challenger_test_metrics = evaluate(challenger_calibrated, X_test, y_test)
    
    log_test_results(test_metrics, challenger_test_metrics)
    
    # 14. Deployment gating (§14)
    deploy_if_passes_gates(primary_calibrated, test_metrics)
```

### 5.2 Tuning `C` Hyperparameter

**Allowed search space:** `C ∈ {0.01, 0.03, 0.1, 0.3, 1.0, 3.0, 10.0}` (7 values, FROZEN).

```python
def tune_C(X_train, y_train, w_train, X_val, y_val):
    best_C = None
    best_score = -np.inf
    for C in [0.01, 0.03, 0.1, 0.3, 1.0, 3.0, 10.0]:
        model = LogisticRegression(
            penalty='elasticnet', solver='saga', l1_ratio=0.5,
            C=C, max_iter=5000, class_weight='balanced',
            random_state=42, n_jobs=-1
        )
        model.fit(X_train, y_train, sample_weight=w_train)
        val_score = roc_auc_score(y_val, model.predict_proba(X_val)[:, 1])
        if val_score > best_score:
            best_score = val_score
            best_C = C
    return best_C
```

**Rules:**
- Search **only** on validation set.
- ABSOLUTELY NOT on test set.
- Search space is frozen — לא להוסיף ערכים, לא להגדיל את ה-grid.
- אם best_C על קצה ה-grid (0.01 או 10.0) → log warning. אם זה קורה ב-2 refits עוקבים → consider amendment.

### 5.3 No Tuning Allowed Beyond `C`

ב-Primary Model, רק `C` נבחר ב-validation. כל שאר הפרמטרים (l1_ratio, class_weight, etc.) frozen.

ב-Challenger Model, **כלום** נבחר ב-validation (כל ה-hparams frozen).

**אסור:**
- Hyperparameter searches רחבים.
- Bayesian optimization.
- Optuna / Hyperopt.
- מחקר על ערכים אחרים של l1_ratio.

---

## 6. Calibration

### 6.1 Why Calibrate

Logistic regression נותן probabilities, אבל לא בהכרח calibrated (כלומר, החיזוי p=0.7 לא בהכרח אומר שב-70% מהמקרים האירוע מתממש). ב-decision support, calibration קריטית כדי שה-thresholds יהיו משמעותיים.

### 6.2 Calibration Procedure (Frozen)

**Method:** Isotonic Regression on validation set.

```python
from sklearn.calibration import CalibratedClassifierCV

def calibrate(fitted_model, X_val, y_val):
    """
    NOTE: We use 'prefit' mode because we already trained on full train set.
    We never re-fit base model during calibration.
    """
    calibrated = CalibratedClassifierCV(
        estimator=fitted_model,
        method='isotonic',     # FROZEN — non-parametric, robust to small data
        cv='prefit'
    )
    calibrated.fit(X_val, y_val)
    return calibrated
```

### 6.3 Why Isotonic, Not Sigmoid

- **Isotonic** non-parametric, מתאים יותר ל-Logistic Regression שכבר מחזירה probabilities (sigmoid calibration עליו = redundant).
- **Sigmoid (Platt scaling)** מתאים ל-SVM, לא לLogReg.

**Frozen.** שינוי = bump.

### 6.4 Calibration Quality Check

לאחר calibration, על validation:

```python
def check_calibration(calibrated_model, X_val, y_val):
    p_pred = calibrated_model.predict_proba(X_val)[:, 1]
    
    # Brier score
    brier = brier_score_loss(y_val, p_pred)
    assert brier <= 0.245, f"Calibration too poor: brier={brier}"
    
    # Reliability across deciles
    for decile in np.arange(0, 1, 0.1):
        mask = (p_pred >= decile) & (p_pred < decile + 0.1)
        if mask.sum() < 30:
            continue
        actual_rate = y_val[mask].mean()
        expected_rate = p_pred[mask].mean()
        diff = abs(actual_rate - expected_rate)
        if diff > 0.10:
            log_warning(f"Decile {decile}: actual={actual_rate}, predicted={expected_rate}")
    
    # Calibration on test (LATER, after deployment gate)
    return brier
```

### 6.5 Re-calibration Cadence

Re-calibration בכל refit (כל 6 חודשים), כחלק מ-`refit_decision_model`.

**אין** re-calibration intra-refit (כלומר, לא משנים calibration באמצע 6-month period גם אם performance ב-paper trading מתדרדר). לדבר מהסוג הזה — soft kill (פרק 12).

---

## 7. Bootstrap Confidence Intervals

### 7.1 Procedure (Frozen)

```python
def train_bootstrap_ensemble(X_train, y_train, w_train, C, n=100):
    """
    Train n=100 bootstrap models on resampled training data.
    Each prediction will be the distribution of these n models' outputs.
    """
    models = []
    rng = np.random.RandomState(42)  # FROZEN seed
    
    for i in range(n):
        # Resample with replacement, same size
        idx = rng.choice(len(X_train), size=len(X_train), replace=True)
        X_boot = X_train.iloc[idx]
        y_boot = y_train.iloc[idx]
        w_boot = w_train[idx]
        
        model = LogisticRegression(
            penalty='elasticnet', solver='saga', l1_ratio=0.5,
            C=C, max_iter=5000, class_weight='balanced',
            random_state=42 + i,  # different seed per bootstrap
            n_jobs=-1
        )
        model.fit(X_boot, y_boot, sample_weight=w_boot)
        models.append(model)
    
    return models
```

**Frozen parameters:**
- `n = 100`.
- `random_state = 42` for resampling.
- Bootstrap with replacement, same size.

### 7.2 Inference With CI

```python
def predict_with_ci(bootstrap_models, calibrated_primary, X):
    # Point estimate from calibrated primary
    p_point = calibrated_primary.predict_proba(X)[:, 1]
    
    # CI from bootstrap ensemble (uncalibrated probabilities)
    boot_preds = np.array([
        m.predict_proba(X)[:, 1] for m in bootstrap_models
    ])  # shape: (n_models, n_samples)
    
    p_lower = np.percentile(boot_preds, 10, axis=0)
    p_upper = np.percentile(boot_preds, 90, axis=0)
    
    return {
        'p_point': p_point,
        'p_lower_p10': p_lower,
        'p_upper_p90': p_upper,
        'ci_width': p_upper - p_lower
    }
```

### 7.3 Why Bootstrap, Not Other Methods

- **Bootstrap:** robust, non-parametric, sample size aware. מתאים לdata size שלנו.
- **Conformal prediction:** מצוין אבל overhead implementation; דחוי ל-V2.
- **Bayesian (PyMC, Pyro):** עלות חישובית גבוהה ב-100x; לא מצדיק ב-V1.
- **Naive normal approximation:** משתמש ב-`σ` של coefficients — לא מתאים ל-non-linear softmax output.

### 7.4 Calibration of Bootstrap CIs

ה-bootstrap ensemble **לא** עובר calibration — הוא משמש ל-uncertainty quantification, לא ל-point estimation. ה-point estimate מגיע מ-calibrated_primary.

---

## 8. Decision Rules

### 8.1 Decision Logic (Frozen)

```python
def make_decision(p_point, p_lower_p10, p_upper_p90, memory_output, features, event):
    """
    Returns: 'take' | 'skip'
    + reason logged for every decision
    """
    
    # Rule 0: Tagger confidence pre-check (per Contract §6.6)
    # Events with low tagger confidence don't generate decisions in MVP.
    if event.tagger_confidence is not None and event.tagger_confidence < 0.6:
        return 'skip', 'low_tagger_confidence'
    
    # Rule 1: Risk Pre-filter (per Contract §6.7)
    if features['liquidity_score'] < 0.4:
        return 'skip', 'pre_filtered_illiquid'
    
    # Rule 2: CI crosses 50% — auto-skip (per Contract §5.7)
    if p_lower_p10 < 0.5 < p_upper_p90:
        return 'skip', 'ci_crosses_threshold'
    
    # Rule 3: Threshold check
    threshold = 0.55  # FROZEN
    
    # Rule 3a: Hardened threshold if Memory insufficient (per Contract §6.2)
    if memory_output['flags'] and 'insufficient_memory' in memory_output['flags']:
        threshold = 0.65
    
    # Rule 4: Final decision
    if p_point > threshold:
        return 'take', f'p={p_point:.3f}, threshold={threshold}'
    else:
        return 'skip', f'p={p_point:.3f}, threshold={threshold}'
```

### 8.2 Threshold Justification

`threshold = 0.55`:
- Above 0.5 (random) by 5 percentage points → meaningful edge required.
- Below 0.6 → not too aggressive; allows positive expected value with margin.
- Aligned with `target` definition that already includes 1.5x cost margin.

`threshold_hardened = 0.65` (Memory insufficient):
- When historical context unavailable, require stronger model signal.
- 10 percentage points above standard threshold → conservative.

**Both frozen.** Change = V2 bump.

### 8.3 Forbidden Decision Modifiers

- ❌ Threshold tuning בbacktest כדי "לקבל יותר Sharpe".
- ❌ Position sizing מבוסס `p` (אסור: עוד פוזיציה אגרסיבית כי p=0.85). ב-MVP — flat sizing.
- ❌ Memory output כ-decision modifier אוטומטי (Memory output מוצג למשתמש; הוא מחליט איך לשקלל).
- ❌ Time-of-day modifications.
- ❌ Portfolio context (כמה positions פתוחות).

ב-V1, decision rule היא feature-of-1: הסתברות calibrated עוברת thresholds.

### 8.4 Decision Logging

לכל decision (take או skip), record ב-`decisions_log`. ה-DDL מוגדר ב-Data Layer §4.6 ו-mirror גם פה ל-reference:

```sql
CREATE TABLE decisions_log (
    decision_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID NOT NULL REFERENCES events(event_id),
    decision TEXT NOT NULL,                    -- 'take' | 'skip'
    reason TEXT NOT NULL,
    p_point NUMERIC NOT NULL,
    p_lower_p10 NUMERIC NOT NULL,
    p_upper_p90 NUMERIC NOT NULL,
    threshold_applied NUMERIC NOT NULL,
    memory_flags TEXT[],
    model_version TEXT NOT NULL,
    feature_set_version TEXT NOT NULL,
    decided_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

ראה Data Layer §4.6 ל-DDL מלא, indexes, constraints, ועבור גם `model_deployments` ו-`paper_trading_results`.

**Critical:** decision logged BEFORE outcome known. Audit trail.

---

## 9. Anti-Leakage Tests (חוקתי)

חובה לרוץ ב-CI/CD לפני כל deployment. כל test failure = deployment block.

### 9.1 Random Label Test

```python
def test_random_label():
    """
    Shuffle training labels. Re-train. AUC on validation must be ≈ 0.50.
    If model achieves edge on random labels → leakage.
    """
    rng = np.random.RandomState(42)
    y_random = rng.permutation(y_train.values)
    
    model_random = LogisticRegression(...).fit(X_train, y_random, sample_weight=w_train)
    auc_on_val = roc_auc_score(y_val, model_random.predict_proba(X_val)[:, 1])
    
    assert 0.45 <= auc_on_val <= 0.55, \
        f"LEAKAGE: random labels achieve AUC={auc_on_val} on validation"
```

### 9.2 Future Feature Test

```python
def test_no_future_features():
    """
    Verify every feature timestamp <= event_observable_at.
    """
    for event in train_events.itertuples():
        feature_record = features_at_event_table.get(event.event_id)
        for feature_name, feature_metadata in feature_record.metadata.items():
            assert feature_metadata['as_of'] <= event.event_observable_at, \
                f"FUTURE FEATURE: {feature_name} sourced at {feature_metadata['as_of']} > event obs {event.event_observable_at}"
```

### 9.3 Forward Shift Consistency Test

```python
def test_forward_shift():
    """
    Shift all event timestamps by +7 days. The forward returns should
    be different (non-deterministic), but the predictions on shifted
    events should be plausible (not catastrophically degraded).
    """
    shifted_events = events.copy()
    shifted_events['event_observable_at'] += pd.Timedelta(days=7)
    
    # Recompute features at new timestamps
    X_shifted = build_features(shifted_events)
    p_shifted = primary.predict_proba(X_shifted)[:, 1]
    
    # AUC on shifted data should be near baseline (random) since we
    # shifted past actual events
    # NOT a strict assertion; it's a diagnostic
    log_diagnostic('forward_shift_auc', roc_auc_score(y_shifted, p_shifted))
```

### 9.4 Train-Test Time Order Test

```python
def test_train_before_test():
    train_max = train_events['event_observable_at'].max()
    test_min = test_events['event_observable_at'].min()
    
    embargo_actual = (test_min - train_max).days
    assert embargo_actual >= 5, \
        f"EMBARGO VIOLATED: only {embargo_actual} days between train end and test start"
```

### 9.5 Target Computation Time Test

```python
def test_target_uses_no_future_corrections():
    """
    For each training event, verify target was computed from prices
    that were available at refit_date (not retroactive corrections).
    """
    for event in sample(train_events, 50):
        target_recomputed = compute_target_as_of(
            event.event_id,
            as_of=refit_date
        )
        target_in_use = train_targets[event.event_id]
        assert target_recomputed == target_in_use, \
            f"TARGET DRIFT: event {event.event_id}"
```

### 9.6 Feature Variance Test

```python
def test_feature_variance():
    """
    Each feature should have variance > 0 in training set.
    Zero variance = bug.
    Near-zero variance = no information; flag.
    """
    for col in continuous_features:
        var = X_train[col].var()
        assert var > 1e-8, f"Zero variance in {col}"
        if var < 0.01:
            log_warning(f"Near-zero variance in {col}: {var}")
```

### 9.7 Distribution Shift Test (Train vs. Test)

```python
def test_distribution_shift():
    """
    Compare feature distributions between train and test.
    Substantial shift → regime change → degraded performance expected.
    """
    for col in continuous_features:
        ks_stat, ks_p = ks_2samp(X_train[col], X_test[col])
        if ks_p < 0.001:
            log_warning(f"Distribution shift in {col}: KS={ks_stat}, p={ks_p}")
```

זה לא assertion (לא מצדיק abort), אבל log חשוב.

### 9.8 Reproducibility Test

```python
def test_reproducibility():
    """
    Re-running training with same data + version should produce identical
    coefficients (within float precision).
    """
    model_a = train_primary(X_train, y_train, w_train, C=best_C)
    model_b = train_primary(X_train, y_train, w_train, C=best_C)
    
    assert np.allclose(model_a.coef_, model_b.coef_, atol=1e-10), \
        "REPRODUCIBILITY FAILURE: same input → different coefficients"
```

### 9.9 All Tests Must Pass

```python
LEAKAGE_TESTS = [
    test_random_label,
    test_no_future_features,
    test_train_before_test,
    test_target_uses_no_future_corrections,
    test_feature_variance,
    test_reproducibility,
]

DIAGNOSTIC_TESTS = [
    test_forward_shift,
    test_distribution_shift,
]

def run_leakage_tests():
    for test in LEAKAGE_TESTS:
        result = test()
        if not result.passed:
            raise LeakageError(f"BLOCKED: {test.__name__}: {result.error}")
    
    for test in DIAGNOSTIC_TESTS:
        result = test()
        log_diagnostic(test.__name__, result)
    
    return AllPassed()
```

---

## 10. Metrics

### 10.1 Per-Refit Reporting (Test Set)

לאחר freezing המודל ו-evaluation על test:

| Metric | Target | Acceptable Range |
|---|---|---|
| AUC-ROC | ≥ 0.55 | [0.52, 0.70] |
| Precision @ p > 0.55 | ≥ 0.55 | [0.50, 0.70] |
| Recall @ p > 0.55 | — | informational |
| Brier Score | ≤ 0.245 | [0.20, 0.25] |
| Log Loss | informational | — |
| Hit Rate (paper trading proxy) | ≥ 0.52 | [0.50, 0.65] |

### 10.2 Per-Trading-Period Reporting (Paper Trading)

חודשית, על פי החלטות `take`:

| Metric | Target |
|---|---|
| Sharpe Ratio (annualized) | ≥ 0.5 ב-OOS |
| Max Drawdown | ≤ 20% |
| Average Return per Take (after costs) | ≥ +0.5% |
| Win Rate | ≥ 52% |
| Number of Takes | informational |
| Average Holding Period | ≈ 5d (target) |

### 10.3 Calibration Metrics

| Metric | Target |
|---|---|
| Expected Calibration Error (ECE, 10 bins) | ≤ 0.05 |
| Maximum Calibration Error (MCE) | ≤ 0.15 |
| Brier Score | ≤ 0.245 |
| Reliability Curve (visual) | mostly within ±0.10 of diagonal |

### 10.4 Challenger Comparison

| Comparison | Action |
|---|---|
| Δ-AUC (Challenger - Primary) > +0.05 over 4 consecutive refits | Open V2 amendment for review |
| Δ-AUC ∈ [-0.02, +0.02] | Primary remains; document Challenger non-superiority |
| Δ-AUC < -0.02 | Primary remains; Challenger less effective (expected) |

**Critical:** Challenger superiority **alone** does not justify replacement. Decision-support purposes prefer interpretability + simplicity.

### 10.5 Leakage Detection Metrics

Continuously monitored:
- Random label AUC (every refit): must be ≈ 0.50.
- Live performance / Backtest performance ratio: if < 0.5 over 50+ trades → severe leakage suspect.
- Test-vs-validation AUC gap: if > 0.10 → instability or leakage.

---

## 11. Frozen Hyperparameters Summary

טבלת רפרנס מרוכזת לכל הערכים המוקפאים. שינוי = V2 unless noted.

### 11.1 Primary Model (LogReg)

| Parameter | Value | Tunable? |
|---|---|---|
| `penalty` | `elasticnet` | ❌ Frozen |
| `solver` | `saga` | ❌ Frozen |
| `l1_ratio` | `0.5` | ❌ Frozen |
| `C` | tuned per refit | ✓ on validation only, search space frozen |
| `max_iter` | `5000` | ❌ Frozen |
| `class_weight` | `balanced` | ❌ Frozen |
| `random_state` | `42` | ❌ Frozen |
| `fit_intercept` | `True` | ❌ Frozen |
| `C` search space | `{0.01, 0.03, 0.1, 0.3, 1.0, 3.0, 10.0}` | ❌ Frozen |

### 11.2 Challenger Model (LightGBM)

| Parameter | Value | Tunable? |
|---|---|---|
| `objective` | `binary` | ❌ Frozen |
| `max_depth` | `3` | ❌ Frozen |
| `min_data_in_leaf` | `50` | ❌ Frozen |
| `learning_rate` | `0.03` | ❌ Frozen |
| `n_estimators` | `500` (early stop @ 50) | ❌ Frozen |
| `colsample_bytree` | `0.7` | ❌ Frozen |
| `subsample` | `0.7` | ❌ Frozen |
| `reg_alpha` | `0.1` | ❌ Frozen |
| `reg_lambda` | `1.0` | ❌ Frozen |
| `class_weight` | `balanced` | ❌ Frozen |
| `random_state` | `42` | ❌ Frozen |

### 11.3 Preprocessing

| Parameter | Value | Tunable? |
|---|---|---|
| Continuous scaler | `StandardScaler` | ❌ Frozen |
| Categorical encoder | `BayesianTargetEncoder(smoothing=30)` | ❌ Frozen |
| Imputation policy | per Contract 6.3 | ❌ Frozen |

### 11.4 Target

| Parameter | Value | Tunable? |
|---|---|---|
| Holding horizon | 5 trading days | ❌ Frozen V1 |
| Cost margin multiplier | 1.5 | ❌ Frozen |
| Commission per side | 0.0010 | ❌ Frozen V1 (revisable on broker change) |
| Slippage assumption | 0.0005 per side | ❌ Frozen V1 |

### 11.5 Validation

| Parameter | Value | Tunable? |
|---|---|---|
| Train window | 5 years | ❌ Frozen |
| Validation window | 1 year | ❌ Frozen |
| Test window | 1 year | ❌ Frozen |
| Embargo | 5 trading days | ❌ Frozen |
| Refit cadence | 6 months | ❌ Frozen |
| Sample weight half-life | 3 years | ❌ Frozen |

### 11.6 Calibration

| Parameter | Value | Tunable? |
|---|---|---|
| Method | `isotonic` | ❌ Frozen |
| CV mode | `prefit` | ❌ Frozen |

### 11.7 Bootstrap

| Parameter | Value | Tunable? |
|---|---|---|
| `n` | 100 | ❌ Frozen |
| Random seed | 42 | ❌ Frozen |
| Resample method | with replacement, same size | ❌ Frozen |

### 11.8 Decision Rules

| Parameter | Value | Tunable? |
|---|---|---|
| `threshold` | 0.55 | ❌ Frozen |
| `threshold_hardened` (low memory) | 0.65 | ❌ Frozen |
| `liquidity_pre_filter` | `liquidity_score >= 0.4` | ❌ Frozen |
| CI lower bound | p10 | ❌ Frozen |
| CI upper bound | p90 | ❌ Frozen |

---

## 12. Failure Criteria

### 12.1 Pre-Deployment (Block Promotion)

מודל לא עובר ל-paper trading אם:

- AUC ב-test set < 0.52.
- Precision @ p > 0.55 על test < 0.50.
- Brier score על test > 0.26.
- כל leakage test נכשל.
- Random label AUC > 0.55.
- Calibration ECE > 0.08.

→ Soft kill: investigate. Possible bug, data issue, regime change.

### 12.2 Post-Deployment Soft Kill (Pause)

מודל מושעה אם, ב-rolling 6 months:

- Sharpe ratio < 0.3.
- Max drawdown > 15%.
- Hit rate < 50% over ≥ 50 trades.
- Live / Backtest performance ratio < 0.6.

→ Pause new decisions. Investigate. Possible amendments → V1.x or V2.

### 12.3 Post-Deployment Hard Kill

מערכת מסיימת תפקיד ב-MVP אם:

- 12 months paper trading completed with Sharpe < 0.0.
- Confirmed leakage discovered post-hoc.
- Major regulatory change banning system.
- Live performance < 50% of backtest performance over 100+ trades — overfitting confirmed.

→ Project terminate (per Contract 9.2).

### 12.4 Auto-Triggered Soft Kill Detection

Daily monitoring job:

```python
def check_kill_switches():
    last_50_trades = get_recent_trades(n=50)
    if len(last_50_trades) >= 50:
        sharpe = compute_sharpe(last_50_trades)
        if sharpe < 0.3:
            trigger_soft_kill('low_sharpe', sharpe)
        
        max_dd = compute_max_drawdown(last_50_trades)
        if max_dd > 0.15:
            trigger_soft_kill('high_drawdown', max_dd)
        
        hit_rate = compute_hit_rate(last_50_trades)
        if hit_rate < 0.50:
            trigger_soft_kill('low_hit_rate', hit_rate)
```

Soft kill action:
1. Set `system.allow_new_decisions = False`.
2. Alert owner.
3. Existing positions remain (paper trading log).
4. Manual unfreeze required after investigation.

---

## 13. Model Versioning

### 13.1 Version Format

`<major>.<minor>.<refit_id>`

Examples:
- `1.0.0` — initial V1 model, first refit.
- `1.0.1` — second refit (every 6 months).
- `1.1.0` — V1.1 amendment (e.g., minor change to calibration procedure).
- `2.0.0` — V2 (e.g., new architecture or feature set).

### 13.2 Persisted Artifacts (Per Refit)

```
/models/v1.0.{refit_id}/
├── primary_calibrated.pkl
├── challenger_calibrated.pkl
├── bootstrap_models.pkl
├── preprocessor.pkl
├── metadata.json
│   {
│     "version": "1.0.3",
│     "trained_at": "...",
│     "feature_set_version": "v1.0",
│     "data_layer_version": "v1.0",
│     "contract_version": "v1.0",
│     "train_window": ["2020-01-01", "2024-12-31"],
│     "val_window": ["2025-01-01", "2025-12-31"],
│     "test_window": ["2026-01-01", "2026-12-31"],
│     "best_C": 0.3,
│     "train_size": 4523,
│     "val_size": 891,
│     "test_size": 887,
│     "test_metrics": {...},
│     "leakage_tests_passed": true,
│     "code_git_sha": "abc123..."
│   }
├── coefficients.json  # Primary feature importance
├── test_predictions.csv
└── leakage_test_results.json
```

**Persistence:** Local filesystem in MVP, S3-compatible for V2.

### 13.3 Active Version Management

`/models/ACTIVE_VERSION` symlink → currently deployed version.

Switching requires:
1. New version persisted.
2. Deployment gates passed (§14).
3. Atomic symlink swap.
4. Log entry in `model_deployments`.

### 13.4 Backward Compatibility

- Old versions retained forever (audit trail).
- Backtests can be re-run on any historical version.
- Decisions logged with `model_version` for replayability.

---

## 14. Deployment Gating

### 14.1 Gates Required for Promotion

מודל חדש מקבל deployment ל-paper trading **רק** אם:

| Gate | Threshold |
|---|---|
| All leakage tests passed | ✓ required |
| AUC on test ≥ 0.52 | ✓ required |
| Precision @ p > 0.55 ≥ 0.50 | ✓ required |
| Brier on test ≤ 0.26 | ✓ required |
| Calibration ECE ≤ 0.08 | ✓ required |
| Reproducibility verified | ✓ required |
| Δ from previous model in coefficients < 50% (sanity) | ⚠️ warning if violated |
| Test-vs-validation AUC gap ≤ 0.10 | ⚠️ warning if violated |
| Owner manual sign-off | ✓ required |

### 14.2 Promotion Procedure

```python
def promote_to_paper_trading(new_version):
    # 1. Run all gates
    gates = run_deployment_gates(new_version)
    
    if not gates.all_required_passed:
        raise DeploymentBlocked(gates.failures)
    
    if gates.warnings:
        require_owner_acknowledgment(gates.warnings)
    
    # 2. Owner sign-off (CLI prompt)
    confirm = input(f"Promote {new_version} to paper trading? (yes/no): ")
    if confirm != 'yes':
        log('promotion_aborted')
        return
    
    # 3. Atomic deploy
    save_metadata(new_version, {'promoted_at': now()})
    update_active_symlink(new_version)
    
    # 4. Log
    log_deployment(new_version)
    
    # 5. Notify
    alert_owner(f"Model {new_version} now active in paper trading")
```

### 14.3 Live Money Promotion (V2 only)

V1 explicitly does **not** allow live money trading (Contract 7.9). V2 promotion requires separate spec.

Pre-conditions for V2 live promotion (recap from Contract 9.3):
- 12+ months paper trading completed.
- Sharpe ≥ 0.6 in rolling 12 months.
- Max drawdown ≤ 15%.
- Hit rate ≥ 53%.
- ≥ 100 trades.
- No leakage flags.
- Compliance review complete.

### 14.4 Rollback

If new deployment shows immediate problems (within first week):

```python
def rollback_to_previous(reason):
    previous_version = read_previous_active_version()
    update_active_symlink(previous_version)
    log_rollback(previous_version, reason)
    alert_owner_critical()
```

Rollback eligible reasons:
- Decision logging failures.
- Calibration error in production not caught in tests.
- Leakage discovery post-deployment.

NOT eligible:
- Performance below target (handled via soft kill, not rollback).

---

## 15. Explicitly Forbidden

חוקתיות. **לא** לעבור עליהן ב-V1.x.

### 15.1 Architectural Forbidden

- ❌ Adding LLMs to decision path (Contract 7.4).
- ❌ Using Memory output as feature in Decision Model (Contract 7.3).
- ❌ Adding interaction features manually (Contract 7.1).
- ❌ Using deep learning, ensembles beyond Primary+Challenger.
- ❌ Online learning / streaming updates (frozen between refits).

### 15.2 Hyperparameter Forbidden

- ❌ Tuning anything beyond `C` of Primary on validation.
- ❌ Tuning Challenger hparams at all.
- ❌ Searching over `C` outside frozen grid.
- ❌ Bayesian optimization, AutoML, Optuna.

### 15.3 Data Forbidden

- ❌ Using test window during development (Contract 8.4).
- ❌ Using future data of any kind (Contract 8.x).
- ❌ Using Memory data as features (Contract 7.3).
- ❌ Using Smart Money signals (Contract 7.6, deferred to V2).
- ❌ Using same-day close as price feature (Data Layer 8.3).
- ❌ Cross-validation k-fold on temporal data.

### 15.4 Decision Forbidden

- ❌ Threshold tuning post-hoc on test results.
- ❌ Position sizing based on `p` (flat sizing only in V1).
- ❌ Auto-execution (Contract 7.8).
- ❌ Live money trading in MVP (Contract 7.9).
- ❌ External use / third parties (Contract 7.10).

### 15.5 Process Forbidden

- ❌ Deploying without leakage tests passing.
- ❌ Deploying without owner sign-off.
- ❌ Modifying frozen hyperparameters without bumping version.
- ❌ "Just trying" non-frozen settings to see if they work.
- ❌ Using a model version retroactively (replays must use the version active at time of decision).

---

## 16. Glossary

| Term | Definition |
|---|---|
| **Primary Model** | Logistic Regression with Elastic Net; the model making decisions |
| **Challenger Model** | LightGBM; benchmark only, no decisions |
| **Refit** | Re-training on rolling window every 6 months |
| **Walk-Forward** | Sequential train/val/test splits respecting temporal order |
| **Embargo** | Time gap (5 trading days) between train and test |
| **Calibration** | Adjusting probability outputs to match empirical frequencies |
| **Bootstrap CI** | Confidence interval from resampling-based ensemble |
| **CI Crosses 50%** | When p10 < 0.5 < p90 → auto-skip |
| **Threshold** | 0.55 (frozen); 0.65 if Memory insufficient |
| **Soft Kill** | Pause new decisions pending investigation |
| **Hard Kill** | Project termination |
| **Leakage Test** | Automated check that model has not seen future data |
| **Random Label Test** | Train on shuffled labels, AUC must be ≈ 0.50 |
| **ECE** | Expected Calibration Error |
| **Brier Score** | Probabilistic forecast quality (lower better; baseline 0.25) |

---

## 17. Signatures

```
Owner:        ____________________   Date: __________
Version:      V1.0.1
Companion to: TECHNICAL_CONTRACT_V1.0.1.md, DATA_LAYER_SPEC_V1.0.1.md
Document hash (SHA-256): __________________________________
Repo location: DECISION_MODEL_SPEC_V1.0.1.md
Amendments applied: AMENDMENT_V1.0.1.md
```

---

**END OF DECISION MODEL SPECIFICATION V1.0.1**
