import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Icon from '../../components/Icon';
import { Alert, ConfirmButton, Empty, ErrorState, Field, Loading, useToast } from '../../components/ui';
import { ActivityCard, CATEGORY_LABELS } from '../../components/WellnessBits';
import { api } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { useApi } from '../../lib/hooks';

function Generator({ onCreated }) {
  const { user } = useAuth();
  const [concern, setConcern] = useState('');
  const [minutes, setMinutes] = useState(5);
  const [preference, setPreference] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const a = await api.post('/api/activities/generate', { concern, available_minutes: Number(minutes), preference: preference || null });
      onCreated(a);
      setConcern('');
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card stack" onSubmit={submit} aria-labelledby="gen-h">
      <div>
        <h2 id="gen-h"><Icon name="sparkle" size={18} /> Create a personal activity with AI</h2>
        <p className="small muted" style={{ margin: 0 }}>
          Describe what's going on and how much time you have. Gemini drafts a short, low-risk activity; MindWell checks it
          for safety before saving it. XP is set by MindWell, not the AI. What you type here is sent to Gemini.
        </p>
      </div>
      {!user?.privacy?.ai_processing_consent && (
        <Alert kind="info">This needs AI processing to be allowed in Settings → Privacy.</Alert>
      )}
      {error && (
        <Alert kind="error">
          {error.message}
          {error.code === 'ai_unavailable' && ' Nothing was created. You can still use the built-in activities below.'}
        </Alert>
      )}
      <Field id="concern" label="What's on your mind?" hint="e.g. “I keep procrastinating before my lab report”. Avoid names or personal details.">
        <textarea id="concern" className="textarea" style={{ minHeight: 80 }} maxLength={300} value={concern}
          onChange={(e) => setConcern(e.target.value)} required />
      </Field>
      <div className="form-grid">
        <Field id="minutes" label="Time available">
          <select id="minutes" className="select" value={minutes} onChange={(e) => setMinutes(e.target.value)}>
            {[3, 5, 10, 15, 20].map((m) => <option key={m} value={m}>{m} minutes</option>)}
          </select>
        </Field>
        <Field id="pref" label="Preferred type">
          <select id="pref" className="select" value={preference} onChange={(e) => setPreference(e.target.value)}>
            <option value="">No preference</option>
            <option value="breathing">Breathing</option>
            <option value="journal">Writing / journaling</option>
            <option value="guided_steps">Guided steps</option>
          </select>
        </Field>
      </div>
      <button className="btn btn-primary" disabled={busy || concern.trim().length < 3 || !user?.privacy?.ai_processing_consent}>
        {busy ? 'Creating…' : 'Create activity'}
      </button>
    </form>
  );
}

export default function Activities() {
  const toast = useToast();
  const navigate = useNavigate();
  const recs = useApi('/api/recommendations/today');
  const all = useApi('/api/activities');
  const [tab, setTab] = useState('today');
  const [category, setCategory] = useState('');

  async function dismiss(id) {
    try {
      await api.post(`/api/recommendations/${id}/dismiss`);
      recs.setData((list) => list.map((r) => (r.id === id ? { ...r, status: 'dismissed' } : r)));
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  async function removePersonal(id) {
    try {
      await api.del(`/api/activities/${id}`);
      all.reload();
      toast('Activity removed.');
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  const list = (all.data || []).filter((a) => !category || a.category === category);
  const visibleRecs = (recs.data || []).filter((r) => r.status !== 'dismissed');

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h1>Activities</h1>
          <p>Short, optional exercises. Do as many or as few as you like — there's no penalty for skipping.</p>
        </div>
      </div>
      <div className="tabs" role="tablist" aria-label="Activity views">
        {[['today', "Today's suggestions"], ['all', 'All activities'], ['create', 'Create with AI']].map(([k, label]) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}>{label}</button>
        ))}
      </div>

      {tab === 'today' && (
        <div role="tabpanel">
          {recs.loading && <Loading />}
          {recs.error && <ErrorState error={recs.error} onRetry={recs.reload} />}
          {recs.data && !visibleRecs.length && <div className="card"><Empty title="Nothing suggested right now"><p className="small">Browse all activities or create one with AI.</p></Empty></div>}
          <div className="grid grid-3">
            {visibleRecs.map((r) => (
              <ActivityCard key={r.id} activity={r.activity} reason={r.reason} status={r.status} source={r.source}
                onDismiss={() => dismiss(r.id)} />
            ))}
          </div>
        </div>
      )}

      {tab === 'all' && (
        <div role="tabpanel" className="stack">
          <div className="chips" role="group" aria-label="Filter by category">
            <button className="chip" aria-pressed={!category} onClick={() => setCategory('')}>All</button>
            {Object.entries(CATEGORY_LABELS).map(([k, v]) => (
              <button key={k} className="chip" aria-pressed={category === k} onClick={() => setCategory(k)}>{v}</button>
            ))}
          </div>
          {all.loading && <Loading />}
          {all.error && <ErrorState error={all.error} onRetry={all.reload} />}
          {all.data && !list.length && <p className="muted">No activities in this category yet.</p>}
          <div className="grid grid-3">
            {list.map((a) => (
              <div key={a.id} className="stack-sm">
                <ActivityCard activity={a} />
                {a.is_personal && (
                  <ConfirmButton confirmText="Remove this activity?" onConfirm={() => removePersonal(a.id)}>
                    <Icon name="trash" size={14} /> Remove
                  </ConfirmButton>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === 'create' && (
        <div role="tabpanel" style={{ maxWidth: 680 }}>
          <Generator onCreated={(a) => {
            toast('Activity created. It has been added to your suggestions for today.');
            all.reload();
            recs.reload();
            navigate(`/app/activities/${a.id}`);
          }} />
        </div>
      )}
    </div>
  );
}
