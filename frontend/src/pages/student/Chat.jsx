import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import Icon from '../../components/Icon';
import { GetHelpButton, HelplineActions, useSupport } from '../../components/SupportPanel';
import { Alert, ConfirmButton, ErrorState, Loading, useToast } from '../../components/ui';
import { api } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { formatDate, formatDateTime } from '../../lib/hooks';

const SOURCE_LABEL = {
  gemini: 'AI reply (Gemini)',
  safety_template: 'MindWell safety message — pre-written, not AI-generated',
};

function Bubble({ m }) {
  const cls = m.role === 'user' ? 'user' : m.source === 'safety_template' ? 'assistant safety' : 'assistant';
  return (
    <div className={`bubble-row ${cls}`}>
      <div className="bubble">{m.content}</div>
      <div className="bubble-meta">
        {m.role === 'user' ? 'You' : SOURCE_LABEL[m.source]}
        {m.created_at && ` · ${formatDateTime(m.created_at)}`}
        {m.pending && ' · sending…'}
      </div>
      {m.suggested_activities?.length > 0 && (
        <div className="chips" style={{ marginTop: 6 }}>
          {m.suggested_activities.map((a) => (
            <Link key={a.id} className="chip" to={`/app/activities/${a.id}`}>
              <Icon name="bolt" size={14} /> {a.title} · {a.duration_minutes} min
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Chat() {
  const { conversationId } = useParams();
  const navigate = useNavigate();
  const { user, setUser } = useAuth();
  const { openSupport } = useSupport();
  const toast = useToast();
  const [convs, setConvs] = useState(null);
  const [listError, setListError] = useState(null);
  const [conv, setConv] = useState(null);
  const [convLoading, setConvLoading] = useState(false);
  const [convError, setConvError] = useState(null);
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState(null);
  const [safety, setSafety] = useState(null);
  const [showList, setShowList] = useState(false);
  const scrollRef = useRef(null);
  const loadedId = useRef(null); // id of the conversation already in state (skip refetch)
  const aiAllowed = user?.privacy?.ai_processing_consent;

  const loadList = useCallback(async () => {
    try {
      setConvs(await api.get('/api/conversations'));
      setListError(null);
    } catch (err) {
      setListError(err);
    }
  }, []);

  useEffect(() => {
    loadList();
  }, [loadList]);

  useEffect(() => {
    if (conversationId && loadedId.current === conversationId) return;
    setSafety(null);
    setSendError(null);
    if (!conversationId) {
      loadedId.current = null;
      setConv(null);
      return;
    }
    loadedId.current = conversationId;
    setConvLoading(true);
    setConvError(null);
    api.get(`/api/conversations/${conversationId}`)
      .then(setConv)
      .catch(setConvError)
      .finally(() => setConvLoading(false));
  }, [conversationId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [conv?.messages?.length, sending]);

  async function newConversation({ go = true } = {}) {
    try {
      const c = await api.post('/api/conversations');
      await loadList();
      if (go) navigate(`/app/chat/${c.id}`);
      setShowList(false);
      return c;
    } catch (err) {
      toast(err.message, 'error');
      return null;
    }
  }

  async function send(e) {
    e?.preventDefault();
    const content = text.trim();
    if (!content || sending) return;
    setSending(true);
    setSendError(null);
    let target = conv;
    if (!target) {
      target = await newConversation({ go: false });
      if (!target) {
        setSending(false);
        return;
      }
      target = { ...target, messages: [] };
      loadedId.current = String(target.id);
      navigate(`/app/chat/${target.id}`, { replace: true });
    }
    const pending = { id: `p-${Date.now()}`, role: 'user', content, pending: true };
    setConv({ ...target, messages: [...(target.messages || []), pending] });
    setText('');
    try {
      const data = await api.post(`/api/conversations/${target.id}/messages`, { content });
      setConv((c) => ({
        ...c,
        title: data.conversation.title,
        messages: [...c.messages.filter((m) => m.id !== pending.id), data.user_message, data.assistant_message],
      }));
      if (data.safety?.show_support) {
        setSafety(data.safety);
        if (data.safety.level === 'crisis') openSupport({ urgent: true });
      }
      loadList();
    } catch (err) {
      // Nothing was saved server-side; restore the text so the student can retry.
      setConv((c) => ({ ...c, messages: c.messages.filter((m) => m.id !== pending.id) }));
      setText(content);
      setSendError(err);
      const s = err.details?.safety;
      if (s?.show_support) setSafety(s);
    } finally {
      setSending(false);
    }
  }

  async function enableAI() {
    try {
      const privacy = await api.patch('/api/privacy', { ai_processing_consent: true });
      setUser((u) => ({ ...u, privacy }));
      setSendError(null);
      toast('AI processing allowed. You can turn it off any time in Settings.');
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  async function deleteConversation(id) {
    try {
      await api.del(`/api/conversations/${id}`);
      toast('Conversation deleted.');
      await loadList();
      if (String(id) === String(conversationId)) navigate('/app/chat');
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  return (
    <div className="chat-layout">
      <aside className={`card chat-sidebar ${showList ? 'open' : ''}`} aria-label="Conversations">
        <button className="btn btn-primary btn-block btn-sm" onClick={() => newConversation()}>
          <Icon name="plus" size={16} /> New conversation
        </button>
        <div style={{ marginTop: 12 }} className="stack-sm">
          {listError && <ErrorState error={listError} onRetry={loadList} />}
          {!convs && !listError && <Loading />}
          {convs?.length === 0 && <p className="small muted">No conversations yet.</p>}
          {convs?.map((c) => (
            <div key={c.id} className="row" style={{ gap: 2, flexWrap: 'nowrap' }}>
              <button
                className={`conv-item ${String(c.id) === conversationId ? 'active' : ''}`}
                onClick={() => {
                  navigate(`/app/chat/${c.id}`);
                  setShowList(false);
                }}
                aria-current={String(c.id) === conversationId ? 'page' : undefined}
              >
                <span className="t">{c.title}</span>
                <span className="d">{formatDate(c.updated_at)}</span>
              </button>
            </div>
          ))}
        </div>
        <p className="tiny muted" style={{ marginTop: 14 }}>
          Manage what MindWell remembers in <Link to="/app/settings?tab=memory">Settings → Memory</Link>.
        </p>
      </aside>

      <section className="card chat-panel" aria-label="Chat with MindWell">
        <div className="chat-head">
          <button className="icon-btn" aria-label="Show conversations" onClick={() => setShowList((s) => !s)}
            style={{ display: 'inline-grid' }}>
            <Icon name="menu" />
          </button>
          <div style={{ flex: 1, minWidth: 0 }}>
            <strong style={{ color: 'var(--teal-900)' }}>{conv?.title || 'MindWell Companion'}</strong>
            <div className="tiny muted">AI wellbeing companion · not a therapist or emergency service</div>
          </div>
          {conv && (
            <ConfirmButton confirmText="Delete this conversation?" onConfirm={() => deleteConversation(conv.id)}>
              <Icon name="trash" size={16} /> Delete
            </ConfirmButton>
          )}
          <GetHelpButton />
        </div>

        <div className="chat-scroll" ref={scrollRef} aria-live="polite">
          {convLoading && <Loading />}
          {convError && <ErrorState error={convError} />}
          {!convLoading && !convError && (!conv || conv.messages.length === 0) && (
            <div className="stack" style={{ maxWidth: 560, margin: 'auto', textAlign: 'center' }}>
              <h2>What's on your mind?</h2>
              <p className="muted small">
                You can talk about exams, stress, sleep, feeling lonely, or anything else. I'm an AI — I can listen, help
                you reflect and suggest small steps, but I'm not a counsellor and can't diagnose anything.
              </p>
              <div className="chips" style={{ justifyContent: 'center' }}>
                {["I'm stressed about exams", "I can't sleep well lately", 'I feel a bit lonely', 'Help me plan my week'].map((s) => (
                  <button key={s} className="chip" onClick={() => setText(s)}>{s}</button>
                ))}
              </div>
            </div>
          )}
          {conv?.messages.map((m) => <Bubble key={m.id} m={m} />)}
          {sending && (
            <div className="bubble-row assistant">
              <div className="typing" aria-label="MindWell is replying"><span /><span /><span /></div>
            </div>
          )}
          {safety?.show_support && (
            <div className="crisis-banner stack-sm" role="region" aria-label="Support options">
              <h3 style={{ margin: 0 }}>Support is available right now</h3>
              <p className="small" style={{ margin: 0 }}>
                {safety.level === 'crisis'
                  ? 'Please reach out to a person you trust or a trained counsellor now. MindWell has not contacted anyone.'
                  : "If things feel like too much, talking to a person can really help. You can keep chatting too."}
              </p>
              <div className="support-actions">
                <button className="support-action urgent" onClick={() => openSupport({ urgent: safety.level === 'crisis' })}>
                  <span className="sa-icon"><Icon name="phone" /></span>
                  <span>
                    <strong>{safety.has_emergency_contact ? 'Call or message my trusted contact' : 'See all support options'}</strong>
                    <span className="sub">Opens your support options</span>
                  </span>
                </button>
                <HelplineActions />
              </div>
            </div>
          )}
        </div>

        {sendError && (
          <div style={{ padding: '0 12px 8px' }}>
            {sendError.code === 'ai_consent_required' ? (
              <Alert kind="info">
                {sendError.message}{' '}
                <button className="btn btn-primary btn-sm" onClick={enableAI}>Allow AI processing</button>
              </Alert>
            ) : (
              <Alert kind="error">
                <strong>No reply was generated.</strong> {sendError.message} Your message wasn't saved — it's back in the box
                so you can try again.{' '}
                <button className="btn btn-secondary btn-sm" onClick={send} disabled={sending}>Retry</button>
              </Alert>
            )}
          </div>
        )}
        {!aiAllowed && !sendError && (
          <div style={{ padding: '0 12px 8px' }}>
            <Alert kind="info">
              AI processing is off, so the companion can't reply. Help options above still work.{' '}
              <button className="btn btn-primary btn-sm" onClick={enableAI}>Allow AI processing</button>
            </Alert>
          </div>
        )}

        <form className="chat-input" onSubmit={send}>
          <label htmlFor="chat-text" className="sr-only">Message MindWell</label>
          <textarea
            id="chat-text"
            className="textarea"
            rows={1}
            maxLength={2000}
            placeholder="Type how you're feeling…"
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) send(e);
            }}
          />
          <button className="btn btn-primary" style={{ width: 46, height: 46, padding: 0 }} aria-label="Send message"
            disabled={sending || !text.trim()}>
            <Icon name="send" />
          </button>
        </form>
      </section>
    </div>
  );
}
