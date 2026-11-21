"""Train a within-video highlight ranker from timestamped YouTube replay data.

The target is replay behavior per candidate window, ranked against other windows
from the same source video. This predicts relative standout moments, not future
virality. Encoder features are cached; pairwise ranking trains the RNN output head.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import zlib
from pathlib import Path

import numpy as np
import sentencepiece as spm
import torch
from datasets import load_dataset
from scipy.stats import rankdata, spearmanr
from sklearn.metrics import roc_auc_score
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from sparkcut_django.inference import SparkRNN, SparkCutScorer


ROOT = Path(__file__).resolve().parent
DATASET = "behavior-in-the-wild/content-behavior-corpus"
OUT_DIR = ROOT / "sparkcut_highlights_v4"
SEED = 913
MAX_LEN = 160
HIDDEN_BATCH = 96
PAIR_BATCH = 512
EPOCHS = 16
PATIENCE = 3
LR = 0.00035
WINDOW_TARGET, WINDOW_MIN, WINDOW_MAX, HOP = 25.0, 10.0, 45.0, 8.0


def finite(value):
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def make_windows(example):
    asr = [s for s in (example.get("asr_raw") or [])
           if isinstance(s, dict) and s.get("text") and finite(s.get("start")) and finite(s.get("end"))]
    markers = [m for m in (((example.get("replay_graphs") or {}).get("markers")) or [])
               if isinstance(m, dict) and finite(m.get("replay_score"))
               and finite(m.get("start")) and finite(m.get("end"))]
    if len(asr) < 3 or not markers:
        return []
    length = float((example.get("metadata") or {}).get("length") or 0)
    asr_max = max(float(s["end"]) for s in asr)
    if length <= 0 or not math.isfinite(length):
        length = asr_max
    if length < 45:
        return []
    asr_scale = 0.001 if asr_max > length * 5 else 1.0
    asr = [{"start": float(s["start"]) * asr_scale,
            "end": float(s["end"]) * asr_scale,
            "text": str(s["text"]).strip()} for s in asr]
    starts = np.array([float(m["start"]) for m in markers])
    ends = np.array([float(m["end"]) for m in markers])
    values = np.array([float(m["replay_score"]) for m in markers])
    scale = length / ends.max() if ends.max() > 0 else 1.0
    if abs(scale - 1.0) > 0.05:
        starts, ends = starts * scale, ends * scale
    annotations = example.get("blip2_annotations") or {}
    visual_arrays = [annotations.get("captions") or [], annotations.get("actions") or [],
                     annotations.get("objects") or [], example.get("ocr") or []]
    visual_count = max((len(a) for a in visual_arrays), default=0)

    def visual_context(start, end):
        if not visual_count:
            return ""
        interval = length / visual_count
        first = max(0, int(start / interval))
        last = min(visual_count, int(math.ceil(end / interval)))
        indexes = list(range(first, last))
        if len(indexes) > 20:
            indexes = [indexes[round(i * (len(indexes) - 1) / 19)] for i in range(20)]
        frames = []
        previous = set()
        for idx in indexes:
            bits = []
            for source in visual_arrays:
                if idx >= len(source):
                    continue
                item = source[idx]
                values = item if isinstance(item, list) else [item]
                for value in values:
                    value = str(value).strip() if value is not None else ""
                    key = value.casefold()
                    if value and key not in previous:
                        bits.append(value)
                        previous.add(key)
            if bits:
                frames.append("; ".join(bits))
        return " Visual events: " + " | ".join(frames) if frames else ""

    rows, i = [], 0
    while i < len(asr):
        j = i
        while (j + 1 < len(asr) and asr[j]["end"] - asr[i]["start"] < WINDOW_TARGET
               and asr[j + 1]["end"] - asr[i]["start"] <= WINDOW_MAX):
            j += 1
        start, end = asr[i]["start"], asr[j]["end"]
        text = " ".join(s["text"] for s in asr[i:j + 1]).strip()
        words = text.lower().split()
        if WINDOW_MIN <= end - start <= WINDOW_MAX and len(words) >= 12 and len(set(words)) / len(words) >= 0.30:
            overlap = np.clip(np.minimum(end, ends) - np.maximum(start, starts), 0, None)
            if overlap.sum() > 0:
                replay = float((overlap * values).sum() / overlap.sum())
                if math.isfinite(replay):
                    context = visual_context(start, end)
                    text = (context + " Transcript: " + text) if context else text
                    rows.append({"video_id": str(example.get("video_id")), "start": start,
                                 "end": end, "text": text, "replay": replay})
        nxt = i + 1
        while nxt < len(asr) and asr[nxt]["start"] < start + HOP:
            nxt += 1
        i = nxt
    if len(rows) < 5:
        return []
    y = (rankdata([x["replay"] for x in rows]) - 1) / max(1, len(rows) - 1)
    for row, target in zip(rows, y):
        row["target"] = float(target)
        row["peak"] = float(target >= 0.8)
    return rows


def split_video(video_id):
    # Stable validation split by whole video; official test split stays untouched.
    return zlib.crc32(video_id.encode("utf-8")) % 10 == 0


def collect_data():
    cache_dir = ROOT / ".hf_cbc_cache"
    print(f"Loading {DATASET} with cache in {cache_dir}", flush=True)
    ds = load_dataset(DATASET, cache_dir=str(cache_dir))
    train_rows, val_rows, test_rows = [], [], []
    seen = set()
    for split_name, target in (("train", None), ("test", test_rows)):
        for n, example in enumerate(ds[split_name]):
            video_id = str(example.get("video_id") or "")
            if not video_id or video_id in seen:
                continue
            seen.add(video_id)
            rows = make_windows(example)
            if not rows:
                continue
            if split_name == "test":
                test_rows.extend(rows)
            elif split_video(video_id):
                val_rows.extend(rows)
            else:
                train_rows.extend(rows)
            if n and n % 3000 == 0:
                print(f"  {split_name}: {n:,} videos, {len(target or train_rows):,} windows", flush=True)
    if min(map(len, (train_rows, val_rows, test_rows))) == 0:
        raise RuntimeError("CBC yielded an empty split")
    print(f"Windows train/val/test: {len(train_rows):,}/{len(val_rows):,}/{len(test_rows):,}; "
          f"videos: {len({r['video_id'] for r in train_rows}):,}/"
          f"{len({r['video_id'] for r in val_rows}):,}/{len({r['video_id'] for r in test_rows}):,}", flush=True)
    return train_rows, val_rows, test_rows


@torch.inference_mode()
def features_for(model, texts, tokenizer, device="cpu"):
    model.eval()
    features = []
    for offset in range(0, len(texts), HIDDEN_BATCH):
        seqs = [tokenizer.encode(t)[:MAX_LEN] or [1] for t in texts[offset:offset + HIDDEN_BATCH]]
        lengths = torch.tensor([len(s) for s in seqs], dtype=torch.long)
        x = torch.zeros((len(seqs), int(lengths.max())), dtype=torch.long)
        for i, seq in enumerate(seqs):
            x[i, :len(seq)] = torch.tensor(seq, dtype=torch.long)
        x = x.to(device)
        e = model.drop(model.emb(x))
        packed = nn.utils.rnn.pack_padded_sequence(e, lengths.cpu(), batch_first=True, enforce_sorted=False)
        packed_out, _ = model.rnn(packed)
        out, _ = nn.utils.rnn.pad_packed_sequence(packed_out, batch_first=True, total_length=x.size(1))
        att = model.att(out).squeeze(-1).masked_fill(x == 0, -1e9)
        pooled = model.drop((out * torch.softmax(att, dim=1).unsqueeze(-1)).sum(1))
        features.append(pooled.cpu())
    return torch.cat(features)


def video_groups(rows):
    groups = {}
    for i, row in enumerate(rows):
        groups.setdefault(row["video_id"], []).append(i)
    return groups


def make_pairs(rows):
    pairs = []
    rng = random.Random(SEED)
    for indexes in video_groups(rows).values():
        ys = [rows[i]["target"] for i in indexes]
        high = [i for i, y in zip(indexes, ys) if y >= 0.8]
        low = [i for i, y in zip(indexes, ys) if y <= 0.5]
        if not high or not low:
            continue
        choices = [(hi, lo) for hi in high for lo in low]
        if len(choices) > 48:
            choices = rng.sample(choices, 48)
        pairs.extend(choices)
    return np.asarray(pairs, dtype=np.int64)


def pair_loader(features, pairs, shuffle):
    ds = TensorDataset(torch.from_numpy(pairs[:, 0]), torch.from_numpy(pairs[:, 1]))
    return DataLoader(ds, batch_size=PAIR_BATCH, shuffle=shuffle, num_workers=0)


def predict_head(model, features):
    model.eval()
    with torch.inference_mode():
        return torch.sigmoid(model.h_main(features)[:, :2]).cpu().numpy()


def video_metrics(rows, prediction):
    grouped = video_groups(rows)
    per_video = []
    for indexes in grouped.values():
        if len(indexes) < 4:
            continue
        pred = prediction[indexes, 0]
        y = np.array([rows[i]["target"] for i in indexes])
        peak = np.array([rows[i]["peak"] for i in indexes])
        rho = spearmanr(pred, y).statistic if np.ptp(pred) and np.ptp(y) else np.nan
        k = min(3, len(indexes))
        p3 = float(peak[np.argsort(-pred, kind="stable")[:k]].mean())
        auc = roc_auc_score(peak, pred) if 0 < peak.sum() < len(peak) and np.ptp(pred) else np.nan
        per_video.append((rho, p3, auc))
    arr = np.asarray(per_video, dtype=float)
    return {
        "videos_evaluated": int(len(arr)),
        "spearman_per_video": float(np.nanmean(arr[:, 0])),
        "precision_at_3": float(np.nanmean(arr[:, 1])),
        "peak_auc_per_video": float(np.nanmean(arr[:, 2])),
        "random_precision_at_3": 0.2,
    }


def evaluate_loss(model, features, pairs, device):
    model.eval()
    losses = []
    with torch.inference_mode():
        for lo in range(0, len(pairs), PAIR_BATCH):
            batch = pairs[lo:lo + PAIR_BATCH]
            hi_s = model.h_main(features[batch[:, 0]].to(device))[:, 0]
            lo_s = model.h_main(features[batch[:, 1]].to(device))[:, 0]
            losses.append(float(torch.nn.functional.softplus(-(hi_s - lo_s)).mean().item()))
    return float(np.mean(losses))


def main():
    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    torch.set_num_threads(max(1, min(8, torch.get_num_threads())))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    train_rows, val_rows, test_rows = collect_data()
    base_config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    tokenizer_path = ROOT / "tokenizer.model"
    tokenizer = spm.SentencePieceProcessor(model_file=str(tokenizer_path))
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    base_scorer = SparkCutScorer(ROOT)
    test_texts = [r["text"] for r in test_rows]
    base_pred = np.array([x["score"] for x in base_scorer.score_texts(test_texts)])
    base_metrics = video_metrics(test_rows, np.column_stack((base_pred, base_pred)))
    print("Original model test:", json.dumps(base_metrics), flush=True)

    model = SparkRNN(base_config["vocab"], base_config["emb"], base_config["hid"],
                     base_config["layers"], base_config["drop"], base_config["n_go"],
                     base_config["n_em"], len(base_config["heads"])).to(device)
    model.load_state_dict(torch.load(ROOT / "model_0.pt", map_location=device, weights_only=True), strict=True)
    all_rows = train_rows + val_rows + test_rows
    all_texts = [r["text"] for r in all_rows]
    print("Encoding recurrent features", flush=True)
    all_features = features_for(model, all_texts, tokenizer, device)
    n_train, n_val = len(train_rows), len(val_rows)
    train_features = all_features[:n_train]
    val_features = all_features[n_train:n_train + n_val]
    test_features = all_features[n_train + n_val:]
    train_pairs, val_pairs = make_pairs(train_rows), make_pairs(val_rows)
    if not len(train_pairs) or not len(val_pairs):
        raise RuntimeError("No within-video replay ranking pairs were generated")
    print(f"Pairwise comparisons train/val: {len(train_pairs):,}/{len(val_pairs):,}", flush=True)

    for name, parameter in model.named_parameters():
        parameter.requires_grad_(name.startswith("h_main."))
    optimizer = torch.optim.AdamW(model.h_main.parameters(), lr=LR, weight_decay=0.01)
    best_loss, best_val_p3, bad = float("inf"), -float("inf"), 0
    best_path = OUT_DIR / "model_0.pt"
    train_loader = pair_loader(train_features, train_pairs, True)
    for epoch in range(EPOCHS):
        model.h_main.train()
        running, batches = 0.0, 0
        for hi, lo in train_loader:
            hi = hi.to(device)
            lo = lo.to(device)
            optimizer.zero_grad(set_to_none=True)
            hi_score = model.h_main(train_features[hi].to(device))
            lo_score = model.h_main(train_features[lo].to(device))
            rank_loss = torch.nn.functional.softplus(-(hi_score[:, 0] - lo_score[:, 0])).mean()
            target_hi = torch.tensor([train_rows[int(i)]["target"] for i in hi.cpu()], device=device)
            target_lo = torch.tensor([train_rows[int(i)]["target"] for i in lo.cpu()], device=device)
            fit_loss = (torch.nn.functional.smooth_l1_loss(torch.sigmoid(hi_score[:, 0]), target_hi)
                        + torch.nn.functional.smooth_l1_loss(torch.sigmoid(lo_score[:, 0]), target_lo)) / 2
            peak_hi = torch.ones_like(hi_score[:, 1])
            peak_lo = torch.zeros_like(lo_score[:, 1])
            cls_loss = (nn.functional.binary_cross_entropy_with_logits(hi_score[:, 1], peak_hi)
                        + nn.functional.binary_cross_entropy_with_logits(lo_score[:, 1], peak_lo)) / 2
            loss = rank_loss + 0.2 * fit_loss + 0.15 * cls_loss
            loss.backward()
            nn.utils.clip_grad_norm_(model.h_main.parameters(), 1.0)
            optimizer.step()
            running += float(loss.item())
            batches += 1
        val_loss = evaluate_loss(model, val_features, val_pairs, device)
        val_metrics = video_metrics(val_rows, predict_head(model, val_features))
        print(f"epoch={epoch + 1} train={running / max(1, batches):.4f} val_pair={val_loss:.4f} "
              f"val_P@3={val_metrics['precision_at_3']:.3f}", flush=True)
        improved = val_metrics["precision_at_3"] > best_val_p3 + 1e-6
        tie_better_loss = abs(val_metrics["precision_at_3"] - best_val_p3) <= 1e-6 and val_loss < best_loss
        if improved or tie_better_loss:
            best_loss = val_loss
            best_val_p3 = val_metrics["precision_at_3"]
            bad = 0
            torch.save(model.state_dict(), best_path)
        else:
            bad += 1
            if bad >= PATIENCE:
                break

    model.load_state_dict(torch.load(best_path, map_location=device, weights_only=True))
    val_pred = predict_head(model, val_features)
    test_pred = predict_head(model, test_features)
    tuned_metrics = video_metrics(test_rows, test_pred)
    cal_raw = 0.5 * val_pred[:, 0] + 0.5 * val_pred[:, 1]
    qs = np.percentile(cal_raw, np.linspace(0, 100, 101))
    config = dict(base_config)
    config.update({
        "version": 4,
        "n_models": 1,
        "calibration": {"method": "quantile", "x": qs.tolist(),
                        "y": (10 + 90 * np.linspace(0, 1, 101)).tolist()},
        "score_weights": {"tv": 0.0, "adj": 0.5, "pk": 0.5},
        "uses_teacher": False,
        "explanations_trained": False,
        "training_source": DATASET,
        "training_task": "within_video_highlight_ranking_from_replay_markers_and_visual_descriptions",
        "uses_visual_context": True,
        "target_is_viral_prediction": False,
        "production_ready": bool(tuned_metrics["precision_at_3"] > 0.2
                                  and tuned_metrics["precision_at_3"] >= base_metrics["precision_at_3"]),
    })
    (OUT_DIR / "tokenizer.model").write_bytes(tokenizer_path.read_bytes())
    (OUT_DIR / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    results = {
        "dataset": DATASET,
        "label": "replay score averaged over each 10–45 second transcript window; percentile ranked within its own video",
        "split": "official test videos; validation split hashed by video_id from train",
        "windows": {"train": len(train_rows), "validation": len(val_rows), "test": len(test_rows)},
        "videos": {"train": len(video_groups(train_rows)), "validation": len(video_groups(val_rows)),
                   "test": len(video_groups(test_rows))},
        "original_model_test": base_metrics,
        "pairwise_rnn_test": tuned_metrics,
        "validation_selected_precision_at_3": float(best_val_p3),
        "validation_pairwise_loss_at_selected_checkpoint": float(best_loss),
        "encoder_frozen_head_pairwise_trained": True,
        "limits": ["Replay behavior is a proxy for standout moments, not a guarantee of viral performance.",
                   "Training dataset is English-only; Spanish performance is unvalidated.",
                   "Replay markers are sparse and imperfect annotations."],
    }
    (OUT_DIR / "metrics.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2), flush=True)


if __name__ == "__main__":
    main()
