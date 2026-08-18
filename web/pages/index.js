import { useState } from "react";
import Link from "next/link";
import { runEpisode } from "../lib/api";

const PROJECTS = ["crynux", "neptune_cash", "neptune_privacy"];

export default function Ask() {
  const [project, setProject] = useState(PROJECTS[0]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await runEpisode(project, query);
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <form onSubmit={handleSubmit}>
        <label htmlFor="project">Project</label>
        <select id="project" value={project} onChange={(e) => setProject(e.target.value)}>
          {PROJECTS.map((p) => (
            <option key={p} value={p}>{p}</option>
          ))}
        </select>

        <label htmlFor="query">Research query</label>
        <textarea
          id="query"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="e.g. What is Crynux's current node architecture?"
          required
        />

        <button type="submit" disabled={loading}>
          {loading ? "Researching..." : "Run episode"}
        </button>
      </form>

      {error && <div className="error">{error}</div>}

      {result && (
        <>
          <div className="panel">
            <h2>Strategy</h2>
            <div className="strategy">{result.strategy_summary}</div>
            <h2>Answer</h2>
            <p>{result.final_answer}</p>
          </div>

          <div className="panel">
            <h2>Claims extracted ({result.claims.length})</h2>
            {result.claims.length === 0 && <div className="empty">None this episode.</div>}
            {result.claims.map((c, i) => (
              <div className="claim" key={i}>
                {c.text} <span className="confidence">(confidence {c.confidence.toFixed(2)})</span>
              </div>
            ))}
          </div>

          <div className="panel">
            <h2>Lessons recorded ({result.lessons.length})</h2>
            {result.lessons.length === 0 && <div className="empty">None this episode -- nothing notable happened.</div>}
            {result.lessons.map((l, i) => (
              <div className="lesson" key={i}>
                {l.text} <span className="confidence">(confidence {l.confidence.toFixed(2)})</span>
              </div>
            ))}
          </div>

          <p className="subtitle">
            Episode {result.episode_id} &middot;{" "}
            <Link href="/memory">view this project's Memory Trace &rarr;</Link>
          </p>
        </>
      )}
    </div>
  );
}
