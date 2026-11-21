"""Inferencia del ensamble SparkCut v6."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .artifacts import ModelArtifactsError, artifacts_dir, load_config, model_files


class _Cache:
    models = None
    tokenizer = None
    config = None
    context = None


_cache = _Cache()


def _build_model_class():
    import torch
    from torch import nn

    class SparkRNN(nn.Module):
        def __init__(self, config):
            super().__init__()
            vocab, emb, hid = int(config["vocab"]), int(config["emb"]), int(config["hid"])
            layers, drop = int(config["layers"]), float(config["drop"])
            self.emb = nn.Embedding(vocab, emb, padding_idx=0)
            self.drop = nn.Dropout(drop)
            self.rnn = nn.GRU(emb, hid, layers, batch_first=True,
                              bidirectional=True, dropout=drop)
            self.att = nn.Linear(hid * 2, 1)
            self.h_go = nn.Linear(hid * 2, int(config["n_go"]))
            self.h_em = nn.Linear(hid * 2, int(config["n_em"]))
            self.h_main = nn.Sequential(
                nn.Linear(hid * 2, 128), nn.ReLU(), nn.Dropout(drop),
                nn.Linear(128, len(config["heads"])),
            )

        def forward(self, input_ids, lengths):
            import torch
            embedded = self.drop(self.emb(input_ids))
            packed = nn.utils.rnn.pack_padded_sequence(
                embedded, lengths.cpu(), batch_first=True, enforce_sorted=False)
            packed_out, _ = self.rnn(packed)
            output, _ = nn.utils.rnn.pad_packed_sequence(
                packed_out, batch_first=True, total_length=input_ids.size(1))
            attention = self.att(output).squeeze(-1).masked_fill(input_ids == 0, -1e9)
            weights = torch.softmax(attention, dim=1).unsqueeze(-1)
            pooled = self.drop((output * weights).sum(1))
            return self.h_go(pooled), self.h_em(pooled), self.h_main(pooled)

    return SparkRNN


def _load():
    if _cache.models is not None:
        return _cache.models, _cache.tokenizer, _cache.config, _cache.context
    try:
        import sentencepiece as spm
        import torch
    except ImportError as exc:
        raise ModelArtifactsError("El modelo real requiere torch y sentencepiece instalados.") from exc

    config = load_config()
    tokenizer = spm.SentencePieceProcessor(model_file=str(artifacts_dir() / "tokenizer.model"))
    model_class = _build_model_class()
    models = []
    for path in model_files(config):
        model = model_class(config)
        try:
            state = torch.load(path, map_location="cpu", weights_only=True)
            model.load_state_dict(state, strict=True)
        except Exception as exc:
            raise ModelArtifactsError(f"No se pudieron cargar los pesos {Path(path).name}.") from exc
        model.eval()
        models.append(model)

    context = None
    context_file = config.get("context_ranker_file")
    if context_file:
        try:
            import joblib
            context = joblib.load(artifacts_dir() / context_file)
        except Exception as exc:
            raise ModelArtifactsError(f"No se pudo cargar el ranker contextual {context_file}.") from exc

    _cache.models, _cache.tokenizer, _cache.config, _cache.context = models, tokenizer, config, context
    return _cache.models, _cache.tokenizer, _cache.config, _cache.context


def _encode(texts, tokenizer, max_len):
    import torch
    sequences = [tokenizer.encode(text, out_type=int)[:max_len] or [1] for text in texts]
    lengths = torch.tensor([len(row) for row in sequences], dtype=torch.long)
    input_ids = torch.zeros((len(sequences), int(lengths.max())), dtype=torch.long)
    for index, sequence in enumerate(sequences):
        input_ids[index, :len(sequence)] = torch.tensor(sequence, dtype=torch.long)
    return input_ids, lengths


def _calibrate(config, raw):
    calibration = config.get("calibration", {})
    if calibration.get("method") == "quantile":
        return float(np.interp(raw, calibration["x"], calibration["y"]))
    return float(np.clip(float(calibration.get("a", 90.0)) * raw
                         + float(calibration.get("b", 10.0)), 10.0, 100.0))


def _predict_base(texts):
    if not texts:
        return []
    import torch
    models, tokenizer, config, _ = _load()
    max_len = int(config.get("max_len", 160))
    outputs = []
    with torch.no_grad():
        for start in range(0, len(texts), 64):
            input_ids, lengths = _encode(texts[start:start + 64], tokenizer, max_len)
            ensemble = []
            for model in models:
                go, emotion, main = model(input_ids, lengths)
                ensemble.append(torch.cat((torch.sigmoid(main), torch.sigmoid(go),
                                           torch.softmax(emotion, dim=1)), dim=1))
            ensemble = torch.stack(ensemble).mean(0).cpu().numpy()
            head_index = {name: index for index, name in enumerate(config["heads"])}
            weights = config.get("score_weights", {})
            raw = sum(float(weights.get(name, 0.0)) * ensemble[:, head_index[name]]
                      for name in ("tv", "adj", "pk") if name in head_index)
            main_size, go_size = len(config["heads"]), int(config["n_go"])
            for row, raw_value in zip(ensemble, raw):
                outputs.append({"score": round(_calibrate(config, float(raw_value)), 1),
                                "main": row[:main_size], "go": row[main_size:main_size + go_size]})
    return outputs


def _percentile(values):
    if len(values) <= 1:
        return np.full(len(values), 0.5, dtype=np.float32)
    order = np.argsort(np.asarray(values), kind="stable")
    ranks = np.zeros(len(values), dtype=np.float32)
    ranks[order] = np.arange(len(values), dtype=np.float32) / (len(values) - 1)
    return ranks


def predict_detailed(texts: list[str], contextual: bool = False) -> list[dict]:
    if not texts:
        return []
    _, _, config, context = _load()
    base = _predict_base(texts)
    head_index = {name: index for index, name in enumerate(config["heads"])}
    scores = [item["score"] for item in base]
    contextual_data = None
    if contextual and context is not None:
        clean = [text.split(" Transcript: ", 1)[1] if " Transcript: " in text else text
                 for text in texts]
        vectorizer = context["vectorizer"]
        matrix = vectorizer.transform(clean)
        tfidf = context["text_ranker"].predict(matrix)
        from sklearn.metrics.pairwise import cosine_similarity
        novelty = [1.0 - float(cosine_similarity(matrix[i], matrix[min(i + 1, len(clean) - 1)])[0, 0])
                   if len(clean) > 1 else 0.0 for i in range(len(clean))]
        rnn_rank, tfidf_rank, novelty_rank = map(_percentile, (scores, tfidf, novelty))
        blend = config.get("context_rank_blend", {"rnn": 0.3, "tfidf": 0.2, "novelty_next": 0.5})
        combined = (float(blend.get("rnn", 0.3)) * rnn_rank
                    + float(blend.get("tfidf", 0.2)) * tfidf_rank
                    + float(blend.get("novelty_next", 0.5)) * novelty_rank)
        contextual_data = combined, tfidf_rank, novelty_rank

    result = []
    for index, item in enumerate(base):
        score = round(float(10 + 90 * contextual_data[0][index]), 1) if contextual_data else item["score"]
        dimensions = {name: round(float(item["main"][head_index[name]]) * 10, 1)
                      for name in config.get("dims", []) if name in head_index}
        top = np.argsort(-item["go"])[:3]
        result.append({
            "score": score,
            "base_score": item["score"],
            "dims": dimensions,
            "top_emotions": [{"name": config.get("go_names", [])[int(pos)],
                              "score": round(float(item["go"][pos]), 3)}
                             for pos in top if int(pos) < len(config.get("go_names", []))],
        })
        if contextual_data:
            result[-1]["tfidf_rank"] = round(float(contextual_data[1][index]) * 100, 1)
            result[-1]["novelty_rank"] = round(float(contextual_data[2][index]) * 100, 1)
    return result


def predict(texts: list[str]) -> list[float]:
    return [item["score"] for item in predict_detailed(texts)]


def predict_contextual(texts: list[str]) -> list[dict]:
    return predict_detailed(texts, contextual=True)
