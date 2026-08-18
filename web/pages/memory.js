import { useState } from "react";
import { getMemoryTrace } from "../lib/api";

const PROJECTS = ["crynux", "neptune_cash", "neptune_privacy"];

function reliabilityColor(score) {
  if (score >= 0.6) return "var(...good)";
  if (score <= 0.35) return "var(...bad)";
  return "var(--brass)";
}

export default function MemoryTrace() {
  const [project, setProject] = useState(PROJECTS[0]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [trace, setTrace] = useState(null);

  async function load(p) {
    setLoading(true);
    setError(null);
    try {
      const data = await getMemoryTrace(p);
      setTrace(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function domainFor(sourceId) {
    if (!trace) return sourceId;
    const s = trace.sources.find((s) => s.source_id === sourceId);
    return s ? s.domain : sourceId;
  }

  return (
    <div>
      <label htmlFor="project">Project</label>
      <select
        id="project"
        value={project}
        onChange={(e) => setProject(e.target.value)}
      >
        {PROJECTS.map((p) => (
          <option key={p} value={p}>{p}</option>
        ))}
      </select>
      <button onClick={() => load(project)} disabled={loading}>
        {loading ? "Loading..." : "Load Memory Trace"}
      </button>

      {error && <div className="error">{error}</div>}

      {trace && (
        <>
          <div className="panel">
            <h2>Source reliability</h2>
            {trace.sources.length === 0 && <div className="empty">No sources recorded for this project yet.</div>}
            {trace.sources.length > 0 && (
              <table>
                <thead>
                  <tr><th>Domain</th><th>Reliability</th><th>Used</th><th>Successful</th><th>Problematic</th></tr>
                </thead>
                <tbody>
                  {trace.sources.map((s) => (
                    <tr key={s.source_id}>
                      <td>{s.domain}</td>
                      <td>
                        <span className="reliability-bar">
                          <span
                            className="reliability-fill"
                            style={{
                              width: `${Math.round(s.reliability_score * 100)}%`,
                              background: reliabilityColor(s.reliability_score),
                            }}
                          />
                        </span>{" "}
                        {(s.reliability_score * 100).toFixed(0)}%
                      </td>
                      <td>{s.times_used}</td>
                      <td>{s.successful_uses}</td>
                      <td>{s.problematic_uses}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div className="panel">
            <h2>Contradictions detected ({trace.contradictions.length})</h2>
            {trace.contradictions.length === 0 && (
              <div className="empty">None yet, this shows up once a later episode's claim supersedes an earlier one.</div>
            )}
            {trace.contradictions.map((c, i) => (
              <div className="contradiction" key={i}>
                <div className="old-claim">Old: {c.old_claim_text}</div>
                <div className="new-claim">New: {c.new_claim_text}</div>
                <div className="confidence">{c.resolution_note}</div>
              </div>
            ))}
          </div>

          <div className="panel">
            <h2>Lessons ({trace.lessons.length})</h2>
            {trace.lessons.length === 0 && <div className="empty">None yet.</div>}
            {trace.lessons.map((l) => (
              <div className="lesson" key={l.lesson_id}>
                <strong>{domainFor(l.source_id)}:</strong> {l.text}{" "}
                <span className="confidence">(confidence {l.confidence.toFixed(2)})</span>
              </div>
            ))}
          </div>

          <div className="panel">
            <h2>Recent episodes ({trace.episodes.length})</h2>
            {trace.episodes.length === 0 && <div className="empty">None yet.</div>}
            {trace.episodes.map((e) => (
              <div className="claim" key={e.episode_id}>
                <strong>{e.status}</strong> &middot; {e.query}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
