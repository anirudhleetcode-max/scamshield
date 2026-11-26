"""DistilBERT vs TF-IDF: same splits, same threshold rules, plus deployment costs.

    cd backend && python -m ml.transformer --tfidf-run ../experiments/results/combined-analysis-<ts>

What it does (Track C data: synthetic + UCI train / val, three test sets):
  1. fine-tunes distilbert-base-uncased (full fine-tune, AdamW, linear warm-up/decay) on TRAIN;
     the epoch kept is the one with the best VAL PR-AUC;
  2. temperature scaling on VAL logits (one parameter, keeps the ranking, fixes over-confidence);
  3. decision threshold = max F1 on VAL; TEST scored once;
  4. deployment costs on CPU: single-message latency (1 thread, p50/p95), artifact size,
     peak RSS of a fresh process that loads the model and scores one message; for
     DistilBERT fp32, DistilBERT int8 (dynamic quantisation) and the shipped TF-IDF model;
  5. explanation cost: leave-one-word-out occlusion for DistilBERT vs the exact linear
     contributions the TF-IDF model already returns;
  6. figures overlaying DistilBERT on the TF-IDF analysis run (if --tfidf-run is given).

Fine-tuned weights go to backend/models/distilbert-scamshield/ (git-ignored, ~255 MB).
Requires requirements-ml.txt (torch, transformers). CPU only is fine: ~30-60 min on 4 cores.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch
from torch import nn

from . import plots
from .analysis import MAIN, SLOTS
from .evaluate import binary_metrics, choose_threshold, min_cost_threshold, risk_coverage, selective_band
from .experiment import REPO_ROOT, env_info, select

BACKEND = Path(__file__).resolve().parents[1]
BASE_MODEL = "distilbert-base-uncased"
OUT_MODEL = BACKEND / "models" / "distilbert-scamshield"
HP = {"max_length": 128, "batch_size": 32, "epochs": 3, "lr": 5e-5, "weight_decay": 0.01, "warmup_ratio": 0.06,
      "seed": 42}


def _y(rows):
    return np.array([r["label_binary"] for r in rows])


def seed_all(seed: int):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def batches(enc, idx, bs, tok):
    for i in range(0, len(idx), bs):
        chunk = idx[i:i + bs]
        yield tok.pad({"input_ids": [enc["input_ids"][j] for j in chunk],
                       "attention_mask": [enc["attention_mask"][j] for j in chunk]}, return_tensors="pt")


@torch.inference_mode()
def logits_of(model, tok, texts: list[str], max_length: int, bs: int = 64) -> np.ndarray:
    model.eval()
    enc = tok(texts, truncation=True, max_length=max_length)
    order = np.argsort([len(x) for x in enc["input_ids"]])  # length-sorted batches = less padding
    out = np.zeros(len(texts), dtype=np.float32)
    for i, b in zip(range(0, len(order), bs), batches(enc, order, bs, tok)):
        lg = model(**b).logits
        out[order[i:i + bs]] = (lg[:, 1] - lg[:, 0]).float().numpy()  # binary logit
    return out


def sigmoid(x):
    return 1 / (1 + np.exp(-x))


def fit_temperature(logits: np.ndarray, y: np.ndarray) -> float:
    """One scalar T minimising validation NLL of sigmoid(logit / T)."""
    lg = torch.tensor(logits, dtype=torch.float64)
    yt = torch.tensor(y, dtype=torch.float64)
    log_t = torch.zeros(1, dtype=torch.float64, requires_grad=True)
    opt = torch.optim.LBFGS([log_t], lr=0.1, max_iter=200)

    def closure():
        opt.zero_grad()
        loss = nn.functional.binary_cross_entropy_with_logits(lg / log_t.exp(), yt)
        loss.backward()
        return loss

    opt.step(closure)
    return float(log_t.exp())


def train(train_rows, val_rows, log=print) -> tuple:
    from transformers import AutoModelForSequenceClassification, AutoTokenizer, get_linear_schedule_with_warmup

    seed_all(HP["seed"])
    tok = AutoTokenizer.from_pretrained(BASE_MODEL)
    model = AutoModelForSequenceClassification.from_pretrained(BASE_MODEL, num_labels=2)
    texts = [r["text"] for r in train_rows]
    y = torch.tensor(_y(train_rows))
    enc = tok(texts, truncation=True, max_length=HP["max_length"])
    lens = np.array([len(x) for x in enc["input_ids"]])
    log(f"  token length: p50={int(np.median(lens))} p95={int(np.percentile(lens, 95))} "
        f"max={lens.max()} truncated={int((lens >= HP['max_length']).sum())}")
    steps_per_epoch = math.ceil(len(texts) / HP["batch_size"])
    total = steps_per_epoch * HP["epochs"]
    no_decay = ("bias", "LayerNorm.weight")
    groups = [{"params": [p for n, p in model.named_parameters() if not any(k in n for k in no_decay)],
               "weight_decay": HP["weight_decay"]},
              {"params": [p for n, p in model.named_parameters() if any(k in n for k in no_decay)],
               "weight_decay": 0.0}]
    opt = torch.optim.AdamW(groups, lr=HP["lr"])
    sched = get_linear_schedule_with_warmup(opt, int(HP["warmup_ratio"] * total), total)
    yva = _y(val_rows)
    best = {"pr_auc": -1}
    history = []
    t0 = time.time()
    rng = np.random.default_rng(HP["seed"])
    for epoch in range(HP["epochs"]):
        model.train()
        # bucket by length (shuffle within chunks of 50 batches) for speed, then shuffle batch order
        perm = rng.permutation(len(texts))
        chunks = [perm[i:i + 50 * HP["batch_size"]] for i in range(0, len(perm), 50 * HP["batch_size"])]
        order = np.concatenate([c[np.argsort(lens[c])] for c in chunks])
        bidx = [order[i:i + HP["batch_size"]] for i in range(0, len(order), HP["batch_size"])]
        rng.shuffle(bidx)
        run_loss, e0 = 0.0, time.time()
        for step, b in enumerate(bidx, 1):
            batch = tok.pad({"input_ids": [enc["input_ids"][j] for j in b],
                             "attention_mask": [enc["attention_mask"][j] for j in b]}, return_tensors="pt")
            loss = model(**batch, labels=y[b]).loss
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step(); sched.step(); opt.zero_grad()
            run_loss += loss.item()
            if step % 50 == 0:
                log(f"  epoch {epoch + 1} step {step}/{len(bidx)} loss {run_loss / step:.4f} "
                    f"({(time.time() - e0) / step:.2f}s/step)")
        lv = logits_of(model, tok, [r["text"] for r in val_rows], HP["max_length"])
        m = binary_metrics(yva, sigmoid(lv), 0.5)
        history.append({"epoch": epoch + 1, "train_loss": round(run_loss / len(bidx), 4), "val_pr_auc": m["pr_auc"],
                        "val_f1_at_0.5": m["f1"], "val_ece": m["ece"], "epoch_seconds": round(time.time() - e0, 1)})
        log(f"  epoch {epoch + 1}: {history[-1]}")
        if m["pr_auc"] > best["pr_auc"]:
            best = {"pr_auc": m["pr_auc"], "epoch": epoch + 1}
            OUT_MODEL.mkdir(parents=True, exist_ok=True)
            model.save_pretrained(OUT_MODEL)
            tok.save_pretrained(OUT_MODEL)
    model = AutoModelForSequenceClassification.from_pretrained(OUT_MODEL)
    return model, tok, {"history": history, "best_epoch": best["epoch"], "train_seconds": round(time.time() - t0, 1)}


# ---------------------------------------------------------------- deployment costs
def dir_size_mb(path: Path) -> float:
    return round(sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1e6, 1)


def latency(fn, texts: list[str], warmup: int = 10) -> dict:
    for t in texts[:warmup]:
        fn(t)
    ms = []
    for t in texts:
        s = time.perf_counter()
        fn(t)
        ms.append(1000 * (time.perf_counter() - s))
    ms = np.array(ms)
    return {"n": len(ms), "p50_ms": round(float(np.percentile(ms, 50)), 2),
            "p95_ms": round(float(np.percentile(ms, 95)), 2), "mean_ms": round(float(ms.mean()), 2),
            "throughput_msgs_per_s_1thread": round(float(1000 / ms.mean()), 1)}


PEAK_RSS_SNIPPET = {
    "tfidf": "from app.services.classifier import load_model; m=load_model(); m.predict('{t}')",
    "distilbert_fp32": ("import torch; from transformers import AutoModelForSequenceClassification as M, AutoTokenizer as T; "
                        "torch.set_num_threads(1); tok=T.from_pretrained(r'{p}'); m=M.from_pretrained(r'{p}').eval(); "
                        "torch.inference_mode()(lambda: m(**tok('{t}', return_tensors='pt')))()"),
    "distilbert_int8": ("import torch; from transformers import AutoModelForSequenceClassification as M, AutoTokenizer as T; "
                        "torch.set_num_threads(1); tok=T.from_pretrained(r'{p}'); m=M.from_pretrained(r'{p}').eval(); "
                        "m=torch.ao.quantization.quantize_dynamic(m, {{torch.nn.Linear}}, dtype=torch.qint8); "
                        "torch.inference_mode()(lambda: m(**tok('{t}', return_tensors='pt')))()"),
}


def peak_rss_mb(kind: str) -> float | None:
    """Peak resident memory of a FRESH process that imports, loads and scores one message."""
    # VmHWM (not ru_maxrss: that can carry the parent's high-water mark across fork/exec)
    code = ("import sys; sys.path.insert(0, '.');" + PEAK_RSS_SNIPPET[kind].format(p=OUT_MODEL, t="Your KYC is pending")
            + "; print([l.split()[1] for l in open('/proc/self/status') if l.startswith('VmHWM')][0])")
    r = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True, timeout=300,
                       env={**os.environ, "ENV": "test"})
    try:
        return round(int(r.stdout.strip().splitlines()[-1]) / 1024, 1)  # kB -> MB
    except Exception:
        return None


def occlusion(prob_fn, text: str) -> tuple[list[tuple[str, float]], int]:
    """Leave-one-word-out: drop in P(scam) when each word is removed. Needs n_words + 1 forward passes."""
    words = text.split()
    base = prob_fn(text)
    contrib = [(w, base - prob_fn(" ".join(words[:i] + words[i + 1:]))) for i, w in enumerate(words)]
    return sorted(contrib, key=lambda t: -abs(t[1]))[:6], len(words) + 1


def run(cfg: dict, out_dir: Path, tfidf_run: Path | None, skip_train: bool, log=print) -> dict:
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    import transformers

    torch.set_num_threads(os.cpu_count() or 4)
    train_rows, val = select(cfg["train"]), select(cfg["val"])
    tests = {k: v for k, v in ((n, select(s)) for n, s in cfg["test_sets"].items()) if v}
    yva = _y(val)
    log(f"[distilbert] train={len(train_rows)} val={len(val)} " + " ".join(f"{k}={len(v)}" for k, v in tests.items()))
    res: dict = {"base_model": BASE_MODEL, "hyperparameters": HP}
    if skip_train and OUT_MODEL.exists():
        model, tok = AutoModelForSequenceClassification.from_pretrained(OUT_MODEL), AutoTokenizer.from_pretrained(OUT_MODEL)
        res["training"] = json.loads((OUT_MODEL / "training.json").read_text())
    else:
        model, tok, res["training"] = train(train_rows, val, log)
        (OUT_MODEL / "training.json").write_text(json.dumps(res["training"], indent=1))

    # scores
    t0 = time.time()
    lv = logits_of(model, tok, [r["text"] for r in val], HP["max_length"])
    lt = {k: logits_of(model, tok, [r["text"] for r in rows], HP["max_length"]) for k, rows in tests.items()}
    res["inference_seconds_all_sets_4threads"] = round(time.time() - t0, 1)
    T = fit_temperature(lv, yva)
    res["temperature"] = round(T, 4)
    variants = {"distilbert": (sigmoid(lv), {k: sigmoid(v) for k, v in lt.items()}),
                "distilbert (temp-scaled)": (sigmoid(lv / T), {k: sigmoid(v / T) for k, v in lt.items()})}
    res["models"] = {}
    for name, (pv, pt) in variants.items():
        t = choose_threshold(yva, pv, "max_f1")
        res["models"][name] = {"threshold_max_f1_val": round(t, 4), "val": binary_metrics(yva, pv, t),
                               "test": {k: binary_metrics(_y(tests[k]), s, t) for k, s in pt.items()}}
        log(f"  {name:26s} " + "  ".join(f"{k}: F1={m['f1']:.3f} PR-AUC={m['pr_auc']} ECE={m['ece']}"
                                          for k, m in res["models"][name]["test"].items()))
    pv, pt = variants["distilbert (temp-scaled)"]
    t_f1 = choose_threshold(yva, pv, "max_f1")
    t_cost, _ = min_cost_threshold(yva, pv, 5, 1)
    res["thresholds"] = {"max F1": round(t_f1, 4), "min cost (FN=5, FP=1)": round(t_cost, 4),
                         "test_at_min_cost": {k: binary_metrics(_y(tests[k]), s, t_cost, False) for k, s in pt.items()}}
    band = selective_band(yva, pv, t_f1, 0.98)
    res["abstention"] = {"band_chosen_on_val": band}

    # int8 dynamic quantisation: accuracy check on the two in-domain test sets
    qmodel = torch.ao.quantization.quantize_dynamic(model, {nn.Linear}, dtype=torch.qint8)
    res["int8"] = {}
    for k in ("synthetic_test", "uci_test"):
        if k in tests:
            q = sigmoid(logits_of(qmodel, tok, [r["text"] for r in tests[k]], HP["max_length"]) / T)
            res["int8"][k] = {m: v for m, v in binary_metrics(_y(tests[k]), q, t_f1).items() if m != "reliability"}

    # errors
    out_dir.mkdir(parents=True, exist_ok=True)
    import csv
    for k in ("synthetic_test", "uci_test"):
        rows, p = tests[k], pt[k]
        y = _y(rows)
        fp = [i for i in np.argsort(-p) if y[i] == 0 and p[i] >= t_f1][:25]
        fn = [i for i in np.argsort(p) if y[i] == 1 and p[i] < t_f1][:25]
        with (out_dir / f"errors_{k}.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["error_type", "p_scam", "threshold", "source", "category", "text"])
            for i in fp:
                w.writerow(["false_positive", round(float(p[i]), 4), round(t_f1, 4), rows[i]["source"], rows[i]["category"], rows[i]["text"]])
            for i in fn:
                w.writerow(["false_negative", round(float(p[i]), 4), round(t_f1, 4), rows[i]["source"], rows[i]["category"], rows[i]["text"]])

    # deployment costs
    torch.set_num_threads(1)
    rng = random.Random(0)
    sample = rng.sample([r["text"] for r in tests["uci_test"] + tests["synthetic_test"]], 300)
    from app.services.classifier import load_model
    tfidf = load_model()
    model.eval(); qmodel.eval()

    @torch.inference_mode()
    def bert_prob(m, t):
        lg = m(**tok(t, truncation=True, max_length=HP["max_length"], return_tensors="pt")).logits[0]
        return float(torch.sigmoid((lg[1] - lg[0]) / T))

    feats, binary = tfidf.features, tfidf.binary
    with tempfile.TemporaryDirectory() as td:
        torch.save(qmodel.state_dict(), Path(td) / "q.pt")
        q_size = round((Path(td) / "q.pt").stat().st_size / 1e6, 1)
    res["deployment"] = {
        "hardware": f"{os.cpu_count()} vCPU container, latency measured with 1 thread, batch size 1",
        "tfidf_logreg (probability only)": {"latency": latency(lambda t: binary.predict_proba(feats.transform([t])), sample),
                                            "artifact_mb": round((BACKEND / "models" / "scamshield-2.0.0.joblib").stat().st_size / 1e6, 1),
                                            "peak_rss_mb": peak_rss_mb("tfidf")},
        "tfidf_logreg (full API predict: prob + category + explanation spans)": {"latency": latency(tfidf.predict, sample)},
        "distilbert_fp32": {"latency": latency(lambda t: bert_prob(model, t), sample),
                            "artifact_mb": dir_size_mb(OUT_MODEL), "peak_rss_mb": peak_rss_mb("distilbert_fp32"),
                            "parameters_m": round(sum(p.numel() for p in model.parameters()) / 1e6, 1)},
        "distilbert_int8_dynamic": {"latency": latency(lambda t: bert_prob(qmodel, t), sample),
                                    "artifact_mb": q_size, "peak_rss_mb": peak_rss_mb("distilbert_int8")},
    }
    for k, v in res["deployment"].items():
        log(f"  {k}: {v}")

    # explanation cost (occlusion for BERT; exact linear contributions for TF-IDF)
    ex = ["Dear customer your SBI account will be blocked today. Update KYC at http://sbi-kyc.top immediately",
          "OTP aa gaya hoga, please bhej do jaldi warna order cancel ho jayega",
          "Money received! Rs 45000 from RAHUL (rahul@okaxis) credited to your HDFC account. UPI Ref 412345678901"]
    res["explanations"] = []
    for text in ex:
        s = time.perf_counter(); top, passes = occlusion(lambda t: bert_prob(model, t), text); bt = time.perf_counter() - s
        s = time.perf_counter(); pr = tfidf.predict(text); lt_ = time.perf_counter() - s
        res["explanations"].append({
            "text": text,
            "distilbert": {"p_scam": round(bert_prob(model, text), 4), "occlusion_top_words": [(w, round(c, 4)) for w, c in top],
                           "forward_passes": passes, "ms": round(1000 * bt, 1)},
            "tfidf": {"p_scam": round(pr.scam_probability, 4),
                      "top_spans": [s_.get("text") for s_ in getattr(pr, "spans", [])][:6], "ms": round(1000 * lt_, 1)}})

    # figures (overlay on the TF-IDF analysis run when available)
    fig = out_dir / "figures"
    figs = []
    tf_scores = {}
    if tfidf_run and (tfidf_run / "scores.npz").exists():
        z = np.load(tfidf_run / "scores.npz")
        tf_scores = {k.split("|")[1]: z[k] for k in z.files if k.startswith(MAIN + "|")}
        nb = {k.split("|")[1]: z[k] for k in z.files if k.startswith("nb|")}
    for k, rows in tests.items():
        y = _y(rows)
        s = {"distilbert (temp-scaled)": pt[k]}
        if k in tf_scores and len(tf_scores[k]) != len(y):
            tf_scores.pop(k)
        if k in tf_scores:
            s = {"nb": nb[k], MAIN: tf_scores[k], **s}
        figs.append(plots.roc_pr(y, s, f"{k}: TF-IDF vs DistilBERT", fig / f"roc_pr_{k}.png", SLOTS))
        rel = {"distilbert": variants["distilbert"][1][k], "distilbert (temp-scaled)": pt[k]}
        if k in tf_scores:
            rel[MAIN] = tf_scores[k]
        figs.append(plots.reliability(y, rel, f"Reliability - {k}", fig / f"reliability_{k}.png", slots=SLOTS))
    curves = {"distilbert (temp-scaled)": risk_coverage(_y(tests["uci_test"]), pt["uci_test"], t_f1)}
    if "uci_test" in tf_scores and f"{MAIN}|val" in np.load(tfidf_run / "scores.npz").files:
        from .evaluate import choose_threshold as ct
        z = np.load(tfidf_run / "scores.npz")
        t_lr = ct(yva, z[f"{MAIN}|val"], "max_f1")
        curves = {MAIN: risk_coverage(_y(tests["uci_test"]), tf_scores["uci_test"], t_lr), **curves}
    figs.append(plots.risk_coverage(curves, "Risk-coverage on uci_test", fig / "risk_coverage_uci_test.png", slots=SLOTS))
    res["figures"] = sorted(figs)
    res["tfidf_run"] = str(tfidf_run.relative_to(REPO_ROOT)) if tfidf_run else None

    env = env_info()
    env["libraries"].update({"torch": torch.__version__, "transformers": transformers.__version__})
    (out_dir / "env.json").write_text(json.dumps(env, indent=2) + "\n")
    (out_dir / "metrics.json").write_text(json.dumps(res, indent=1) + "\n")
    (out_dir / "config.json").write_text(json.dumps({**cfg, "transformer": {"base_model": BASE_MODEL, **HP}}, indent=2) + "\n")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(REPO_ROOT / "experiments" / "configs" / "combined.json"))
    ap.add_argument("--tfidf-run", default=None, help="results folder of `python -m ml.analysis` to overlay")
    ap.add_argument("--skip-train", action="store_true", help="reuse models/distilbert-scamshield if present")
    ap.add_argument("--epochs", type=int, default=HP["epochs"])
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    HP["epochs"] = a.epochs
    cfg = json.loads(Path(a.config).read_text())
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = Path(a.out) if a.out else REPO_ROOT / "experiments" / "results" / f"{cfg['name']}-distilbert-{stamp}"
    run(cfg, out, Path(a.tfidf_run).resolve() if a.tfidf_run else None, a.skip_train)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
