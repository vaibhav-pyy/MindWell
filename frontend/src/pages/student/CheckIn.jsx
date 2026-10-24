import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert, Field, Loading, useToast } from '../../components/ui';
import { api } from '../../lib/api';

export const QUESTIONS = [
  { key: 'mood', q: 'How has your mood been today?', ends: ['Very low', 'Very good'] },
  { key: 'stress', q: 'How stressed have you felt today?', ends: ['Not at all', 'Extremely'] },
  { key: 'anxiety', q: 'How worried, nervous or on edge have you felt?', ends: ['Not at all', 'Extremely'] },
  { key: 'sleep_quality', q: 'How well did you sleep last night?', ends: ['Very poorly', 'Very well'] },
  { key: 'academic_pressure', q: 'How much academic pressure are you feeling?', ends: ['None', 'Overwhelming'] },
];

export const STRESSORS = {
  exams: 'Exams', assignments: 'Assignments & deadlines', sleep: 'Sleep', relationships: 'Friends & relationships',
  family: 'Family', finances: 'Finances', health: 'Health', future: 'Career & future', other: 'Something else',
};

export function CheckInForm({ initial, onSubmit, submitLabel = 'Save check-in', busy }) {
  const [values, setValues] = useState(() => ({
    mood: null, stress: null, anxiety: null, sleep_quality: null, academic_pressure: null, sleep_hours: '',
    stressors: [], note: '', ...(initial || {}),
  }));
  const toggle = (k, v) => setValues((s) => ({ ...s, [k]: s[k] === v ? null : v }));
  const toggleStressor = (code) => setValues((s) => ({
    ...s, stressors: s.stressors.includes(code) ? s.stressors.filter((c) => c !== code) : [...s.stressors, code],
  }));

  function submit(e) {
    e.preventDefault();
    const body = { ...values, sleep_hours: values.sleep_hours === '' ? null : Number(values.sleep_hours) };
    onSubmit(body);
  }

  return (
    <form className="stack" onSubmit={submit}>
      {QUESTIONS.map((q) => (
        <fieldset className="card" key={q.key} style={{ margin: 0 }}>
          <legend className="sr-only">{q.q}</legend>
          <div className="row" style={{ justifyContent: 'space-between', marginBottom: 10 }}>
            <strong aria-hidden="true">{q.q}</strong>
            {values[q.key] != null && (
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => toggle(q.key, values[q.key])}>Clear</button>
            )}
          </div>
          <div className="scale" role="group" aria-label={q.q}>
            {[1, 2, 3, 4, 5].map((n) => (
              <button type="button" key={n} aria-pressed={values[q.key] === n} onClick={() => toggle(q.key, n)}
                aria-label={`${n} of 5${n === 1 ? ` (${q.ends[0]})` : ''}${n === 5 ? ` (${q.ends[1]})` : ''}`}>
                {n}
              </button>
            ))}
          </div>
          <div className="scale-ends"><span>{q.ends[0]}</span><span>{q.ends[1]}</span></div>
        </fieldset>
      ))}
      <div className="card">
        <Field id="sleep-hours" label="Roughly how many hours did you sleep last night?" hint="Optional. 0–16.">
          <input id="sleep-hours" className="input" type="number" min="0" max="16" step="0.5" inputMode="decimal"
            value={values.sleep_hours ?? ''} style={{ maxWidth: 140 }}
            onChange={(e) => setValues((s) => ({ ...s, sleep_hours: e.target.value }))} />
        </Field>
      </div>
      <fieldset className="card" style={{ margin: 0 }}>
        <legend className="sr-only">What's weighing on you?</legend>
        <strong aria-hidden="true">Is anything weighing on you? <span className="muted small">(optional, pick any)</span></strong>
        <div className="chips" style={{ marginTop: 10 }}>
          {Object.entries(STRESSORS).map(([code, label]) => (
            <button type="button" key={code} className="chip" aria-pressed={values.stressors.includes(code)}
              onClick={() => toggleStressor(code)}>{label}</button>
          ))}
        </div>
      </fieldset>
      <div className="card">
        <Field id="note" label="Private note (optional)" hint="Only you can see this. It is not sent to the AI or to teachers.">
          <textarea id="note" className="textarea" maxLength={1000} value={values.note || ''}
            onChange={(e) => setValues((s) => ({ ...s, note: e.target.value }))} />
        </Field>
      </div>
      <button className="btn btn-primary btn-lg" disabled={busy}>{busy ? 'Saving…' : submitLabel}</button>
    </form>
  );
}

export default function CheckIn() {
  const navigate = useNavigate();
  const toast = useToast();
  const [initial, setInitial] = useState(undefined);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get('/api/wellness/summary')
      .then((s) => {
        const today = s.checked_in_today ? s.latest : null;
        setInitial(today ? { ...today.inputs, sleep_hours: today.inputs.sleep_hours ?? '', stressors: today.stressors, note: today.note || '' } : null);
      })
      .catch(() => setInitial(null));
  }, []);

  async function submit(body) {
    setBusy(true);
    setError(null);
    try {
      const data = await api.post('/api/checkins', body);
      const extras = [data.xp_awarded ? `+${data.xp_awarded} XP` : null, ...data.new_badges.map((b) => `Badge: ${b.name}`)].filter(Boolean);
      toast(`${data.created ? 'Check-in saved' : 'Check-in updated'}${extras.length ? ` · ${extras.join(' · ')}` : ''}`);
      navigate('/app/wellness');
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  if (initial === undefined) return <Loading />;
  return (
    <div style={{ maxWidth: 720, margin: '0 auto' }}>
      <div className="page-header">
        <div>
          <h1>Daily check-in</h1>
          <p>Answer only what you want to. There are no right answers, and skipping is fine.</p>
        </div>
      </div>
      {initial && <Alert kind="info">You've already checked in today — saving will update today's answers.</Alert>}
      {error && <Alert kind="error">{error.message}</Alert>}
      <div style={{ marginTop: 16 }}>
        <CheckInForm initial={initial} onSubmit={submit} busy={busy} submitLabel={initial ? 'Update check-in' : 'Save check-in'} />
      </div>
    </div>
  );
}
