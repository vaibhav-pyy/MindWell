import { useState } from 'react';
import { Link } from 'react-router-dom';
import Icon from '../../components/Icon';
import { Alert, ConfirmButton, Empty, ErrorState, Field, Loading, useToast } from '../../components/ui';
import { api } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { useApi } from '../../lib/hooks';

export default function TeacherHome() {
  const { user } = useAuth();
  const toast = useToast();
  const { data, error, loading, reload } = useApi('/api/teacher/classes');
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);

  async function create(e) {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post('/api/teacher/classes', { name });
      setName('');
      reload();
      toast('Class created. Share the join code with your students.');
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      setBusy(false);
    }
  }

  async function act(fn, msg) {
    try {
      await fn();
      reload();
      toast(msg);
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h1>Welcome, {user.display_name}</h1>
          <p>Class-level wellbeing trends to help you plan supportive, whole-class initiatives.</p>
        </div>
        <span className="badge"><Icon name="lock" size={14} /> Aggregated data only</span>
      </div>
      <Alert kind="info">
        You will only ever see anonymous averages from students who chose to share, and only when at least five students
        contribute. Individual chats, check-ins, journals, scores and emergency contacts are never available to teachers.
        This dashboard is for supportive planning — not for monitoring, ranking or disciplining students.
      </Alert>

      <form className="card row" onSubmit={create} style={{ alignItems: 'flex-end' }}>
        <div style={{ flex: 1, minWidth: 220 }}>
          <Field id="cls-name" label="Create a class">
            <input id="cls-name" className="input" placeholder="e.g. 24AIM57 · Section A" maxLength={120} value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
        </div>
        <button className="btn btn-primary" disabled={busy || name.trim().length < 2}><Icon name="plus" size={16} /> Create</button>
      </form>

      {loading && <Loading />}
      {error && <ErrorState error={error} onRetry={reload} />}
      {data && !data.length && <div className="card"><Empty title="No classes yet" icon="users"><p className="small">Create a class and share its join code with students.</p></Empty></div>}
      <div className="grid grid-3">
        {data?.map((c) => (
          <div className="card stack-sm" key={c.id}>
            <h2 style={{ margin: 0 }}>{c.name}</h2>
            <p className="small muted" style={{ margin: 0 }}>{c.member_count} member{c.member_count === 1 ? '' : 's'}</p>
            <p className="small" style={{ margin: 0 }}>Join code: <strong style={{ letterSpacing: 1 }}>{c.join_code}</strong></p>
            <div className="row">
              <Link className="btn btn-primary btn-sm" to={`/teacher/classes/${c.id}`}>View trends</Link>
              <button className="btn btn-ghost btn-sm" onClick={() => act(() => api.post(`/api/teacher/classes/${c.id}/rotate-code`), 'New join code generated.')}>New code</button>
              <ConfirmButton confirmText="Delete class?" onConfirm={() => act(() => api.del(`/api/teacher/classes/${c.id}`), 'Class deleted.')}>Delete</ConfirmButton>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
