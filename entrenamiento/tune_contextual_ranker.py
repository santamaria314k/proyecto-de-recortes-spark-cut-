"""Evaluate a lightweight context-aware ranker on the cached CBC split.

The validation split is used for model selection; the official test split is
scored only after choosing the candidate. This does not predict future virality.
"""

from __future__ import annotations

import json
import re

import numpy as np
import torch
from sklearn.ensemble import HistGradientBoostingRegressor, ExtraTreesRegressor
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import Ridge
from sklearn.metrics.pairwise import cosine_similarity

from sparkcut_django.inference import SparkCutScorer
from tune_highlight_hybrid import position_features, score_metrics, text_only, within_video_rank
from train_highlight_ranker import ROOT, collect_data, video_groups


def lexical_features(rows):
    matrix = []
    pattern = re.compile(r"[\w']+", re.UNICODE)
    for row in rows:
        text = row["text"]
        words = pattern.findall(text.lower())
        n = max(len(words), 1)
        punct = sum(ch in "!?" for ch in text)
        caps = sum(ch.isupper() for ch in text)
        laugh = sum(w in {"haha", "hahaha", "lol", "lmao", "jajaja"} for w in words)
        unique_ratio = len(set(words)) / n
        matrix.append([
            np.log1p(n), unique_ratio,
            sum(map(len, words)) / n,
            punct / n, caps / max(len(text), 1),
            laugh / n,
            sum(w.isdigit() for w in words) / n,
            sum(w in {"what", "wow", "wait", "omg", "no", "way", "really"} for w in words) / n,
        ])
    return np.asarray(matrix, dtype=np.float32)


def text_novelty(rows, texts, vectorizer):
    tf = vectorizer.transform(texts)
    novelty = np.zeros((len(rows), 4), dtype=np.float32)
    for indexes in video_groups(rows).values():
        local = tf[indexes]
        for offset, i in enumerate(indexes):
            neighbors = [j for j in (offset - 1, offset + 1, offset - 2, offset + 2)
                         if 0 <= j < len(indexes)]
            if not neighbors:
                continue
            sims = cosine_similarity(local[offset], local[neighbors]).ravel()
            for k, sim in enumerate(sims[:4]):
                novelty[i, k] = 1.0 - float(sim)
    return novelty


def main():
    torch.set_num_threads(4)
    train, val, test = collect_data()
    train_text, val_text, test_text = map(text_only, (train, val, test))
    vectorizer = TfidfVectorizer(max_features=60000, ngram_range=(1, 2),
                                 sublinear_tf=True, min_df=3, strip_accents="unicode")
    x_train = vectorizer.fit_transform(train_text)
    x_val, x_test = vectorizer.transform(val_text), vectorizer.transform(test_text)
    targets = np.asarray([r["target"] for r in train], dtype=np.float32)
    text_model = Ridge(alpha=3.0).fit(x_train, targets)
    text_scores = [text_model.predict(x) for x in (x_train, x_val, x_test)]

    scorer = SparkCutScorer(ROOT)
    rnn_scores = [np.asarray([p["score"] for p in scorer.score_texts(texts, batch_size=192)], dtype=np.float32)
                  for texts in (train_text, val_text, test_text)]
    pos = [position_features(rows) for rows in (train, val, test)]
    lex = [lexical_features(rows) for rows in (train, val, test)]
    nov = [text_novelty(rows, texts, vectorizer)
           for rows, texts in zip((train, val, test), (train_text, val_text, test_text))]

    groups = (train, val, test)
    rank_components = []
    for rows, rnn, tfscore, pos_feat, novelty in zip(groups, rnn_scores, text_scores, pos, nov):
        # Regressed time-position score is fitted below; raw features also keep
        # segment length and relative position available to the context model.
        rank_components.append(np.column_stack([
            within_video_rank(rows, rnn),
            within_video_rank(rows, tfscore),
            within_video_rank(rows, novelty[:, 0]),
            within_video_rank(rows, novelty[:, 1]),
        ]))

    val_best = None
    for weights in ([a / 10, b / 10, c / 10, d / 10]
                    for a in range(11) for b in range(11 - a)
                    for c in range(11 - a - b) for d in [10 - a - b - c]):
        pred = rank_components[1] @ np.asarray(weights, dtype=np.float32)
        metric = score_metrics(val, pred)
        key = (metric["precision_at_3"], metric["spearman"])
        if val_best is None or key > val_best[0]:
            val_best = (key, weights, metric)

    feature_train = np.column_stack([rnn_scores[0], text_scores[0], pos[0], lex[0], nov[0]])
    feature_val = np.column_stack([rnn_scores[1], text_scores[1], pos[1], lex[1], nov[1]])
    feature_test = np.column_stack([rnn_scores[2], text_scores[2], pos[2], lex[2], nov[2]])
    learners = [
        ("hgb_leaf7", HistGradientBoostingRegressor(max_iter=250, learning_rate=0.04,
                                                     max_leaf_nodes=7, l2_regularization=2.0,
                                                     random_state=42)),
        ("hgb_leaf15", HistGradientBoostingRegressor(max_iter=250, learning_rate=0.04,
                                                      max_leaf_nodes=15, l2_regularization=2.0,
                                                      random_state=42)),
        ("extra_trees", ExtraTreesRegressor(n_estimators=300, min_samples_leaf=12,
                                             max_features=0.8, n_jobs=-1,
                                             random_state=42)),
    ]
    model_candidates = []
    for name, model in learners:
        model.fit(feature_train, targets)
        pred = model.predict(feature_val)
        metric = score_metrics(val, pred)
        model_candidates.append((name, model, pred, metric))

    for model_candidate in model_candidates:
        if val_best is None or (model_candidate[3]["precision_at_3"], model_candidate[3]["spearman"]) > val_best[0]:
            val_best = ((model_candidate[3]["precision_at_3"], model_candidate[3]["spearman"]),
                        model_candidate[0], model_candidate[3])

    print("Validation-selected result:", json.dumps({
        "blend_weights": val_best[1] if isinstance(val_best[1], list) else None,
        "candidate": val_best[1] if isinstance(val_best[1], str) else "rank_blend",
        "validation": val_best[2],
        "components_validation": {
            "rnn": score_metrics(val, rank_components[1][:, 0]),
            "tfidf": score_metrics(val, rank_components[1][:, 1]),
            "novelty_previous": score_metrics(val, rank_components[1][:, 2]),
            "novelty_next": score_metrics(val, rank_components[1][:, 3]),
            **{name: metric for name, _, _, metric in model_candidates},
        },
    }, indent=2), flush=True)

    # Select by validation; report the untouched test score once.
    if isinstance(val_best[1], str):
        selected = next(model for name, model, _, _ in model_candidates if name == val_best[1])
        test_pred = selected.predict(feature_test)
        selected_name = val_best[1]
    else:
        test_pred = rank_components[2] @ np.asarray(val_best[1], dtype=np.float32)
        selected_name = "rank_blend"
    print("Untouched test:", json.dumps({
        "selected_on_validation": selected_name,
        "test": score_metrics(test, test_pred),
        "test_rnn": score_metrics(test, rank_components[2][:, 0]),
        "test_tfidf": score_metrics(test, rank_components[2][:, 1]),
        "test_random_precision_at_3": 0.2,
    }, indent=2), flush=True)


if __name__ == "__main__":
    main()
