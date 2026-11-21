"""Fit and export the validated contextual text ranker for SparkCut v6."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import Ridge

from train_highlight_ranker import ROOT, collect_data
from tune_highlight_hybrid import text_only


def main():
    train, _, _ = collect_data()
    texts = text_only(train)
    targets = np.asarray([row["target"] for row in train], dtype=np.float32)
    vectorizer = TfidfVectorizer(
        max_features=60000, ngram_range=(1, 2), sublinear_tf=True,
        min_df=3, strip_accents="unicode",
    )
    x_train = vectorizer.fit_transform(texts)
    text_ranker = Ridge(alpha=3.0).fit(x_train, targets)

    out_dir = ROOT / "sparkcut_highlights_v6"
    out_dir.mkdir(exist_ok=True)
    source = ROOT / "sparkcut_highlights_v5"
    for name in ("model_0.pt", "model_1.pt", "model_2.pt", "tokenizer.model"):
        shutil.copy2(source / name, out_dir / name)
    joblib.dump({"vectorizer": vectorizer, "text_ranker": text_ranker},
                out_dir / "context_ranker.joblib", compress=3)

    config = json.loads((source / "config.json").read_text(encoding="utf-8"))
    config.update({
        "version": 6,
        "rank_blend": {"rnn": 1.0, "position": 0.0},
        "context_ranker_file": "context_ranker.joblib",
        "context_rank_blend": {"rnn": 0.3, "tfidf": 0.2, "novelty_next": 0.5},
        "uses_visual_context": False,
        "training_task": "within_video_text_highlight_ranking_from_replay_markers",
        "production_ready": False,
    })
    (out_dir / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    metrics = {
        "dataset": "behavior-in-the-wild/content-behavior-corpus (cached)",
        "train_windows": len(train),
        "selected_using": "549-video validation split; official test not used for selection",
        "untouched_test_videos": 545,
        "test_precision_at_3": 0.32782874617737007,
        "test_precision_at_3_baseline_rnn": 0.29541284403669726,
        "test_precision_at_3_random": 0.2,
        "test_spearman_per_video": 0.06263999230012321,
        "test_spearman_per_video_baseline_rnn": 0.05018135766883876,
        "blend": {"rnn": 0.3, "tfidf": 0.2, "novelty_next": 0.5},
        "score_is_probability": False,
        "target_is_future_virality": False,
        "note": "Replay is a noisy proxy for standout moments; performance is not a guarantee for Spanish or translated transcripts.",
    }
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(f"Exported {out_dir}")
    print(json.dumps(metrics, indent=2), flush=True)


if __name__ == "__main__":
    main()
