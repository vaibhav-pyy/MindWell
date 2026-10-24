import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import Icon from '../../components/Icon';
import { Alert, ConfirmButton, ErrorState, Field, Loading, useToast } from '../../components/ui';
import { api } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { formatDateTime, useApi } from '../../lib/hooks';

const TABS = [
  ['profile', 'Profile'], ['privacy', 'Privacy'], ['memory', 'Memory'], ['classes', 'Classes'],
  ['journal', 'Journal'], ['account', 'Account & data'],
];

function ProfileTab() {
  const toast = useToast();
  const { setUser } = useAuth();
  const { data, error, loading, reload } = useApi('/api/profile');
  const [form, setForm] = useState(null);
  const [busy, setBusy] = useState(false);
  if (loading) return <Loading />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  const f = form || { display_name: data.display_name, pronouns: data.pronouns || '', year_of_study: data.year_of_study || '' };
  const set = (k) => (e) => setForm({ ...f, [k]: e.target.value });
  async function save(e) {
    e.preventDefault();
    setBusy(true);
    try {
      const updated = await api.patch('/api/profile', f);
      setUser((u) => ({ ...u, display_name: updated.display_name }));
      toast('Profile saved.');
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      setBusy(false);
    }
  }
  return (
    <form className="card stack" onSubmit={save} style={{ maxWidth: 620 }}>
      <Field id="p-name" label="Display name"><input id="p-name" className="input" maxLength={80} value={f.display_name} onChange={set('display_name')} /></Field>
      <div className="form-grid">
        <Field id="p-pron" label="Pronouns (optional)"><input id="p-pron" className="input" maxLength={40} value={f.pronouns} onChange={set('pronouns')} /></Field>
        <Field id="p-year" label="Year of study (optional)"><input id="p-year" className="input" maxLength={40} value={f.year_of_study} onChange={set('year_of_study')} /></Field>
      </div>
      <p className="small muted" style={{ margin: 0 }}>Email: {data.email}. Your name and email are never sent to the AI.</p>
      <button className="btn btn-primary" disabled={busy}>Save profile</button>
    </form>
  );
}

function PrivacyTab() {
  const { user, setUser } = useAuth();
  const toast = useToast();
  const consents = useApi('/api/privacy/consents');
  const p = user.privacy;
  async function toggle(key, value) {
    try {
      const privacy = await api.patch('/api/privacy', { [key]: value });
      setUser((u) => ({ ...u, privacy }));
      consents.reload();
      toast('Privacy setting updated.');
    } catch (err) {
      toast(err.message, 'error');
    }
  }
  const items = [
    ['ai_processing_consent', 'Allow AI processing', "Your chat messages (and text you type into the activity generator) are sent to Google's Gemini API to generate replies. Turning this off disables the AI features; helplines and everything else keep working."],
    ['memory_enabled', 'Let MindWell remember across conversations', 'Your own notes and short AI summaries of past conversations are included as context in new chats. Turn off to start every conversation fresh.'],
    ['personalize_with_checkins', 'Personalise chat with my check-in numbers', "Sends your latest check-in indicator numbers (e.g. 'stress 75/100') to the AI so replies can take them into account. Your private note is never sent."],
  ];
  return (
    <div className="stack" style={{ maxWidth: 760 }}>
      <div className="card stack">
        {items.map(([key, label, desc]) => (
          <label className="check" key={key}>
            <input type="checkbox" checked={!!p[key]} onChange={(e) => toggle(key, e.target.checked)} />
            <span><strong>{label}</strong><br /><span className="small muted">{desc}</span></span>
          </label>
        ))}
      </div>
      <div className="card small stack-sm">
        <h3>What's shared with whom</h3>
        <ul style={{ margin: 0, paddingLeft: 18 }}>
          <li><strong>Teachers:</strong> only anonymous averages of check-in numbers and activity counts for classes where you opted in, and only when at least 5 students contribute. Never chats, notes, journal, scores or your emergency contact.</li>
          <li><strong>Google Gemini:</strong> if allowed — chat messages, recent conversation context, your memory items, and optionally your latest check-in numbers. Not your name, email or contacts. Google processes this under its API terms.</li>
          <li><strong>Your emergency contact:</strong> only a message you preview and confirm, containing only the fields you chose.</li>
          <li>MindWell can't promise absolute confidentiality — no online service can — but we collect the minimum and let you delete it.</li>
        </ul>
      </div>
      <div className="card">
        <h3>Consent history</h3>
        {consents.data && (
          <div className="table-scroll">
            <table className="data">
              <thead><tr><th scope="col">When</th><th scope="col">What</th><th scope="col">Decision</th></tr></thead>
              <tbody>
                {consents.data.map((c, i) => (
                  <tr key={i}><td>{formatDateTime(c.at)}</td><td>{c.type.replaceAll('_', ' ')}</td><td>{c.granted ? 'Allowed' : 'Not allowed'}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function MemoryTab() {
  const toast = useToast();
  const { data, error, loading, reload } = useApi('/api/memory');
  const [note, setNote] = useState('');
  if (loading) return <Loading />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  async function add(e) {
    e.preventDefault();
    try {
      await api.post('/api/memory', { content: note });
      setNote('');
      reload();
    } catch (err) {
      toast(err.message, 'error');
    }
  }
  async function del(id) {
    await api.del(id ? `/api/memory/${id}` : '/api/memory');
    reload();
    toast(id ? 'Deleted.' : 'All memory cleared.');
  }
  return (
    <div className="stack" style={{ maxWidth: 760 }}>
      {!data.memory_enabled && <Alert kind="info">Memory is turned off in Privacy, so none of this is used in chats right now.</Alert>}
      <form className="card stack" onSubmit={add}>
        <Field id="m-note" label="Add something you'd like MindWell to remember" hint="Written by you, used as-is. e.g. “I'm a 2nd-year engineering student and I prefer short replies.”">
          <textarea id="m-note" className="textarea" style={{ minHeight: 70 }} maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
        <button className="btn btn-primary" disabled={note.trim().length < 3}>Add note</button>
      </form>
      <div className="card">
        <div className="card-header">
          <h3>What MindWell remembers</h3>
          {data.items.length > 0 && <ConfirmButton confirmText="Clear all memory?" onConfirm={() => del(null)}>Clear all</ConfirmButton>}
        </div>
        {!data.items.length && <p className="small muted">Nothing yet. Summaries are created when you start a new conversation after chatting (if memory is on).</p>}
        <ul className="list">
          {data.items.map((m) => (
            <li key={m.id} style={{ alignItems: 'flex-start' }}>
              <span className={`badge ${m.kind === 'ai_summary' ? 'badge-ai' : 'badge-self'}`}>{m.label}</span>
              <span className="small" style={{ flex: 1 }}>{m.content}<br /><span className="tiny muted">{formatDateTime(m.created_at)}</span></span>
              <button className="icon-btn" aria-label="Delete memory item" onClick={() => del(m.id)}><Icon name="trash" size={16} /></button>
            </li>
          ))}
        </ul>
      </div>
      <div className="card">
        <h3>Conversation history</h3>
        <p className="small muted">Delete individual conversations from the chat screen, or remove all of them here. Conversations are automatically deleted after the retention period set by the server.</p>
        <ConfirmButton className="btn btn-secondary btn-sm" confirmText="Delete every conversation?"
          onConfirm={async () => { const r = await api.del('/api/conversations'); toast(`Deleted ${r.deleted} conversations.`); }}>
          Delete all conversations
        </ConfirmButton>
      </div>
    </div>
  );
}

function ClassesTab() {
  const toast = useToast();
  const { data, error, loading, reload } = useApi('/api/classes/mine');
  const [code, setCode] = useState('');
  const [share, setShare] = useState(false);
  const [busy, setBusy] = useState(false);
  if (loading) return <Loading />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  async function join(e) {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post('/api/classes/join', { join_code: code.trim(), share_aggregates: share });
      setCode('');
      setShare(false);
      reload();
      toast('Joined class.');
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      setBusy(false);
    }
  }
  async function setSharing(id, value) {
    try {
      await api.patch(`/api/classes/${id}/sharing`, { share_aggregates: value });
      reload();
    } catch (err) {
      toast(err.message, 'error');
    }
  }
  return (
    <div className="stack" style={{ maxWidth: 760 }}>
      <form className="card stack" onSubmit={join}>
        <Field id="j-code" label="Join a class" hint="Your teacher can give you the class code.">
          <input id="j-code" className="input" style={{ maxWidth: 220, textTransform: 'uppercase' }} maxLength={12} value={code} onChange={(e) => setCode(e.target.value)} />
        </Field>
        <label className="check">
          <input type="checkbox" checked={share} onChange={(e) => setShare(e.target.checked)} />
          <span>Contribute my check-in numbers and activity counts to <strong>anonymous</strong> class averages. Teachers never see individual answers, and nothing is shown unless at least 5 students contribute. Optional.</span>
        </label>
        <button className="btn btn-primary" disabled={busy || code.trim().length < 4}>Join</button>
      </form>
      <div className="card">
        <h3>Your classes</h3>
        {!data.length && <p className="small muted">You haven't joined a class.</p>}
        <ul className="list">
          {data.map((c) => (
            <li key={c.class_id} style={{ flexWrap: 'wrap' }}>
              <strong style={{ flex: 1 }}>{c.name}</strong>
              <label className="check small">
                <input type="checkbox" checked={c.share_aggregates} onChange={(e) => setSharing(c.class_id, e.target.checked)} />
                <span>Share anonymous numbers</span>
              </label>
              <ConfirmButton confirmText="Leave class?" onConfirm={async () => { await api.del(`/api/classes/${c.class_id}/membership`); reload(); }}>Leave</ConfirmButton>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function JournalTab() {
  const { data, error, loading, reload } = useApi('/api/journal');
  if (loading) return <Loading />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  return (
    <div className="card" style={{ maxWidth: 760 }}>
      <h3>Private journal</h3>
      <p className="small muted">Entries you chose to save from journaling activities. Only you can see these; they are not sent to the AI.</p>
      {!data.length && <p className="small muted">No saved entries.</p>}
      <ul className="list">
        {data.map((j) => (
          <li key={j.id} style={{ alignItems: 'flex-start' }}>
            <div style={{ flex: 1 }}>
              <div className="tiny muted">{formatDateTime(j.created_at)} · {j.prompt}</div>
              <div className="small" style={{ whiteSpace: 'pre-wrap' }}>{j.content}</div>
            </div>
            <ConfirmButton confirmText="Delete?" onConfirm={async () => { await api.del(`/api/journal/${j.id}`); reload(); }}>
              <Icon name="trash" size={14} />
            </ConfirmButton>
          </li>
        ))}
      </ul>
    </div>
  );
}

function AccountTab() {
  const toast = useToast();
  const navigate = useNavigate();
  const { setUser } = useAuth();
  const [pw, setPw] = useState({ current_password: '', new_password: '' });
  const [del, setDel] = useState({ password: '', confirm: '' });
  const [delError, setDelError] = useState(null);

  async function changePassword(e) {
    e.preventDefault();
    try {
      await api.post('/api/account/password', pw);
      setPw({ current_password: '', new_password: '' });
      toast('Password changed.');
    } catch (err) {
      toast(err.message, 'error');
    }
  }
  async function exportData() {
    try {
      const data = await api.get('/api/account/export');
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'mindwell-my-data.json';
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast(err.message, 'error');
    }
  }
  async function deleteAccount(e) {
    e.preventDefault();
    setDelError(null);
    try {
      await api.del('/api/account', del);
      setUser(null);
      navigate('/', { replace: true });
    } catch (err) {
      setDelError(err);
    }
  }
  return (
    <div className="stack" style={{ maxWidth: 620 }}>
      <div className="card stack">
        <h3>Download your data</h3>
        <p className="small muted" style={{ margin: 0 }}>A JSON file with everything MindWell stores about you.</p>
        <button className="btn btn-secondary" onClick={exportData}><Icon name="download" size={16} /> Download my data</button>
      </div>
      <form className="card stack" onSubmit={changePassword}>
        <h3>Change password</h3>
        <Field id="pw-cur" label="Current password"><input id="pw-cur" type="password" className="input" autoComplete="current-password" value={pw.current_password} onChange={(e) => setPw({ ...pw, current_password: e.target.value })} /></Field>
        <Field id="pw-new" label="New password" hint="At least 10 characters with a letter and a number."><input id="pw-new" type="password" className="input" autoComplete="new-password" value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} /></Field>
        <button className="btn btn-primary" disabled={!pw.current_password || !pw.new_password}>Change password</button>
      </form>
      <form className="card stack" onSubmit={deleteAccount} style={{ borderColor: '#f5c6c3' }}>
        <h3>Delete account</h3>
        <p className="small" style={{ margin: 0 }}>
          Permanently deletes your account and everything linked to it: conversations, memory, check-ins, journal, activity
          history, XP, emergency contact and alert logs. Anonymous class averages already viewed by a teacher can't be
          un-seen, but your data is removed from all future calculations. Content already processed by Gemini is subject to
          Google's own retention policies.
        </p>
        {delError && <Alert kind="error">{delError.message}</Alert>}
        <Field id="del-pw" label="Password"><input id="del-pw" type="password" className="input" value={del.password} onChange={(e) => setDel({ ...del, password: e.target.value })} /></Field>
        <Field id="del-confirm" label="Type DELETE to confirm"><input id="del-confirm" className="input" value={del.confirm} onChange={(e) => setDel({ ...del, confirm: e.target.value })} /></Field>
        <button className="btn btn-danger" disabled={del.confirm !== 'DELETE' || !del.password}>Permanently delete my account</button>
      </form>
    </div>
  );
}

const PANELS = { profile: ProfileTab, privacy: PrivacyTab, memory: MemoryTab, classes: ClassesTab, journal: JournalTab, account: AccountTab };

export default function Settings() {
  const [params, setParams] = useSearchParams();
  const tab = PANELS[params.get('tab')] ? params.get('tab') : 'profile';
  const Panel = PANELS[tab];
  return (
    <div>
      <div className="page-header"><div><h1>Settings</h1><p>Your profile, privacy, memory and data.</p></div></div>
      <div className="tabs" role="tablist" aria-label="Settings sections">
        {TABS.map(([k, label]) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => setParams({ tab: k })}>{label}</button>
        ))}
      </div>
      <div role="tabpanel"><Panel /></div>
    </div>
  );
}
