# phase2_models.py
# BHARAT EDGE - Phase 2 ML Engine v4
# FIXED: joblib/Python 3.14 compatibility + n_jobs=1

import warnings
warnings.filterwarnings('ignore')
import os
import sys

os.environ['LOKY_MAX_CPU_COUNT'] = '1'
os.environ['PYTHONWARNINGS']     = 'ignore'

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

import pandas as pd
import numpy as np
import pickle
import traceback

from sklearn.ensemble import RandomForestClassifier, ExtraTreesClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import TimeSeriesSplit, cross_val_score
from sklearn.metrics import (
    accuracy_score, classification_report,
    confusion_matrix, roc_auc_score,
)
import sklearn.base

import xgboost as xgb
import lightgbm as lgb

from phase2_features import build_features, get_feature_columns, build_live_row

print("✅ phase2_models.py loaded")

# ============================================================
# CONFIGURATION
# ============================================================

MODEL_DIR = "models"
os.makedirs(MODEL_DIR, exist_ok=True)

CONFIG = {
    'xgboost': {
        'n_estimators'     : 300,
        'max_depth'        : 4,
        'learning_rate'    : 0.03,
        'subsample'        : 0.8,
        'colsample_bytree' : 0.8,
        'min_child_weight' : 5,
        'gamma'            : 0.5,
        'reg_alpha'        : 0.5,
        'reg_lambda'       : 2.0,
        'scale_pos_weight' : 1.67,
        'eval_metric'      : 'logloss',
        'random_state'     : 42,
        'n_jobs'           : 1,
        'verbosity'        : 0,
    },
    'lightgbm': {
        'n_estimators'     : 300,
        'max_depth'        : 4,
        'learning_rate'    : 0.03,
        'subsample'        : 0.8,
        'colsample_bytree' : 0.8,
        'min_child_samples': 20,
        'reg_alpha'        : 0.5,
        'reg_lambda'       : 2.0,
        'class_weight'     : 'balanced',
        'random_state'     : 42,
        'n_jobs'           : 1,
        'verbose'          : -1,
    },
    'random_forest': {
        'n_estimators'     : 300,
        'max_depth'        : 7,
        'min_samples_split': 15,
        'min_samples_leaf' : 7,
        'max_features'     : 'sqrt',
        'class_weight'     : 'balanced',
        'random_state'     : 42,
        'n_jobs'           : 1,
    },
    'extra_trees': {
        'n_estimators'     : 300,
        'max_depth'        : 7,
        'min_samples_split': 15,
        'min_samples_leaf' : 7,
        'max_features'     : 'sqrt',
        'class_weight'     : 'balanced',
        'random_state'     : 42,
        'n_jobs'           : 1,
    },
}


# ============================================================
# SECTION 1: DATA PREPARATION
# ============================================================

def prepare_training_data(
    symbols        : list,
    period         : str   = "2y",
    vix_value      : float = 15.0,
    vix_change     : float = 0.0,
    fii_net        : float = 0.0,
    dii_net        : float = 0.0,
    sgx_gap        : float = 0.0,
    news_sentiment : float = 0.0,
    news_volume    : int   = 0,
) -> tuple:
    print(f"\n{'='*50}")
    print(f"  PREPARING TRAINING DATA")
    print(f"{'='*50}")

    all_dfs = []
    for symbol in symbols:
        print(f"  📊 {symbol}...", end=" ")
        try:
            df = build_features(
                symbol=symbol, period=period,
                vix_value=vix_value, vix_change=vix_change,
                fii_net=fii_net, dii_net=dii_net,
                sgx_gap=sgx_gap, news_sentiment=news_sentiment,
                news_volume=news_volume, verbose=False,
            )
            if not df.empty:
                df['_symbol'] = symbol
                all_dfs.append(df)
                print(f"✅ {len(df)} rows")
            else:
                print("⚠️  empty")
        except Exception as e:
            print(f"❌ {e}")

    if not all_dfs:
        return None, None, None

    combined  = pd.concat(all_dfs).sort_index()
    feat_cols = get_feature_columns()
    available = [c for c in feat_cols if c in combined.columns]

    X = combined[available].copy()
    y = combined['target_binary'].copy()
    X = X.replace([np.inf, -np.inf], np.nan).fillna(X.median())

    print(f"\n  Combined → {len(X)} rows | {len(available)} features")
    print(f"  UP:{(y==1).sum()}  DOWN:{(y==0).sum()}  "
          f"ratio={((y==0).sum()/(y==1).sum()):.2f}x")

    return X, y, available


# ============================================================
# SECTION 2: BUILD + TRAIN BASE MODELS
# ============================================================

def build_base_models() -> dict:
    return {
        'xgboost'      : xgb.XGBClassifier(**CONFIG['xgboost']),
        'lightgbm'     : lgb.LGBMClassifier(**CONFIG['lightgbm']),
        'random_forest': RandomForestClassifier(**CONFIG['random_forest']),
        'extra_trees'  : ExtraTreesClassifier(**CONFIG['extra_trees']),
    }


def train_base_models(X, y, n_splits=5):
    print(f"\n{'='*50}")
    print(f"  TRAINING BASE MODELS")
    print(f"  {len(X)} samples | {X.shape[1]} features | "
          f"{n_splits}-fold TSS CV")
    print(f"{'='*50}")

    models    = build_base_models()
    tscv      = TimeSeriesSplit(n_splits=n_splits)
    cv_scores = {}
    scaler    = StandardScaler()
    scaler.fit(X)

    for name, model in models.items():
        print(f"\n  🤖 {name.upper()}")
        try:
            acc = cross_val_score(
                model, X, y,
                cv=tscv, scoring='accuracy', n_jobs=1,
            )
            auc = cross_val_score(
                model, X, y,
                cv=tscv, scoring='roc_auc', n_jobs=1,
            )
            cv_scores[name] = {
                'acc'    : acc.mean(),
                'acc_std': acc.std(),
                'auc'    : auc.mean(),
                'auc_std': auc.std(),
            }
            model.fit(X, y)
            print(f"     CV Acc: {acc.mean():.4f}±{acc.std():.4f}  "
                  f"folds={[f'{s:.3f}' for s in acc]}")
            print(f"     CV AUC: {auc.mean():.4f}±{auc.std():.4f}")
        except Exception as e:
            print(f"     ❌ {e}")
            traceback.print_exc()
            cv_scores[name] = {
                'acc':0,'acc_std':0,'auc':0,'auc_std':0}

    return models, cv_scores, scaler


# ============================================================
# SECTION 3: SOFT VOTING
# ============================================================

def soft_vote_proba(
    base_models : dict,
    X_input     : pd.DataFrame,
) -> np.ndarray:
    """
    Manual soft voting.
    FIXED: Forces n_jobs=1 for Python 3.14 compatibility.
    """
    all_probs = []
    for name, model in base_models.items():
        try:
            if hasattr(model, 'n_jobs'):
                model.n_jobs = 1
            probs = model.predict_proba(X_input)[:, 1]
            all_probs.append(probs)
        except Exception as e:
            print(f"  ⚠️ {name} failed: {e}")
    if not all_probs:
        return np.full(len(X_input), 0.5)
    return np.mean(all_probs, axis=0)


# ============================================================
# SECTION 4: FULL TRAINING PIPELINE
# ============================================================

def train_full_ensemble(
    symbols        : list,
    period         : str   = "2y",
    vix_value      : float = 15.0,
    vix_change     : float = 0.0,
    fii_net        : float = 0.0,
    dii_net        : float = 0.0,
    sgx_gap        : float = 0.0,
    news_sentiment : float = 0.0,
    news_volume    : int   = 0,
    save_models    : bool  = True,
) -> dict:

    print(f"\n{'🤖'*20}")
    print(f"  BHARAT EDGE - ENSEMBLE TRAINING v4")
    print(f"{'🤖'*20}")

    X, y, feature_names = prepare_training_data(
        symbols=symbols, period=period,
        vix_value=vix_value, vix_change=vix_change,
        fii_net=fii_net, dii_net=dii_net,
        sgx_gap=sgx_gap, news_sentiment=news_sentiment,
        news_volume=news_volume,
    )
    if X is None:
        return {}

    n_splits = 3 if len(X) < 200 else 5
    base_models, cv_scores, scaler = train_base_models(
        X, y, n_splits)

    # Hold-out evaluation
    split  = int(len(X) * 0.80)
    X_test = X.iloc[split:]
    y_test = y.iloc[split:]

    print(f"\n{'='*62}")
    print(f"  HOLD-OUT EVALUATION")
    print(f"{'='*62}")
    print(f"  {'Model':<22} {'Acc':>7} {'AUC':>7} "
          f"{'UP_P':>7} {'UP_R':>7} {'UP_F1':>7}")
    print(f"  {'-'*60}")

    eval_results = {}
    for name, model in base_models.items():
        try:
            if hasattr(model, 'n_jobs'):
                model.n_jobs = 1
            preds = model.predict(X_test)
            probs = model.predict_proba(X_test)[:, 1]
            acc   = accuracy_score(y_test, preds)
            auc   = roc_auc_score(y_test, probs)
            rep   = classification_report(
                        y_test, preds,
                        target_names=['DOWN','UP'],
                        output_dict=True, zero_division=0)
            up_p  = rep['UP']['precision']
            up_r  = rep['UP']['recall']
            up_f1 = rep['UP']['f1-score']
            eval_results[name] = dict(
                acc=acc, auc=auc,
                up_p=up_p, up_r=up_r, up_f1=up_f1)
            print(f"  {name:<22} {acc:>7.4f} {auc:>7.4f} "
                  f"{up_p:>7.4f} {up_r:>7.4f} {up_f1:>7.4f}")
        except Exception as e:
            print(f"  {name:<22} ERROR: {e}")

    # Soft voting
    v_probs = soft_vote_proba(base_models, X_test)
    v_preds = (v_probs >= 0.5).astype(int)
    v_acc   = accuracy_score(y_test, v_preds)
    v_auc   = roc_auc_score(y_test, v_probs)
    v_rep   = classification_report(
                  y_test, v_preds,
                  target_names=['DOWN','UP'],
                  output_dict=True, zero_division=0)

    print(f"  {'SOFT VOTING':<22} {v_acc:>7.4f} {v_auc:>7.4f} "
          f"{v_rep['UP']['precision']:>7.4f} "
          f"{v_rep['UP']['recall']:>7.4f} "
          f"{v_rep['UP']['f1-score']:>7.4f}  ⭐")

    print(f"\n  Full Classification Report (Soft Voting):")
    print(classification_report(
        y_test, v_preds,
        target_names=['DOWN','UP'], zero_division=0))

    if save_models:
        _save_models(base_models, scaler, feature_names)

    ensemble = {
        'base_models'     : base_models,
        'scaler'          : scaler,
        'feature_names'   : feature_names,
        'cv_scores'       : cv_scores,
        'eval_results'    : eval_results,
        'voting_acc'      : v_acc,
        'voting_auc'      : v_auc,
        'training_samples': len(X),
    }

    print(f"\n{'='*50}")
    print(f"  ✅ TRAINING COMPLETE")
    print(f"  Voting Accuracy : {v_acc*100:.1f}%")
    print(f"  Voting AUC      : {v_auc:.4f}")
    print(f"{'='*50}")

    return ensemble


# ============================================================
# SECTION 5: SAVE / LOAD
# ============================================================

def _save_models(base_models, scaler, feature_names):
    print(f"\n  💾 Saving to '{MODEL_DIR}/'...")
    for name, m in base_models.items():
        pickle.dump(
            m,
            open(os.path.join(MODEL_DIR, f"{name}.pkl"), 'wb'))
        print(f"     ✅ {name}.pkl")
    pickle.dump(
        scaler,
        open(os.path.join(MODEL_DIR, "scaler.pkl"), 'wb'))
    pickle.dump(
        {'feature_names': feature_names},
        open(os.path.join(MODEL_DIR, "feature_names.pkl"), 'wb'))
    print(f"     ✅ scaler.pkl + feature_names.pkl")


def load_all_models() -> dict:
    print(f"  📂 Loading from '{MODEL_DIR}/'...")
    try:
        base_models = {}
        for name in ['xgboost','lightgbm',
                     'random_forest','extra_trees']:
            path = os.path.join(MODEL_DIR, f"{name}.pkl")
            base_models[name] = pickle.load(open(path, 'rb'))
            if hasattr(base_models[name], 'n_jobs'):
                base_models[name].n_jobs = 1
            print(f"     ✅ {name}")

        scaler = pickle.load(
            open(os.path.join(MODEL_DIR, "scaler.pkl"), 'rb'))
        names  = pickle.load(
            open(os.path.join(
                MODEL_DIR, "feature_names.pkl"), 'rb'))

        print(f"     ✅ scaler + feature_names")
        return {
            'base_models'  : base_models,
            'scaler'       : scaler,
            'feature_names': names['feature_names'],
        }
    except Exception as e:
        print(f"     ❌ Error loading: {e}")
        return {}


# ============================================================
# SECTION 6: CONFIDENCE SCORER
# ============================================================

def calculate_confidence(base_models, X_row) -> dict:
    individual_probs = {}
    prob_list        = []

    for name, model in base_models.items():
        try:
            if hasattr(model, 'n_jobs'):
                model.n_jobs = 1
            p = float(model.predict_proba(X_row)[0][1])
        except:
            p = 0.5
        individual_probs[name] = p
        prob_list.append(p)

    meta_prob  = float(np.mean(prob_list))
    meta_pred  = int(meta_prob >= 0.5)
    prob_array = np.array(prob_list)

    up_votes   = int((prob_array >= 0.5).sum())
    down_votes = int((prob_array < 0.5).sum())
    agreement  = (up_votes / len(prob_list) if meta_pred == 1
                  else down_votes / len(prob_list))
    std_dev    = float(np.std(prob_array))

    base_conf       = meta_prob if meta_pred == 1 else (1-meta_prob)
    agreement_bonus = (agreement - 0.5) * 30
    std_penalty     = std_dev * 20
    confidence      = float(min(99, max(1,
        base_conf*100 + agreement_bonus - std_penalty)))

    if meta_pred == 1:
        signal = ("STRONG_BUY" if confidence >= 70
                  else "BUY"    if confidence >= 55
                  else "WEAK_BUY")
    else:
        signal = ("STRONG_SELL" if confidence >= 70
                  else "SELL"    if confidence >= 55
                  else "WEAK_SELL")

    return {
        'signal'          : signal,
        'direction'       : 'UP' if meta_pred == 1 else 'DOWN',
        'confidence'      : round(confidence, 1),
        'meta_probability': round(meta_prob * 100, 1),
        'model_agreement' : round(agreement * 100, 1),
        'up_votes'        : up_votes,
        'down_votes'      : down_votes,
        'individual_probs': {k: round(v*100,1)
                             for k,v in individual_probs.items()},
        'std_dev'         : round(std_dev, 4),
    }


# ============================================================
# SECTION 7: LIVE PREDICTION ENGINE
# ============================================================

def _build_live_row(
    symbol        : str,
    feature_names : list,
    **market_kwargs
) -> pd.DataFrame:
    live_df = build_live_row(symbol=symbol, **market_kwargs)

    if live_df.empty:
        return pd.DataFrame()

    row_data = {}
    for feat in feature_names:
        if feat in live_df.columns:
            val = float(live_df[feat].values[0])
            row_data[feat] = 0.0 if (
                np.isnan(val) or np.isinf(val)) else val
        else:
            row_data[feat] = 0.0

    return pd.DataFrame([row_data], columns=feature_names)


def predict_live(symbol, ensemble, **market_kwargs) -> dict:
    X_live = _build_live_row(
        symbol        = symbol,
        feature_names = ensemble['feature_names'],
        **market_kwargs
    )
    if X_live.empty:
        return {'symbol': symbol, 'error': 'Feature build failed'}

    result = calculate_confidence(ensemble['base_models'], X_live)
    result['symbol'] = symbol
    return result


def predict_portfolio(symbols, ensemble, **market_kwargs) -> pd.DataFrame:
    print(f"\n{'='*65}")
    print(f"  📡 LIVE SIGNAL GENERATION  ({len(symbols)} symbols)")
    print(f"{'='*65}")

    results = []
    for sym in symbols:
        print(f"  🔮 {sym}...", end=" ", flush=True)
        r = predict_live(
            symbol=sym, ensemble=ensemble, **market_kwargs)
        if 'error' in r:
            print(f"⚠️  {r['error']}")
        else:
            emoji = "🟢" if r['direction'] == 'UP' else "🔴"
            print(f"{emoji} {r['signal']}  "
                  f"conf={r['confidence']:.1f}%")
            results.append(r)

    if not results:
        print("  ❌ No predictions generated!")
        return pd.DataFrame()

    df = (pd.DataFrame(results)
          .sort_values('confidence', ascending=False)
          .reset_index(drop=True))

    print(f"\n{'='*72}")
    print(f"  📊 SIGNAL TABLE")
    print(f"{'='*72}")
    print(f"  {'#':<3} {'Symbol':<14} {'Signal':<14} "
          f"{'Conf':>7} {'Dir':>5} {'Votes':>7} "
          f"{'XGB':>7} {'LGB':>7} {'RF':>7} "
          f"{'ET':>7} {'AVG':>7}")
    print(f"  {'-'*72}")

    for i, row in df.iterrows():
        p     = row.get('individual_probs', {})
        emoji = "🟢" if row['direction'] == 'UP' else "🔴"
        votes = (f"{row.get('up_votes',0)}U/"
                 f"{row.get('down_votes',0)}D")
        print(
            f"  {i+1:<3} {row['symbol']:<14} "
            f"{row['signal']:<14} "
            f"{row['confidence']:>6.1f}% {emoji:>3} "
            f"{votes:>7}  "
            f"{p.get('xgboost',0):>6.1f}%"
            f"{p.get('lightgbm',0):>6.1f}%"
            f"{p.get('random_forest',0):>6.1f}%"
            f"{p.get('extra_trees',0):>6.1f}%"
            f"{row.get('meta_probability',0):>6.1f}%"
        )
    return df


# ============================================================
# SECTION 8: FEATURE IMPORTANCE
# ============================================================

def get_feature_importance(ensemble) -> pd.DataFrame:
    feat = ensemble['feature_names']
    df   = pd.DataFrame({'feature': feat})
    for name in ['xgboost','lightgbm',
                 'random_forest','extra_trees']:
        m = ensemble['base_models'].get(name)
        if m and hasattr(m, 'feature_importances_'):
            imp = m.feature_importances_
            if len(imp) == len(feat):
                mn, mx = imp.min(), imp.max()
                df[name] = (imp-mn)/(mx-mn+1e-9)
    cols = [c for c in df.columns if c != 'feature']
    if cols:
        df['avg'] = df[cols].mean(axis=1)
        df = df.sort_values(
            'avg', ascending=False).reset_index(drop=True)
    return df


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    print("\n" + "🤖"*20)
    print("  BHARAT EDGE - ML ENGINE v4")
    print("🤖"*20)

    SYMBOLS = [
        "TCS.NS","INFY.NS","RELIANCE.NS","HDFCBANK.NS",
        "ICICIBANK.NS","WIPRO.NS","SBIN.NS","BAJFINANCE.NS",
    ]

    MARKET = dict(
        vix_value=17.21, vix_change=-4.9,
        fii_net=500, dii_net=300,
        sgx_gap=0.65, news_sentiment=0.3, news_volume=35,
    )

    ensemble = train_full_ensemble(
        symbols=SYMBOLS, period="2y",
        save_models=True, **MARKET,
    )

    if not ensemble:
        print("❌ Training failed.")
        exit()

    print(f"\n{'='*50}")
    print(f"  TOP 15 FEATURES")
    print(f"{'='*50}")
    imp = get_feature_importance(ensemble)
    for rank, (_, row) in enumerate(imp.head(15).iterrows(), 1):
        bar = "█" * int(row['avg'] * 25)
        print(f"  {rank:>2}. {row['feature']:<25} "
              f"{row['avg']:.4f}  {bar}")

    signals = predict_portfolio(
        symbols  = ["TCS.NS","INFY.NS","RELIANCE.NS",
                    "HDFCBANK.NS","WIPRO.NS","SBIN.NS"],
        ensemble = ensemble,
        **MARKET,
    )

    print(f"\n{'='*50}")
    print(f"  🎯 PHASE 2 COMPLETE")
    print(f"{'='*50}")
    print(f"  Training samples : {ensemble['training_samples']}")
    print(f"  Voting Accuracy  : {ensemble['voting_acc']*100:.1f}%")
    print(f"  Voting AUC       : {ensemble['voting_auc']:.4f}")
    print(f"  Models saved     : ./{MODEL_DIR}/")
    print(f"\n  🚀 Ready for Phase 3: Backtesting Engine!")