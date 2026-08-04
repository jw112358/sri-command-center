import { useEffect, useMemo, useState } from 'react';
import type { Project } from '../types';
import { getProjects, onOperatorSessionChanged } from '../api/client';

function laneClass(lane: Project['lane']): string {
  return lane.toLowerCase().replace(/\s+/g, '-');
}

export function PortfolioStatus() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [error, setError] = useState('');
  const [authVersion, setAuthVersion] = useState(0);

  useEffect(() => onOperatorSessionChanged(
    () => setAuthVersion(current => current + 1),
  ), []);

  useEffect(() => {
    let mounted = true;
    const refresh = () => getProjects()
      .then(items => {
        if (!mounted) return;
        setProjects(items.sort((a, b) => (b.completionPct ?? 0) - (a.completionPct ?? 0)));
        setError('');
      })
      .catch(err => {
        if (!mounted) return;
        setError(err instanceof Error ? err.message : 'Portfolio data is unavailable.');
      });
    refresh();
    const interval = window.setInterval(refresh, 60_000);
    return () => { mounted = false; window.clearInterval(interval); };
  }, [authVersion]);

  const average = useMemo(() => {
    if (!projects.length) return 0;
    return Math.round(projects.reduce((sum, item) => sum + (item.completionPct ?? 0), 0) / projects.length);
  }, [projects]);

  return (
    <section className="portfolio-page">
      <header className="portfolio-head">
        <div>
          <span className="eyebrow">MASTER BUILDER · LIVE PORTFOLIO</span>
          <h1>PROJECT STATUS</h1>
          <p>One concise view of every registered operating system and build.</p>
        </div>
        <div className="portfolio-overall" aria-label={`Average portfolio completion ${average}%`}>
          <strong>{average}%</strong>
          <span>PORTFOLIO AVERAGE</span>
        </div>
      </header>

      {error && <div className="portfolio-error">SIGN IN OR RESTORE THE PORTFOLIO FEED · {error}</div>}
      {!error && projects.length === 0 && <div className="empty">— NO REGISTERED PROJECTS —</div>}

      <div className="portfolio-grid">
        {projects.map(project => {
          const completion = Math.max(0, Math.min(100, project.completionPct ?? 0));
          return (
            <article className="portfolio-card" key={project.id}>
              <div className="portfolio-card-top">
                <span className={`portfolio-lane ${laneClass(project.lane)}`}>{project.lane}</span>
                <strong>{completion}%</strong>
              </div>
              <h2>{project.name}</h2>
              <p>{project.notes || 'No current status description has been filed.'}</p>
              <div className="portfolio-progress" role="progressbar" aria-valuenow={completion} aria-valuemin={0} aria-valuemax={100}>
                <span style={{ width: `${completion}%` }} />
              </div>
              <footer>
                <span>{project.updatedAt ? `UPDATED ${project.updatedAt}` : 'UPDATE PENDING'}</span>
                {project.githubRepo && (
                  <a href={`https://github.com/${project.githubRepo}`} target="_blank" rel="noreferrer">REPOSITORY ↗</a>
                )}
              </footer>
            </article>
          );
        })}
      </div>
    </section>
  );
}
