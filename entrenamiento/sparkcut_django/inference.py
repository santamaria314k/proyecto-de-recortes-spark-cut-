"""Inference for the exported SparkCut v3 BiGRU ensemble."""

from __future__ import annotations

import json
import os
from pathlib import Path
from threading import Lock
from typing import Any

import numpy as np
import sentencepiece as spm
import torch
from scipy.stats import rankdata
from torch import nn


class SparkRNN(nn.Module):
    """Architecture must stay compatible with the exported state dictionaries."""

    def __init__(self, vocab: int, emb: int, hid: int, layers: int, drop: float,
                 n_go: int, n_em: int, n_heads: int):
        super().__init__()
        self.emb = nn.Embedding(vocab, emb, padding_idx=0)
        self.drop = nn.Dropout(drop)
        self.rnn = nn.GRU(emb, hid, layers, batch_first=True,
                          bidirectional=True, dropout=drop)
        self.att = nn.Linear(hid * 2, 1)
        self.h_go = nn.Linear(hid * 2, n_go)
        self.h_em = nn.Linear(hid * 2, n_em)
        self.h_main = nn.Sequential(
            nn.Linear(hid * 2, 128), nn.ReLU(), nn.Dropout(drop),
            nn.Linear(128, n_heads),
        )

    def forward(self, x: torch.Tensor, lens: torch.Tensor):
        e = self.drop(self.emb(x))
        packed = nn.utils.rnn.pack_padded_sequence(
            e, lens.cpu(), batch_first=True, enforce_sorted=False
        )
        packed_out, _ = self.rnn(packed)
        out, _ = nn.utils.rnn.pad_packed_sequence(
            packed_out, batch_first=True, total_length=x.size(1)
        )
        weights = self.att(out).squeeze(-1).masked_fill(x == 0, -1e9)
        weights = torch.softmax(weights, dim=1).unsqueeze(-1)
        pooled = self.drop((out * weights).sum(1))
        return self.h_go(pooled), self.h_em(pooled), self.h_main(pooled)


class SparkCutScorer:
    def __init__(self, model_dir: str | Path | None = None):
        default_dir = Path(__file__).resolve().parent.parent
        self.model_dir = Path(model_dir or os.environ.get("SPARKCUT_MODEL_DIR", default_dir)).resolve()
        with (self.model_dir / "config.json").open(encoding="utf-8") as f:
            self.config = json.load(f)
        self.device = torch.device(
            "cuda" if torch.cuda.is_available() and os.environ.get("SPARKCUT_DEVICE", "auto") != "cpu" else "cpu"
        )
        self.tokenizer = spm.SentencePieceProcessor(
            model_file=str(self.model_dir / "tokenizer.model")
        )
        cfg = self.config
        self.models = []
        for i in range(int(cfg["n_models"])):
            model = SparkRNN(
                int(cfg["vocab"]), int(cfg["emb"]), int(cfg["hid"]),
                int(cfg["layers"]), float(cfg["drop"]), int(cfg["n_go"]),
                int(cfg["n_em"]), len(cfg["heads"]),
            ).to(self.device)
            state = torch.load(
                self.model_dir / f"model_{i}.pt", map_location=self.device,
                weights_only=True,
            )
            model.load_state_dict(state, strict=True)
            model.eval()
            self.models.append(model)
        self.position_ranker = None
        if cfg.get("rank_blend", {}).get("position", 0) > 0:
            import joblib
            self.position_ranker = joblib.load(self.model_dir / "position_ranker.joblib")
        self.context_ranker = None
        context_file = cfg.get("context_ranker_file")
        if context_file:
            import joblib
            self.context_ranker = joblib.load(self.model_dir / context_file)
        self._validate_artifacts()

    def _validate_artifacts(self) -> None:
        expected = int(self.config["vocab"])
        actual = int(self.tokenizer.get_piece_size())
        if actual != expected:
            raise RuntimeError(f"Tokenizer vocab mismatch: config={expected}, tokenizer={actual}")
        for name in ("n_models", "heads", "dims", "score_weights", "calibration"):
            if name not in self.config:
                raise RuntimeError(f"Missing {name!r} in SparkCut config")

    def _encode(self, texts: list[str]) -> tuple[torch.Tensor, torch.Tensor]:
        max_len = int(self.config["max_len"])
        sequences = [self.tokenizer.encode(text)[:max_len] or [1] for text in texts]
        lengths = torch.tensor([len(seq) for seq in sequences], dtype=torch.long)
        x = torch.zeros((len(sequences), int(lengths.max())), dtype=torch.long)
        for i, seq in enumerate(sequences):
            x[i, :len(seq)] = torch.tensor(seq, dtype=torch.long)
        return x.to(self.device), lengths

    @torch.inference_mode()
    def score_texts(self, texts: list[str], batch_size: int = 64) -> list[dict[str, Any]]:
        """Score transcript excerpts. The numeric score is a ranking heuristic, not a probability."""
        if not texts:
            return []
        cfg = self.config
        calibration = cfg["calibration"]
        weights = cfg["score_weights"]
        outputs = []
        for start in range(0, len(texts), batch_size):
            batch = texts[start:start + batch_size]
            x, lengths = self._encode(batch)
            ensemble = []
            for model in self.models:
                go, emotion, main = model(x, lengths)
                ensemble.append(torch.cat((torch.sigmoid(main), torch.sigmoid(go),
                                           torch.softmax(emotion, dim=1)), dim=1))
            pred = torch.stack(ensemble).mean(0).cpu().numpy()
            n_heads = len(cfg["heads"])
            n_go = int(cfg["n_go"])
            head_index = {name: i for i, name in enumerate(cfg["heads"])}
            raw = sum(float(weights.get(name, 0.0)) * pred[:, head_index[name]]
                      for name in ("tv", "adj", "pk") if name in head_index)
            if calibration["method"] == "linear":
                score = np.clip(float(calibration["a"]) * raw + float(calibration["b"]), 10, 100)
            elif calibration["method"] == "quantile":
                score = np.interp(raw, calibration["x"], calibration["y"])
            else:
                raise RuntimeError(f"Unknown calibration method: {calibration['method']}")
            for j, value in enumerate(score):
                result = {"score": round(float(value), 1)}
                if cfg.get("explanations_trained", True):
                    go_scores = pred[j, n_heads:n_heads + n_go]
                    top = np.argsort(-go_scores)[:3]
                    result["dimensions"] = {
                        name: round(float(pred[j, head_index[name]]) * 10, 1)
                        for name in cfg["dims"] if name in head_index
                    }
                    result["top_emotions"] = [
                        {"name": cfg["go_names"][int(k)], "score": round(float(go_scores[k]), 3)}
                        for k in top
                    ]
                outputs.append(result)
        return outputs

    def score_positions(self, windows: list[dict[str, float]]) -> list[float]:
        """Return the learned position component for within-video ranking."""
        if self.position_ranker is None or not windows:
            return [0.0] * len(windows)
        length = max(float(row["end"]) for row in windows)
        features = np.asarray([
            [float(row["start"]) / max(length, 1.0),
             (float(row["end"]) - float(row["start"])) / max(length, 1.0),
             float(float(row["start"]) / max(length, 1.0) < 0.05),
             np.log(max(length, 1.0)) / 10.0]
            for row in windows
        ], dtype=np.float32)
        return self.position_ranker.predict(features).astype(float).tolist()

    def score_contextual_ranks(self, texts: list[str], rnn_scores: list[float]) -> dict[str, list[float]]:
        """Combine transcript relevance with within-video textual novelty ranks."""
        if self.context_ranker is None or not texts:
            return {"combined": [], "tfidf": [], "novelty_next": []}
        vectorizer = self.context_ranker["vectorizer"]
        text_ranker = self.context_ranker["text_ranker"]
        clean_texts = [text.split(" Transcript: ", 1)[1] if " Transcript: " in text else text
                       for text in texts]
        matrix = vectorizer.transform(clean_texts)
        tfidf_scores = text_ranker.predict(matrix).astype(float).tolist()

        novelty = np.zeros((len(texts), 4), dtype=np.float32)
        from sklearn.metrics.pairwise import cosine_similarity
        for offset in range(len(texts)):
            neighbors = [j for j in (offset - 1, offset + 1, offset - 2, offset + 2)
                         if 0 <= j < len(texts)]
            if not neighbors:
                continue
            similarities = cosine_similarity(matrix[offset], matrix[neighbors]).ravel()
            for k, similarity in enumerate(similarities[:4]):
                novelty[offset, k] = 1.0 - float(similarity)

        def percentile(values):
            if len(values) <= 1:
                return np.full(len(values), 0.5, dtype=np.float32)
            return ((rankdata(np.asarray(values), method="average") - 1)
                    / (len(values) - 1)).astype(np.float32)

        cfg = self.config["context_rank_blend"]
        rnn_rank = percentile(rnn_scores)
        tfidf_rank = percentile(tfidf_scores)
        novelty_rank = percentile(novelty[:, 1])
        combined = (float(cfg["rnn"]) * rnn_rank
                    + float(cfg["tfidf"]) * tfidf_rank
                    + float(cfg["novelty_next"]) * novelty_rank)
        return {
            "combined": combined.astype(float).tolist(),
            "tfidf": tfidf_rank.astype(float).tolist(),
            "novelty_next": novelty_rank.astype(float).tolist(),
        }


_instance: SparkCutScorer | None = None
_instance_lock = Lock()


def get_scorer() -> SparkCutScorer:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = SparkCutScorer()
    return _instance
