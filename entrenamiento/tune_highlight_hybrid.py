"""Validation-only search for a text/position ranker; never tunes on test labels."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import joblib
import numpy as np
from scipy.stats import rankdata, spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import Ridge

from train_highlight_ranker import ROOT, collect_data, video_groups
from sparkcut_django.inference import SparkCutScorer


def text_only(rows):
    out = []
    for row in rows:
        text = row["text"]
        if " Transcript: " in text:
            text = text.split(" Transcript: ", 1)[1]
        out.append(text)
    return out


def position_features(rows):
    by = video_groups(rows)
    feat = []
    for row in rows:
        vid_rows = [rows[i] for i in by[row["video_id"]]]
        length = max(r["end"] for r in vid_rows)
        feat.append([row["start"] / max(length, 1),
                     (row["end"] - row["start"]) / max(length, 1),
                     float(row["start"] / max(length, 1) < 0.05),
                     np.log(max(length, 1)) / 10])
    return np.asarray(feat, dtype=np.float32)


def within_video_rank(rows, pred):
    result = np.zeros(len(rows), dtype=np.float32)
    for indexes in video_groups(rows).values():
        if len(indexes) == 1:
            result[indexes[0]] = 0.5
        else:
            result[indexes] = (rankdata(pred[indexes], method="average") - 1) / (len(indexes) - 1)
    return result


def score_metrics(rows, pred):
    metrics = []
    for indexes in video_groups(rows).values():
        if len(indexes) < 4:
            continue
        labels = np.asarray([rows[i]["target"] for i in indexes])
        peaks = np.asarray([rows[i]["peak"] for i in indexes])
        rho = spearmanr(pred[indexes], labels).statistic if np.ptp(pred[indexes]) and np.ptp(labels) else np.nan
        top = np.argsort(-pred[indexes], kind="stable")[:3]
        metrics.append((rho, peaks[top].mean()))
    arr = np.asarray(metrics)
    return {"videos": int(len(arr)), "spearman": float(np.nanmean(arr[:, 0])),
            "precision_at_3": float(np.nanmean(arr[:, 1]))}


def main():
    train, val, test = collect_data()
    tr_txt, va_txt, te_txt = map(text_only, (train, val, test))
    vectorizer = TfidfVectorizer(max_features=60000, ngram_range=(1, 2), sublinear_tf=True,
                                 min_df=3, strip_accents="unicode")
    xtr = vectorizer.fit_transform(tr_txt)
    xva, xte = vectorizer.transform(va_txt), vectorizer.transform(te_txt)
    ytr = np.asarray([r["target"] for r in train])
    tfidf = Ridge(alpha=3.0).fit(xtr, ytr)
    tf_va, tf_te = tfidf.predict(xva), tfidf.predict(xte)

    pos = HistGradientBoostingRegressor(max_iter=150, learning_rate=0.08, random_state=42)
    pos.fit(position_features(train), ytr)
    pos_va, pos_te = pos.predict(position_features(val)), pos.predict(position_features(test))

    scorer = SparkCutScorer(ROOT)
    rnn_va = np.asarray([x["score"] for x in scorer.score_texts(va_txt)])
    rnn_te = np.asarray([x["score"] for x in scorer.score_texts(te_txt)])
    val_components = np.column_stack([within_video_rank(val, rnn_va),
                                      within_video_rank(val, tf_va),
                                      within_video_rank(val, pos_va)])
    test_components = np.column_stack([within_video_rank(test, rnn_te),
                                       within_video_rank(test, tf_te),
                                       within_video_rank(test, pos_te)])
    names = ["rnn", "tfidf", "position"]
    component_metrics = {name: score_metrics(val, val_components[:, i]) for i, name in enumerate(names)}
    component_test = {name: score_metrics(test, test_components[:, i]) for i, name in enumerate(names)}
    best = None
    for wi in range(11):
        for wt in range(11 - wi):
            wp = 10 - wi - wt
            weights = np.array([wi, wt, wp], dtype=np.float32) / 10
            pred = val_components @ weights
            metric = score_metrics(val, pred)
            key = (metric["precision_at_3"], metric["spearman"])
            if best is None or key > best[0]:
                best = (key, weights, metric)
    weights = best[1]
    tuned_test = score_metrics(test, test_components @ weights)
    result = {
        "selection": "weights maximized validation precision@3; official test untouched",
        "validation_components": component_metrics,
        "test_components": component_test,
        "selected_weights": dict(zip(names, map(float, weights))),
        "validation_selected": best[2],
        "test_selected": tuned_test,
        "test_random_precision_at_3": 0.2,
        "note": "Hybrid result must beat the RNN test P@3 before export; predictions are relative ranks within each video.",
    }
    out_dir = ROOT / "sparkcut_highlights_v5"
    out_dir.mkdir(exist_ok=True)
    for name in ("model_0.pt", "model_1.pt", "model_2.pt", "tokenizer.model"):
        shutil.copy2(ROOT / name, out_dir / name)
    joblib.dump(pos, out_dir / "position_ranker.joblib")
    config = dict(scorer.config)
    config.update({
        "version": 5,
        "rank_blend": {"rnn": float(weights[0]), "position": float(weights[2])},
        "uses_visual_context": False,
        "target_is_viral_prediction": False,
        "training_task": "within_video_replay_peak_ranking",
        "production_ready": False,
    })
    (out_dir / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    (out_dir / "metrics.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    out = out_dir / "metrics.json"
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
