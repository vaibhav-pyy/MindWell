import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, newRequestId } from '../lib/api';
import { useAuth } from '../lib/auth';
import { EMERGENCY, HELPLINE, SUPPORT, telHref } from '../lib/support';
import Icon from './Icon';
import { Alert, Modal, Spinner } from './ui';

const SupportContext = createContext({ openSupport: () => {} });

export function useSupport() {
  return useContext(SupportContext);
}

export function SupportProvider({ children }) {
  const [state, setState] = useState({ open: false, urgent: false });
  const openSupport = useCallback((opts = {}) => setState({ open: true, urgent: !!opts.urgent }), []);
  const close = useCallback(() => setState((s) => ({ ...s, open: false })), []);
  return (
    <SupportContext.Provider value={{ openSupport }}>
      {children}
      <Modal open={state.open} onClose={close} title={state.urgent ? "You don't have to face this alone" : 'Get support now'} labelledBy="support-title">
        <SupportContent urgent={state.urgent} onClose={close} />
      </Modal>
    </SupportContext.Provider>
  );
}

export function HelplineActions() {
  const short = telHref(HELPLINE.short_code_tel);
  const tollFree = telHref(HELPLINE.toll_free_tel);
  return (
    <>
      <a className="support-action" href={short}>
        <span className="sa-icon"><Icon name="phone" /></span>
        <span>
          <strong>Call {HELPLINE.name}: {HELPLINE.short_code}</strong>
          <span className="sub">Free, confidential, {HELPLINE.hours} · {HELPLINE.languages}</span>
        </span>
      </a>
      <a className="support-action" href={tollFree}>
        <span className="sa-icon"><Icon name="phone" /></span>
        <span>
          <strong>Or call toll-free {HELPLINE.toll_free}</strong>
          <span className="sub">Same {HELPLINE.name} service</span>
        </span>
      </a>
      <a className="support-action urgent" href={telHref(EMERGENCY.tel)}>
        <span className="sa-icon"><Icon name="alert" /></span>
        <span>
          <strong>In immediate danger? Call {EMERGENCY.number}</strong>
          <span className="sub">{EMERGENCY.description}</span>
        </span>
      </a>
    </>
  );
}

function SupportContent({ urgent, onClose }) {
  const { user } = useAuth();
  const isStudent = user?.role === 'student';
  const [info, setInfo] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [step, setStep] = useState('menu'); // menu | preview | result

  useEffect(() => {
    if (!isStudent) return;
    api.get('/api/emergency').then(setInfo).catch(setLoadError);
  }, [isStudent]);

  const contact = info?.contact;
  const alertsEnabled = info?.preferences?.alerts_enabled && contact && contact.preferred_method !== 'call_only';

  if (step === 'preview' || step === 'result') {
    return <AlertFlow contact={contact} onBack={() => setStep('menu')} onClose={onClose} />;
  }

  return (
    <div className="stack">
      {urgent && (
        <div className="crisis-banner">
          <p style={{ margin: 0 }}>
            What you shared sounds really hard. Please reach out to a real person now — someone you trust, or a trained
            counsellor. You can use the options below; MindWell itself cannot call or check on you.
          </p>
        </div>
      )}
      <div className="support-actions">
        {isStudent && !info && !loadError && (
          <div className="row muted small"><Spinner /> Loading your trusted contact…</div>
        )}
        {isStudent && contact && (
          <a className="support-action urgent" href={contact.tel_href}>
            <span className="sa-icon"><Icon name="phone" /></span>
            <span>
              <strong>Call {contact.name}</strong>
              <span className="sub">{contact.relationship} · {contact.phone}</span>
            </span>
          </a>
        )}
        {isStudent && contact && alertsEnabled && (
          <button className="support-action" onClick={() => setStep('preview')}>
            <span className="sa-icon"><Icon name="mail" /></span>
            <span>
              <strong>Send {contact.name} a support message</strong>
              <span className="sub">You'll see exactly what will be sent before anything goes out</span>
            </span>
          </button>
        )}
        <HelplineActions />
      </div>

      {isStudent && info && !contact && (
        <Alert kind="info">
          You haven't added a trusted contact yet.{' '}
          <Link to="/app/support" onClick={onClose}>Add one in Emergency settings</Link> so you can reach them in one tap.
        </Alert>
      )}
      {loadError && <Alert kind="warn">Your saved contact couldn't be loaded right now — the helplines above still work.</Alert>}

      <p className="tiny muted" style={{ margin: 0 }}>
        Call buttons open your device's phone app. On a computer without calling set up, nothing may happen — dial the
        number directly instead. Tapping a button does not mean a call was connected. {SUPPORT.affiliation_disclaimer}
      </p>
      <div className="row">
        {isStudent && (
          <Link className="btn btn-ghost btn-sm" to="/app/chat" onClick={onClose}>Back to chat</Link>
        )}
        <button className="btn btn-secondary btn-sm" onClick={onClose}>Close</button>
      </div>
    </div>
  );
}

export function AlertFlow({ contact, onBack, onClose }) {
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState(null);
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState(null);
  const requestId = useRef(newRequestId());

  useEffect(() => {
    api.get('/api/emergency/alert-preview').then(setPreview).catch(setError);
  }, []);

  async function send() {
    setSending(true);
    setError(null);
    try {
      // Same request id on retry => the server never sends a duplicate.
      const data = await api.post('/api/emergency/alerts', { client_request_id: requestId.current, confirm: true });
      setResult(data.alert);
    } catch (err) {
      setError(err);
    } finally {
      setSending(false);
    }
  }

  if (result) {
    const good = result.status === 'accepted_by_provider';
    return (
      <div className="stack">
        <Alert kind={good ? 'success' : 'warn'}>
          <strong>{good ? 'Message handed to provider.' : 'Message NOT sent.'}</strong> {result.status_text}
        </Alert>
        <div className="support-actions">
          {contact && (
            <a className="support-action urgent" href={contact.tel_href}>
              <span className="sa-icon"><Icon name="phone" /></span>
              <span><strong>Call {contact.name}</strong><span className="sub">{contact.phone}</span></span>
            </a>
          )}
          <HelplineActions />
        </div>
        <div className="row">
          {onBack && <button className="btn btn-ghost btn-sm" onClick={onBack}>Back</button>}
          {onClose && <button className="btn btn-secondary btn-sm" onClick={onClose}>Close</button>}
        </div>
      </div>
    );
  }

  return (
    <div className="stack">
      {!preview && !error && <div className="row muted"><Spinner /> Preparing preview…</div>}
      {error && <Alert kind="error">{error.message}</Alert>}
      {preview && (
        <>
          <p style={{ margin: 0 }}>
            This is exactly what will be sent to <strong>{preview.contact_name}</strong> by <strong>{preview.channel}</strong>{' '}
            ({preview.destination}):
          </p>
          <pre className="card tinted small" style={{ whiteSpace: 'pre-wrap', fontFamily: 'inherit', margin: 0 }}>{preview.message}</pre>
          {!preview.provider_configured && (
            <Alert kind="warn">
              <strong>No {preview.channel} provider is configured on this server</strong>, so this message will not be
              delivered{preview.dev_outbox ? ' (it will only be written to a local development file)' : ''}. Please call
              your contact or a helpline instead.
            </Alert>
          )}
          <div className="row">
            <button className="btn btn-primary" onClick={send} disabled={sending}>
              {sending ? 'Sending…' : 'Yes, send this message'}
            </button>
            {onBack && <button className="btn btn-ghost" onClick={onBack} disabled={sending}>Cancel</button>}
          </div>
        </>
      )}
    </div>
  );
}

export function GetHelpButton({ className = 'btn btn-help btn-sm', label }) {
  const { openSupport } = useSupport();
  return (
    <button className={className} onClick={() => openSupport()}>
      <Icon name="lifebuoy" size={18} />
      {label || <>Get help<span className="hide-xs"> now</span></>}
    </button>
  );
}
