import { useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import Icon from '../../components/Icon';
import { Alert, ErrorState, Field, Loading, ProgressBar } from '../../components/ui';
import { CATEGORY_LABELS } from '../../components/WellnessBits';
import { api } from '../../lib/api';
import { useApi } from '../../lib/hooks';

function useElapsed(running) {
  const [elapsed, setElapsed] = useState(0);
  const elapsedRef = useRef(0);
  elapsedRef.current = elapsed;
  useEffect(() => {
    if (!running) return undefined;
    const start = Date.now() - elapsedRef.current * 1000; // resume from where we paused
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - start) / 1000)), 250);
    return () => clearInterval(id);
  }, [running]);
  return elapsed;
}

const fmt = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;

function Breathing({ activity, elapsed, running }) {
  const pattern = activity.config.pattern || [{ phase: 'Breathe in', seconds: 4 }, { phase: 'Breathe out', seconds: 6 }];
  const cycle = pattern.reduce((a, p) => a + p.seconds, 0);
  let t = elapsed % cycle;
  let idx = 0;
  while (t >= pattern[idx].seconds) {
    t -= pattern[idx].seconds;
    idx += 1;
  }
  const phase = pattern[idx];
  const scale = phase.phase.toLowerCase().includes('in') ? 1 : phase.phase.toLowerCase().includes('out') ? 0.6 : null;
  const prevScale = idx > 0 && pattern[idx - 1].phase.toLowerCase().includes('in') ? 1 : 0.6;
  const s = scale ?? prevScale;
  return (
    <div className="breath-stage">
      <div className="breath-circle" style={{ '--s': running ? s : 0.6, transitionDuration: `${phase.seconds}s` }}
        aria-live="polite">
        <div>
          {running ? phase.phase : 'Ready'}
          {running && <div style={{ fontSize: 14, fontWeight: 600 }}>{phase.seconds - t}</div>}
        </div>
      </div>
    </div>
  );
}

function Steps({ activity, current, setCurrent }) {
  return (
    <div className="stack-sm">
    <ol className="steps">
      {activity.instructions.map((step, i) => (
        <li key={i} className={i === current ? 'current' : i < current ? 'done' : ''} aria-current={i === current ? 'step' : undefined}>
          <span className="step-num">{i < current ? <Icon name="check" size={14} /> : i + 1}</span>
          <span style={{ flex: 1 }}>{step}</span>
        </li>
      ))}
    </ol>
      <div className="row">
        <button className="btn btn-ghost btn-sm" disabled={current === 0} onClick={() => setCurrent((c) => Math.max(0, c - 1))}>Previous step</button>
        <button className="btn btn-secondary btn-sm" disabled={current >= activity.instructions.length}
          onClick={() => setCurrent((c) => Math.min(activity.instructions.length, c + 1))}>
          {current >= activity.instructions.length - 1 ? 'Finish steps' : 'Next step'}
        </button>
      </div>
    </div>
  );
}

export default function ActivityPlayer() {
  const { activityId } = useParams();
  const { data: activity, error, loading, reload } = useApi(`/api/activities/${activityId}`);
  const [session, setSession] = useState(null);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState(null);
  const [running, setRunning] = useState(false);
  const [step, setStep] = useState(0);
  const [journal, setJournal] = useState('');
  const [saveJournal, setSaveJournal] = useState(false);
  const [completing, setCompleting] = useState(false);
  const [completeError, setCompleteError] = useState(null);
  const [result, setResult] = useState(null);
  const elapsed = useElapsed(running);

  async function start() {
    setStarting(true);
    setStartError(null);
    try {
      setSession(await api.post(`/api/activities/${activityId}/sessions`));
      setRunning(true);
    } catch (err) {
      setStartError(err);
    } finally {
      setStarting(false);
    }
  }

  async function complete() {
    setCompleting(true);
    setCompleteError(null);
    try {
      const body = activity.kind === 'journal' ? { journal_text: journal, save_to_journal: saveJournal } : {};
      const data = await api.post(`/api/activity-sessions/${session.session_id}/complete`, body);
      setResult(data);
      setRunning(false);
    } catch (err) {
      setCompleteError(err);
    } finally {
      setCompleting(false);
    }
  }

  if (loading) return <Loading />;
  if (error) return <ErrorState error={error} onRetry={reload} />;

  const target = activity.duration_minutes * 60;
  const minSeconds = session?.min_seconds ?? Math.floor(target * 0.6);
  const stepsDone = activity.kind !== 'guided_steps' || step >= activity.instructions.length;
  const journalOk = activity.kind !== 'journal' || journal.trim().length >= 20;
  const timeOk = elapsed >= minSeconds;
  const canComplete = session && timeOk && stepsDone && journalOk && !result;
  const prompts = activity.config.prompts || [];

  return (
    <div style={{ maxWidth: 760, margin: '0 auto' }} className="stack">
      <Link to="/app/activities" className="small row" style={{ gap: 4 }}><Icon name="arrowLeft" size={16} /> All activities</Link>
      <div className="card stack">
        <div>
          <div className="row" style={{ gap: 8 }}>
            <span className="badge">{CATEGORY_LABELS[activity.category]}</span>
            {activity.source === 'ai' && <span className="badge badge-ai">AI-generated · safety-checked</span>}
            <span className="small muted">{activity.duration_minutes} min · {activity.difficulty} · +{activity.xp_reward} XP</span>
          </div>
          <h1 style={{ marginTop: 10 }}>{activity.title}</h1>
          <p className="muted">{activity.description}</p>
          {activity.safety_notes && <Alert kind="info">{activity.safety_notes}</Alert>}
        </div>

        {result ? (
          <div className="stack">
            <Alert kind="success">
              <strong>{result.already_completed ? 'Already recorded.' : 'Nicely done — activity complete.'}</strong>{' '}
              {result.xp_awarded ? `+${result.xp_awarded} XP. ` : ''}
              {result.xp_note || ''}
              {result.new_badges.map((b) => ` New badge: ${b.name}!`).join('')}
            </Alert>
            <div>
              <div className="row small" style={{ justifyContent: 'space-between' }}>
                <strong>Level {result.progress.level}</strong>
                <span className="muted">{result.progress.total_xp} / {result.progress.next_level_xp} XP · {result.progress.current_streak}-day streak</span>
              </div>
              <ProgressBar value={result.progress.progress_pct} label="Progress to next level" />
            </div>
            <div className="row">
              <Link className="btn btn-primary" to="/app">Back to home</Link>
              <Link className="btn btn-secondary" to="/app/activities">More activities</Link>
              <Link className="btn btn-ghost" to="/app/chat">Talk about how it went</Link>
            </div>
          </div>
        ) : !session ? (
          <div className="stack">
            <h3 style={{ margin: 0 }}>How it works</h3>
            <ol className="small" style={{ margin: 0, paddingLeft: 20 }}>
              {activity.instructions.map((s, i) => <li key={i}>{s}</li>)}
            </ol>
            <p className="tiny muted" style={{ margin: 0 }}>Counts as complete when: {activity.completion_criteria}</p>
            {startError && <Alert kind="error">{startError.message}</Alert>}
            <div className="row">
              <button className="btn btn-primary btn-lg" onClick={start} disabled={starting}>{starting ? 'Starting…' : 'Start'}</button>
              <Link className="btn btn-ghost" to="/app/activities">Not now</Link>
            </div>
          </div>
        ) : (
          <div className="stack">
            <div className="row" style={{ justifyContent: 'space-between' }}>
              <div className="timer" aria-label={`Elapsed ${fmt(elapsed)}`}>{fmt(elapsed)}</div>
              <div className="row">
                <button className="btn btn-secondary btn-sm" onClick={() => setRunning((r) => !r)}>{running ? 'Pause' : 'Resume'}</button>
              </div>
            </div>
            <ProgressBar value={(elapsed / target) * 100} label="Time progress" />

            {activity.kind === 'breathing' && <Breathing activity={activity} elapsed={elapsed} running={running} />}
            {activity.kind === 'guided_steps' && <Steps activity={activity} current={step} setCurrent={setStep} />}
            {activity.kind === 'journal' && (
              <div className="stack">
                {prompts.length > 0 && (
                  <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>
                    {prompts.map((p, i) => <li key={i}>{p}</li>)}
                  </ul>
                )}
                <Field id="journal" label="Your reflection" hint={`${journal.trim().length}/20 characters minimum. Not sent to the AI or teachers.`}>
                  <textarea id="journal" className="textarea" style={{ minHeight: 180 }} maxLength={5000} value={journal}
                    onChange={(e) => setJournal(e.target.value)} />
                </Field>
                <label className="check">
                  <input type="checkbox" checked={saveJournal} onChange={(e) => setSaveJournal(e.target.checked)} />
                  <span>Save this to my private journal (otherwise it's discarded after completion)</span>
                </label>
              </div>
            )}

            {completeError && <Alert kind="error">{completeError.message}</Alert>}
            <div className="row">
              <button className="btn btn-primary" onClick={complete} disabled={!canComplete || completing}>
                {completing ? 'Saving…' : 'Mark complete'}
              </button>
              <Link className="btn btn-ghost" to="/app/activities">Stop — that's okay</Link>
            </div>
            {!canComplete && (
              <p className="tiny muted" style={{ margin: 0 }}>
                {!timeOk && `Complete becomes available after ${fmt(minSeconds)}. `}
                {!stepsDone && 'Go through all the steps. '}
                {!journalOk && 'Write at least a couple of sentences. '}
                Stopping early is fine — it just won't earn XP.
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
