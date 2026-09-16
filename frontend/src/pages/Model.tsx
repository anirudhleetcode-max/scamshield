import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { ModelInfo } from "../lib/types";
import { SkeletonBlock } from "../components/Skeleton";
import { KindTag } from "../components/KindTag";

const f3 = (x: number | null | undefined) => (x === null || x === undefined ? "–" : x.toFixed(3));
const BASELINE_LABEL: Record<string, string> = {
  majority: "Majority class",
  rules_only: "Rules only",
  nb: "TF-IDF + Naive Bayes",
  logreg_noweight: "LogReg (no class weight)",
  logreg_uncal: "LogReg (balanced, uncalibrated)",
  logreg_cal: "LogReg (balanced, calibrated) — shipped",
  linsvc_cal: "LinearSVC + calibration",
};

function testKind(note: string | undefined) {
  return note?.startsWith("SYNTHETIC") ? "synthetic" : "real";
}

export default function Model() {
  const [info, setInfo] = useState<ModelInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<ModelInfo>("/api/model").then(setInfo).catch((e) => setError(e.message));
  }, []);

  if (error) return <p className="error" role="alert">{error}</p>;
  if (!info) return <><div className="page-head"><h1>Model</h1></div><SkeletonBlock height={300} /></>;
  if (!info.card) {
    return (
      <>
        <div className="page-head"><h1>Model</h1></div>
        <div className="panel empty">
          <strong>No model card found</strong>
          Train a model with <span className="mono">python -m ml.train</span>. {info.error && <div className="mono small">{info.error}</div>}
        </div>
      </>
    );
  }
  const c = info.card;
  const ops = c.operating_points;
  const testSets = Object.keys(c.metrics.main_model_test);
  const baselineSets = testSets.filter((k) => k !== "all_scam_spam_short");

  return (
    <>
      <div className="page-head">
        <h1>Model</h1>
        <p>What the checker is, what it was trained on, how well it did and where it fails.</p>
        <span className="right mono small">
          v{c.model_version} · {info.loaded ? "loaded" : <span style={{ color: "var(--scam)" }}>not loaded</span>}
        </span>
      </div>

      {c.training_data.contains_synthetic && (
        <p className="abstain" style={{ border: "1px solid var(--rule)", marginBottom: 24 }} data-testid="synthetic-warning">
          <strong>Part of the training data is synthetic.</strong> The Indian scam examples and all 13 pattern labels
          come from templates written for this project, not from real messages. The only real labelled SMS data
          (UCI SMS Spam, 2011) is English spam from the UK and Singapore. Scores on synthetic test data overstate
          real-world accuracy.
        </p>
      )}

      <div className="card-grid">
        <section className="panel">
          <div className="panel-h"><h2>What it is</h2></div>
          <div className="panel-b" style={{ display: "grid", gap: 12, fontSize: 13 }}>
            <p>{c.intended_use}</p>
            <ol className="plain">{c.pipeline.map((p) => <li key={p}>{p}</li>)}</ol>
            <dl className="kv">
              <dt>Trained</dt><dd>{new Date(c.created_at).toLocaleString("en-IN")}</dd>
              <dt>Run</dt><dd>{c.experiment_run}</dd>
              <dt>Commit</dt><dd>{c.git_commit?.slice(0, 10) ?? "—"}</dd>
              <dt>Libraries</dt><dd>python {c.python} · {Object.entries(c.libraries).map(([k, v]) => `${k} ${v}`).join(" · ")}</dd>
              <dt>Artifact</dt><dd>{c.artifact ? `${c.artifact.file} (${c.artifact.size_kb} KB)` : "—"}</dd>
            </dl>
          </div>
        </section>

        <section className="panel">
          <div className="panel-h"><h2>Data</h2><span className="right small muted">{c.training_data.train_rows} train · {c.training_data.val_rows} val rows</span></div>
          <div className="table-wrap">
            <table className="t" data-testid="datasets">
              <thead><tr><th>Dataset</th><th>Kind</th><th>Used for</th><th className="hide-sm">Licence</th><th className="n">Rows</th></tr></thead>
              <tbody>
                {c.training_data.datasets.map((d) => (
                  <tr key={d.name}>
                    <td>
                      <div className="mono">{d.name}</div>
                      <div className="muted small">{d.description}</div>
                      {d.processed_sha256 && <div className="muted small mono">sha256 {d.processed_sha256.slice(0, 12)}…</div>}
                    </td>
                    <td><KindTag kind={d.kind} /></td>
                    <td className="small">{d.used_for?.join(", ") ?? "—"}</td>
                    <td className="hide-sm small">{d.licence}</td>
                    <td className="n">{d.counts.total.toLocaleString("en-IN")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <section className="panel section">
        <div className="panel-h"><h2>Test results</h2><span className="right small muted">threshold chosen on validation, test scored once</span></div>
        <div className="table-wrap">
          <table className="t" data-testid="test-metrics">
            <thead>
              <tr><th>Test set</th><th className="n">n</th><th className="n">Precision</th><th className="n">Recall</th><th className="n">F1</th>
                <th className="n">PR-AUC</th><th className="n">ECE</th><th className="n hide-sm">System F1</th></tr>
            </thead>
            <tbody>
              {testSets.map((k) => {
                const m = c.metrics.main_model_test[k];
                const sys = c.metrics.full_system_test[k];
                return (
                  <tr key={k}>
                    <td><span className="mono">{k}</span> <KindTag kind={testKind(c.test_set_notes[k])} />
                      <div className="muted small">{c.test_set_notes[k]}</div></td>
                    <td className="n">{m.n}</td>
                    <td className="n">{f3(m.precision)}</td>
                    <td className="n">{f3(m.recall)}</td>
                    <td className="n">{f3(m.f1)}</td>
                    <td className="n">{f3(m.pr_auc)}</td>
                    <td className="n">{f3(m.ece)}</td>
                    <td className="n hide-sm">{f3(sys?.flag_if_suspicious_or_scam.f1)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="note panel-b" style={{ paddingTop: 8 }}>
          System F1 counts a message as flagged when the app says Suspicious or Scam (model + rules, no community reports).
          Pattern head on synthetic test: accuracy {f3(c.metrics.category_head_test.synthetic_test?.accuracy)},
          macro-F1 {f3(c.metrics.category_head_test.synthetic_test?.macro_f1)}.
        </p>
      </section>

      <div className="card-grid section">
        <section className="panel">
          <div className="panel-h"><h2>Baselines (F1 on test)</h2></div>
          <div className="table-wrap">
            <table className="t" data-testid="baselines">
              <thead><tr><th>Model</th>{baselineSets.map((k) => <th key={k} className="n">{k}</th>)}</tr></thead>
              <tbody>
                {Object.entries(c.metrics.baselines_test_at_val_threshold).map(([name, sets]) => (
                  <tr key={name} style={name === "logreg_cal" ? { fontWeight: 600 } : undefined}>
                    <td>{BASELINE_LABEL[name] ?? name}</td>
                    {baselineSets.map((k) => <td key={k} className="n">{f3(sets[k]?.f1)}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="panel">
          <div className="panel-h"><h2>Decision rules</h2></div>
          <div className="panel-b" style={{ fontSize: 13, display: "grid", gap: 10 }}>
            <dl className="kv" data-testid="operating-points">
              <dt>Suspicious</dt><dd>score ≥ {ops.suspicious_score}</dd>
              <dt>Scam</dt><dd>score ≥ {ops.scam_score}</dd>
              <dt>Model threshold</dt><dd>{ops.model_threshold.toFixed(3)}</dd>
              <dt>Uncertain band</dt><dd>{ops.uncertain_band.low.toFixed(3)} – {ops.uncertain_band.high.toFixed(3)}</dd>
            </dl>
            <ul className="plain small">{Object.entries(ops.rules).map(([k, v]) => <li key={k}><b>{k}</b>: {v}</li>)}</ul>
            <p className="small">
              On validation, answering only outside the uncertain band covers {(ops.val_selective.coverage * 100).toFixed(0)}% of
              messages with {ops.val_selective.selective_accuracy !== null ? `${(ops.val_selective.selective_accuracy * 100).toFixed(1)}%` : "–"} accuracy
              {ops.val_selective.target_met === false && <> — <b>below the {ops.val_selective.target_accuracy * 100}% target</b></>}.
              Messages asking for an OTP/PIN, a collect-request PIN or a remote-access app are always at least Suspicious.
            </p>
            <p className="small muted">Calibration (ECE on UCI test): uncalibrated {f3(c.metrics.calibration.logreg_uncal?.uci_test?.ece)} → calibrated {f3(c.metrics.calibration.logreg_cal?.uci_test?.ece)}.</p>
          </div>
        </section>
      </div>

      <section className="panel section">
        <div className="panel-h"><h2>Limitations</h2></div>
        <div className="panel-b">
          <ul className="plain" data-testid="limitations">{c.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
        </div>
      </section>
    </>
  );
}
