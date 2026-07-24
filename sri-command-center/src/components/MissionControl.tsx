import { useCallback, useEffect, useState } from 'react';
import type { Lane, OSPlugin, Priority, Project } from '../types';
import {
  createProject,
  deleteProject,
  getOSPlugins,
  getProjects,
  patchProject,
} from '../api/client';
const LANES: Lane[] = ['PLANNING', 'IN PROGRESS', 'BLOCKED', 'COMPLETE'];

interface ProjectDraft {
  name: string;
  os: string;
  owner: string;
  priority: Priority;
}

const EMPTY_DRAFT: ProjectDraft = {
  name: '',
  os: 'builder',
  owner: 'Jeffery Williams',
  priority: 'MED',
};

function projectSaveMessage(reason: unknown): string {
  const message = reason instanceof Error ? reason.message : '';
  if (/authentication is not configured|missing operator authorization|session expired/i.test(message)) {
    return 'Jeff sign-in is required before dashboard changes can be saved.';
  }
  if (/storage|drive|persistence|not configured/i.test(message)) {
    return 'Drive storage must be connected before dashboard changes can be saved.';
  }
  return 'This project could not be saved. No dashboard data was changed.';
}

function ProjectDialog({
  project,
  osPlugins,
  busy,
  error,
  onClose,
  onSave,
  onDelete,
}: {
  project: Project | null;
  osPlugins: OSPlugin[];
  busy: boolean;
  error: string;
  onClose: () => void;
  onSave: (draft: ProjectDraft) => void;
  onDelete: (() => void) | null;
}) {
  const [draft, setDraft] = useState<ProjectDraft>(() => project ? {
    name: project.name,
    os: project.os,
    owner: project.owner,
    priority: project.priority,
  } : EMPTY_DRAFT);

  return (
    <div className="modal-backdrop" onMouseDown={onClose}>
      <form
        className="modal-box mc-project-dialog"
        onMouseDown={event => event.stopPropagation()}
        onSubmit={event => {
          event.preventDefault();
          if (draft.name.trim() && draft.owner.trim()) onSave(draft);
        }}
      >
        <div className="modal-h">
          {project ? 'EDIT PROJECT' : 'ADD PROJECT'}
          <button className="btn sm" type="button" onClick={onClose}>✕</button>
        </div>
        <label>
          PROJECT NAME
          <input
            autoFocus
            value={draft.name}
            onChange={event => setDraft(current => ({ ...current, name: event.target.value }))}
            placeholder="Project or build name"
            maxLength={200}
          />
        </label>
        <label>
          OPERATING SYSTEM
          <select
            value={draft.os}
            onChange={event => setDraft(current => ({ ...current, os: event.target.value }))}
          >
            {osPlugins.map(os => <option value={os.id} key={os.id}>{os.name}</option>)}
          </select>
        </label>
        <label>
          OWNER
          <input
            value={draft.owner}
            onChange={event => setDraft(current => ({ ...current, owner: event.target.value }))}
            placeholder="Owner"
            maxLength={120}
          />
        </label>
        <label>
          PRIORITY
          <select
            value={draft.priority}
            onChange={event => setDraft(current => ({ ...current, priority: event.target.value as Priority }))}
          >
            <option value="HIGH">HIGH</option>
            <option value="MED">MED</option>
            <option value="LOW">LOW</option>
          </select>
        </label>
        {error && <p className="mc-dialog-error">{error}</p>}
        <div className="mc-dialog-actions">
          {onDelete && (
            <button className="btn danger" type="button" disabled={busy} onClick={onDelete}>
              DELETE
            </button>
          )}
          <span />
          <button className="btn" type="button" onClick={onClose}>CANCEL</button>
          <button className="btn solid" type="submit" disabled={busy || !draft.name.trim()}>
            {busy ? 'SAVING…' : 'SAVE'}
          </button>
        </div>
      </form>
    </div>
  );
}

export function MissionControl() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [drag, setDrag] = useState<string | null>(null);
  const [over, setOver] = useState<string | null>(null);
  const [osPlugins, setOsPlugins] = useState<OSPlugin[]>([]);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<Project | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [syncState, setSyncState] = useState<'loaded' | 'synced' | 'saving' | 'error'>('loaded');

  const osNames = Object.fromEntries(osPlugins.map(os => [os.id, os.name]));

  const refresh = useCallback(() => {
    Promise.allSettled([getProjects(), getOSPlugins()]).then(([projectResult, osResult]) => {
      if (projectResult.status === 'fulfilled') {
        setProjects(projectResult.value.map(project => ({
          ...project,
          updated: project.updated ?? (
            project.updatedAt
              ? new Date(project.updatedAt).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
              : '—'
          ),
        })));
        setSyncState('loaded');
      } else {
        setProjects([]);
        setSyncState('error');
      }
      if (osResult.status === 'fulfilled') setOsPlugins(osResult.value);
    });
  }, []);

  useEffect(() => {
    refresh();
    const interval = window.setInterval(refresh, 15_000);
    return () => window.clearInterval(interval);
  }, [refresh]);

  const move = (projectId: string, lane: Lane) => {
    const original = projects.find(project => project.id === projectId);
    if (!original || original.lane === lane) return;
    setSyncState('saving');
    setProjects(current => current.map(project => (
      project.id === projectId ? { ...project, lane, updated: 'just now' } : project
    )));
    patchProject(projectId, { lane }).then(updated => {
      setProjects(current => current.map(project => (
        project.id === projectId ? { ...project, ...updated, updated: 'just now' } : project
      )));
      setSyncState('synced');
    }).catch(() => {
      setProjects(current => current.map(project => (
        project.id === projectId ? { ...project, lane: original.lane, updated: original.updated } : project
      )));
      setSyncState('error');
    });
  };

  const openNew = () => {
    setEditing(null);
    setError('');
    setDialogOpen(true);
  };

  const openEdit = (project: Project) => {
    setEditing(project);
    setError('');
    setDialogOpen(true);
  };

  const save = (draft: ProjectDraft) => {
    setBusy(true);
    setError('');
    setSyncState('saving');
    const operation = editing
      ? patchProject(editing.id, draft)
      : createProject(draft);
    operation.then(saved => {
      setProjects(current => {
        const exists = current.some(project => project.id === saved.id);
        return exists
          ? current.map(project => project.id === saved.id ? { ...project, ...saved, updated: 'just now' } : project)
          : [{ ...saved, updated: 'just now' }, ...current];
      });
      setBusy(false);
      setDialogOpen(false);
      setSyncState('synced');
    }).catch(reason => {
      setBusy(false);
      setError(projectSaveMessage(reason));
      setSyncState('error');
    });
  };

  const remove = () => {
    if (!editing?.id.startsWith('p:')) return;
    setBusy(true);
    setError('');
    deleteProject(editing.id).then(() => {
      setProjects(current => current.filter(project => project.id !== editing.id));
      setBusy(false);
      setDialogOpen(false);
      setSyncState('synced');
    }).catch(reason => {
      setBusy(false);
      setError(projectSaveMessage(reason));
      setSyncState('error');
    });
  };

  return (
    <div className="mc">
      <div className="mc-head">
        <span className="mc-title">MISSION CONTROL</span>
        <span className="badge ACTIVE">
          <span className="bd"></span>
          {projects.filter(project => project.lane === 'IN PROGRESS').length} IN FLIGHT
        </span>
        <span className="badge BLOCKED">
          <span className="bd"></span>
          {projects.filter(project => project.lane === 'BLOCKED').length} BLOCKED
        </span>
        <span className={'mc-sync-state ' + syncState}>
          {syncState === 'saving'
            ? 'SAVING…'
            : syncState === 'error'
              ? 'READ ONLY · SIGN IN / STORAGE REQUIRED'
              : syncState === 'synced'
                ? 'DRIVE SYNCED'
                : 'LIVE PROJECT INDEX'}
        </span>
        <button className="btn solid" style={{ marginLeft: 'auto' }} onClick={openNew}>
          + ADD PROJECT
        </button>
      </div>

      <div className="mc-board">
        {LANES.map(lane => {
          const cards = projects.filter(project => project.lane === lane);
          return (
            <section
              className={'panel mc-lane ' + lane.replace(/\s/g, '') + (over === lane ? ' drop-target' : '')}
              key={lane}
              onDragOver={event => {
                event.preventDefault();
                if (over !== lane) setOver(lane);
              }}
              onDragLeave={event => {
                if (event.currentTarget === event.target) setOver(null);
              }}
              onDrop={() => {
                if (drag) move(drag, lane as Lane);
                setOver(null);
                setDrag(null);
              }}
            >
              <div className="mc-lane-h">
                <span className="lt">{lane}</span>
                <span className="lc">{cards.length}</span>
              </div>
              <div className="mc-cards">
                {cards.map(project => {
                  const osName = osNames[project.os] ?? project.os;
                  const initials = project.owner
                    .replace(/[^A-Za-z. ]/g, '')
                    .split(/[.\s]+/)
                    .filter(Boolean)
                    .map(value => value[0])
                    .join('')
                    .slice(0, 2)
                    .toUpperCase() || '—';
                  const ciClass =
                    project.ciStatus === 'failure' ? 'err'
                      : project.ciStatus === 'success' ? 'dim'
                        : '';

                  return (
                    <article
                      className={'mc-card' + (drag === project.id ? ' dragging' : '')}
                      key={project.id}
                      draggable
                      onDragStart={() => setDrag(project.id)}
                      onDragEnd={() => {
                        setDrag(null);
                        setOver(null);
                      }}
                    >
                      <div className="ctop">
                        <span className="cname">{project.name}</span>
                        <span className={'prio ' + project.priority}>{project.priority}</span>
                      </div>
                      <div className="cmeta">
                        <span className="cos">{osName.replace(/ \(.*\)/, '')}</span>
                        {project.githubPrCount != null && project.githubPrCount > 0 && (
                          <span className={'cpr ' + ciClass} title={`${project.githubPrCount} open PRs · CI: ${project.ciStatus ?? 'unknown'}`}>
                            ⎇ {project.githubPrCount}
                          </span>
                        )}
                        <button
                          className="btn sm mc-edit"
                          type="button"
                          onMouseDown={event => event.stopPropagation()}
                          onClick={() => openEdit(project)}
                        >
                          EDIT
                        </button>
                      </div>
                      <div className="cfoot">
                        <span className="cowner"><span className="av">{initials}</span>{project.owner}</span>
                        <span className="cupd">{project.updated}</span>
                      </div>
                    </article>
                  );
                })}
                {cards.length === 0 && (
                  <div className="empty" style={{ padding: 16 }}>— EMPTY —</div>
                )}
              </div>
            </section>
          );
        })}
      </div>

      {dialogOpen && (
        <ProjectDialog
          project={editing}
          osPlugins={osPlugins}
          busy={busy}
          error={error}
          onClose={() => {
            if (!busy) setDialogOpen(false);
          }}
          onSave={save}
          onDelete={editing?.id.startsWith('p:') ? remove : null}
        />
      )}
    </div>
  );
}
