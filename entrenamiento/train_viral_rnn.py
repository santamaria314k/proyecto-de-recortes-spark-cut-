"""Fine-tune SparkCut on rights-cleared video engagement (weak clip labels).

Run with .venv_sparkcut/Scripts/python.exe train_viral_rnn.py
The source records have video-level engagement, so a sampled transcript window
inherits a noisy video label. The held-out test split is grouped by channel.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from pathlib import Path

import numpy as np
import sentencepiece as spm
import torch
from datasets import Dataset, concatenate_datasets
from scipy.stats import rankdata, spearmanr
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import roc_auc_score, average_precision_score
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from sparkcut_django.inference import SparkRNN, SparkCutScorer


ROOT = Path(__file__).resolve().parent
SOURCE = "Oxylabs/YouTube_Videos_with_Training_Rights"
BASE_DIR = ROOT
OUT_DIR = ROOT / "sparkcut_viral_v4"
SEED = 417
MAX_ROWS = 100_000
MAX_LEN = 160
EPOCHS = 12
BATCH_SIZE = 256
PATIENCE = 2
LR = 0.00012
SEEDS = 1
MIN_WORDS = 12


def number(value, default=0.0):
    try:
        n = float(str(value).replace(",", ""))
        return n if math.isfinite(n) else default
    except (TypeError, ValueError):
        return default


def transcript_windows(row):
    tr = row.get("transcript") or {}
    if not isinstance(tr, dict):
        return []
    language = (tr.get("detectedLanguage") or {}).get("language")
    if language != "en" and tr.get("platformLanguage") != "en":
        return []
    pieces = tr.get("segments") or []
    segments = []
    for p in pieces:
        if not isinstance(p, dict) or not p.get("text"):
            continue
        start, end = number(p.get("start"), -1), number(p.get("end"), -1)
        if start >= 0 and end > start:
            segments.append((start, end, str(p["text"]).strip()))
    if not segments:
        return []
    # Source transcript times are usually milliseconds; duration is seconds.
    duration = number(tr.get("duration"), number(row.get("duration"), 0))
    max_end = max(s[1] for s in segments)
    scale = 0.001 if duration and max_end > duration * 5 else 1.0
    segments = [(a * scale, b * scale, t) for a, b, t in segments]
    windows, i = [], 0
    while i < len(segments):
        st, j = segments[i][0], i
        while j + 1 < len(segments) and segments[j][1] - st < 25 and segments[j + 1][1] - st <= 45:
            j += 1
        en = segments[j][1]
        text = " ".join(x[2] for x in segments[i:j + 1]).strip()
        words = text.split()
        if 10 <= en - st <= 45 and len(words) >= MIN_WORDS:
            windows.append((st, en, text))
        nxt = i + 1
        while nxt < len(segments) and segments[nxt][0] < st + 8:
            nxt += 1
        i = nxt
    if not windows:
        return []
    # One random-position window per source video prevents long videos from
    # dominating and avoids teaching the model a preferred timestamp.
    video_id = str(row.get("id") or row.get("url") or "")
    pick = int(hashlib.sha1(video_id.encode()).hexdigest()[:8], 16) % len(windows)
    return [windows[pick]]


def read_examples():
    print(f"Reading cached {SOURCE} Arrow shards (video files are not downloaded)", flush=True)
    cache_root = Path.home() / ".cache" / "huggingface" / "datasets"
    prepared = cache_root / "Oxylabs___you_tube_videos_with_training_rights" / "default" / "0.0.0"
    candidates = sorted(prepared.glob("*/you_tube_videos_with_training_rights-train-*.arrow"))
    if not candidates:
        raise FileNotFoundError(f"Expected downloaded Arrow shards under {prepared}")
    dataset = concatenate_datasets([Dataset.from_file(str(path)) for path in candidates])
    examples = []
    for index, row in enumerate(dataset):
        if index >= MAX_ROWS:
            break
        rights = row.get("trainingRights") or []
        if "All" not in rights or row.get("isPrivate") or row.get("isUnlisted"):
            continue
        stats = row.get("statistics") or {}
        views = number(stats.get("views"))
        likes = number(stats.get("likes"))
        if views < 100:
            continue
        channel = row.get("channel") or {}
        group = str(channel.get("id") or (row.get("author") or {}).get("id") or row.get("id"))
        subscribers = max(number(channel.get("subscribers")), 1.0)
        windows = transcript_windows(row)
        if not windows:
            continue
        start, end, text = windows[0]
        if len(text) < 40:
            continue
        # Relative reach (views per subscriber) plus like conversion is a
        # platform outcome proxy, not a human judgment of clip quality.
        reach = math.log1p(views / subscribers)
        like_rate = likes / max(views, 1.0)
        examples.append({
            "id": str(row.get("id") or row.get("url") or index),
            "group": group,
            "text": text,
            "start": start,
            "end": end,
            "views": views,
            "reach": reach,
            "like_rate": like_rate,
        })
        if (index + 1) % 20_000 == 0:
            print(f"  scanned {index + 1:,}; usable English windows {len(examples):,}", flush=True)
    if len(examples) < 1000:
        raise RuntimeError(f"Too few usable English windows: {len(examples)}")
    reach_rank = rankdata([x["reach"] for x in examples]) / len(examples)
    likes_rank = rankdata([x["like_rate"] for x in examples]) / len(examples)
    for row, r, l in zip(examples, reach_rank, likes_rank):
        row["target_raw"] = float(0.75 * r + 0.25 * l)
    print(f"Usable windows: {len(examples):,}; unique channels: {len({x['group'] for x in examples}):,}", flush=True)
    return examples


def split_examples(examples):
    indices = np.arange(len(examples))
    groups = np.array([x["group"] for x in examples])
    first = GroupShuffleSplit(n_splits=1, test_size=0.15, random_state=SEED)
    train_val, test = next(first.split(indices, groups=groups))
    second = GroupShuffleSplit(n_splits=1, test_size=0.1765, random_state=SEED + 1)
    tr_rel, va_rel = next(second.split(train_val, groups=groups[train_val]))
    train, val = train_val[tr_rel], train_val[va_rel]
    raw = np.array([x["target_raw"] for x in examples], dtype=np.float32)
    q20, q80 = np.percentile(raw[train], [20, 80])
    scale_low, scale_high = np.percentile(raw[train], [5, 95])
    labels = np.clip((raw - scale_low) / max(scale_high - scale_low, 1e-6), 0, 1)
    peak = (raw >= q80).astype(np.float32)
    return train, val, test, raw, labels.astype(np.float32), peak, float(q20), float(q80)


def encode(examples, tokenizer, indices):
    all_ids = [tokenizer.encode(examples[i]["text"])[:MAX_LEN] or [1] for i in indices]
    lengths = torch.tensor([len(x) for x in all_ids], dtype=torch.long)
    x = torch.zeros((len(all_ids), MAX_LEN), dtype=torch.long)
    for i, seq in enumerate(all_ids):
        x[i, :len(seq)] = torch.tensor(seq, dtype=torch.long)
    return x, lengths


@torch.inference_mode()
def pooled_features(model, x, lengths, device="cpu"):
    model.eval()
    chunks = []
    for start in range(0, len(x), 128):
        xb = x[start:start + 128].to(device)
        lb = lengths[start:start + 128]
        e = model.drop(model.emb(xb))
        packed = nn.utils.rnn.pack_padded_sequence(e, lb.cpu(), batch_first=True, enforce_sorted=False)
        packed_out, _ = model.rnn(packed)
        out, _ = nn.utils.rnn.pad_packed_sequence(packed_out, batch_first=True, total_length=xb.size(1))
        att = model.att(out).squeeze(-1).masked_fill(xb == 0, -1e9)
        pooled = (out * torch.softmax(att, dim=1).unsqueeze(-1)).sum(1)
        chunks.append(pooled.cpu())
    return torch.cat(chunks)


def make_loader(features, labels, peaks, indices, shuffle):
    ds = TensorDataset(features[indices], torch.from_numpy(labels[indices]), torch.from_numpy(peaks[indices]))
    generator = torch.Generator().manual_seed(SEED)
    return DataLoader(ds, batch_size=BATCH_SIZE, shuffle=shuffle,
                      generator=generator if shuffle else None, num_workers=0)


def run_head_epoch(model, loader, optimizer=None, device="cpu"):
    train = optimizer is not None
    model.h_main.train(train)
    total, count = 0.0, 0
    criterion_bce = nn.BCEWithLogitsLoss()
    for features, target, peak in loader:
        features = features.to(device)
        target, peak = target.to(device), peak.to(device)
        if train:
            optimizer.zero_grad(set_to_none=True)
        with torch.set_grad_enabled(train):
            main = model.h_main(features)
            adj = torch.sigmoid(main[:, 0])
            loss = nn.functional.smooth_l1_loss(adj, target) + 0.35 * criterion_bce(main[:, 1], peak)
            if train:
                loss.backward()
                nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
        total += float(loss.item()) * len(features)
        count += len(features)
    return total / max(count, 1)


@torch.inference_mode()
def predict_head(model, features, indices, device="cpu"):
    model.eval()
    return torch.sigmoid(model.h_main(features[indices].to(device))[:, :2]).cpu().numpy()


def metrics(pred, examples, indices, raw, threshold):
    y = raw[indices]
    peak = (y >= threshold).astype(int)
    score = 0.5 * pred[:, 0] + 0.5 * pred[:, 1]
    order = np.argsort(-score, kind="stable")
    k = max(1, int(math.ceil(len(indices) * 0.20)))
    auc = roc_auc_score(peak, score) if len(np.unique(peak)) == 2 else float("nan")
    ap = average_precision_score(peak, score) if peak.sum() else float("nan")
    rho = spearmanr(score, y).statistic if np.ptp(score) and np.ptp(y) else float("nan")
    return {
        "n": int(len(indices)),
        "spearman_vs_engagement_proxy": float(rho),
        "auc_top20_engagement": float(auc),
        "average_precision_top20": float(ap),
        "precision_top20": float(peak[order[:k]].mean()),
        "random_precision_top20": float(peak.mean()),
    }


def main():
    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    torch.set_num_threads(max(1, min(8, torch.get_num_threads())))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    base_config = json.loads((BASE_DIR / "config.json").read_text(encoding="utf-8"))
    tokenizer_path = BASE_DIR / "tokenizer.model"
    tokenizer = spm.SentencePieceProcessor(model_file=str(tokenizer_path))
    examples = read_examples()
    train_idx, val_idx, test_idx, raw, labels, peaks, q20, q80 = split_examples(examples)
    groups = [np.array([x["group"] for x in examples])[ix] for ix in (train_idx, val_idx, test_idx)]
    if set(groups[0]) & set(groups[1]) or set(groups[0]) & set(groups[2]) or set(groups[1]) & set(groups[2]):
        raise RuntimeError("Channel leakage across splits")
    texts = [x["text"] for x in examples]
    x_all, lens_all = encode(examples, tokenizer, np.arange(len(examples)))
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    base_scorer = SparkCutScorer(BASE_DIR)
    test_texts = [texts[i] for i in test_idx]
    base_scores = np.array([p["score"] for p in base_scorer.score_texts(test_texts)])
    base_pred = np.column_stack((base_scores / 100.0, base_scores / 100.0))
    base_metrics = metrics(base_pred, examples, test_idx, raw, q80)
    print("Existing-model test metrics:", json.dumps(base_metrics), flush=True)

    best_models, seed_results = [], []
    best_features = None
    for seed in range(SEEDS):
        torch.manual_seed(SEED + seed)
        cfg = base_config
        model = SparkRNN(cfg["vocab"], cfg["emb"], cfg["hid"], cfg["layers"], cfg["drop"],
                         cfg["n_go"], cfg["n_em"], len(cfg["heads"])).to(device)
        state = torch.load(BASE_DIR / f"model_{seed}.pt", map_location=device, weights_only=True)
        model.load_state_dict(state, strict=True)
        for name, parameter in model.named_parameters():
            parameter.requires_grad_(name.startswith("h_main."))
        features = pooled_features(model, x_all, lens_all, device)
        train_loader = make_loader(features, labels, peaks, train_idx, True)
        val_loader = make_loader(features, labels, peaks, val_idx, False)
        optimizer = torch.optim.AdamW(model.h_main.parameters(), lr=LR, weight_decay=0.01)
        best_val, bad, path = float("inf"), 0, OUT_DIR / f"model_{seed}.pt"
        for epoch in range(EPOCHS):
            train_loss = run_head_epoch(model, train_loader, optimizer, device)
            val_loss = run_head_epoch(model, val_loader, None, device)
            print(f"seed={seed} epoch={epoch + 1} train={train_loss:.4f} val={val_loss:.4f}", flush=True)
            if val_loss < best_val:
                best_val, bad = val_loss, 0
                torch.save(model.state_dict(), path)
            else:
                bad += 1
                if bad >= PATIENCE:
                    break
        model.load_state_dict(torch.load(path, map_location=device, weights_only=True))
        model.eval()
        best_models.append(model)
        best_features = features
        seed_results.append({"seed": seed, "best_val_loss": float(best_val)})

    all_test_pred = np.mean([predict_head(m, best_features, test_idx, device) for m in best_models], axis=0)
    viral_metrics = metrics(all_test_pred, examples, test_idx, raw, q80)
    val_pred = np.mean([predict_head(m, best_features, val_idx, device) for m in best_models], axis=0)
    weights = base_config["score_weights"]
    raw_val_score = weights["adj"] * val_pred[:, 0] + weights["pk"] * val_pred[:, 1] + weights.get("tv", 0.0) * 0
    qs = np.percentile(raw_val_score, np.linspace(0, 100, 101))
    config = dict(base_config)
    config.update({
        "version": 4,
        "n_models": SEEDS,
        "calibration": {"method": "quantile", "x": qs.tolist(),
                        "y": (10 + 90 * np.linspace(0, 1, 101)).tolist()},
        "uses_teacher": False,
        "teacher_model": None,
        "explanations_trained": False,
        "training_source": SOURCE,
        "target_definition": "0.75 * percentile(log1p(views/channel_subscribers)) + 0.25 * percentile(likes/views)",
        "target_is_segment_viral_label": False,
        "production_ready": False,
    })
    (OUT_DIR / "tokenizer.model").write_bytes(tokenizer_path.read_bytes())
    (OUT_DIR / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    results = {
        "source": SOURCE,
        "source_rows": 100_000,
        "usable_windows": len(examples),
        "split_by": "channel id (disjoint train/validation/test)",
        "split_sizes": {"train": len(train_idx), "validation": len(val_idx), "test": len(test_idx)},
        "label": "relative video reach and like conversion; weakly inherited by one random timed transcript window",
        "train_target_q20": q20,
        "train_target_q80": q80,
        "existing_model": base_metrics,
        "fine_tuned_rnn": viral_metrics,
        "models": seed_results,
        "important_limit": "These are video-level engagement proxies inherited by one sampled window, not human labels or measured short-clip retention/virality. The recurrent encoder was kept frozen; the regression/classification head was fine-tuned.",
    }
    (OUT_DIR / "metrics.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2), flush=True)


if __name__ == "__main__":
    main()
