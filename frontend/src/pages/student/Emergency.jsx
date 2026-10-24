import { useEffect, useState } from 'react';
import Icon from '../../components/Icon';
import { AlertFlow, HelplineActions } from '../../components/SupportPanel';
import { Alert, ConfirmButton, ErrorState, Field, Loading, Modal, useToast } from '../../components/ui';
import { api } from '../../lib/api';
import { formatDateTime, useApi } from '../../lib/hooks';
import { HELPLINE, SUPPORT } from '../../lib/support';

const EMPTY_CONTACT = { name: '', relationship: '', phone: '', email: '', preferred_method: 'call_only', confirm: false };

function ContactForm({ contact, channels, onSaved }) {
  const toast = useToast();
  const [form, setForm] = useState(() => (contact ? { ...contact, email: contact.email || '', confirm: false } : EMPTY_CONTACT));
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }));
  const fe = (k) => (error?.details?.[k] ? error.message : null);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const saved = await api.put('/api/emergency/contact', form);
      toast('Trusted contact saved.');
      onSaved(saved);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="stack" onSubmit={submit} noValidate>
      {error && !fe('name') && !fe('phone') && !fe('email') && <Alert kind="error">{error.message}</Alert>}
      <div className="form-grid">
        <Field id="c-name" label="Contact name" error={fe('name')}>
          <input id="c-name" className="input" value={form.name} onChange={set('name')} maxLength={80} required />
        </Field>
        <Field id="c-rel" label="Relationship to you" hint="e.g. parent, sibling, friend, warden" error={fe('relationship')}>
          <input id="c-rel" className="input" value={form.relationship} onChange={set('relationship')} maxLength={40} required />
        </Field>
        <Field id="c-phone" label="Phone number" hint="Indian numbers can be entered without +91." error={fe('phone')}>
          <input id="c-phone" className="input" type="tel" inputMode="tel" autoComplete="off" value={form.phone}
            onChange={set('phone')} aria-invalid={!!fe('phone')} required />
        </Field>
        <Field id="c-email" label="Email (optional)" hint="Needed only for email alerts." error={fe('email')}>
          <input id="c-email" className="input" type="email" value={form.email} onChange={set('email')} aria-invalid={!!fe('email')} />
        </Field>
      </div>
      <Field id="c-method" label="If you ask MindWell to message them, use" error={fe('preferred_method')}>
        <select id="c-method" className="select" value={form.preferred_method} onChange={set('preferred_method')}>
          <option value="call_only">Don't message them — I'll only call</option>
          <option value="email">Email{channels.email ? '' : ' (not configured on this server)'}</option>
          <option value="sms">SMS{channels.sms ? '' : ' (not configured on this server)'}</option>
        </select>
      </Field>
      {form.preferred_method !== 'call_only' && !channels[form.preferred_method] && (
        <Alert kind="warn">
          This server has no {form.preferred_method === 'email' ? 'email' : 'SMS'} provider configured, so messages
          <strong> will not be delivered</strong> until an administrator sets one up. Calling will still work.
        </Alert>
      )}
      <label className="check">
        <input type="checkbox" checked={form.confirm} onChange={set('confirm')} />
        <span>This person has agreed to be my emergency contact, and I'm allowed to share their details here.</span>
      </label>
      <button className="btn btn-primary" disabled={busy || !form.confirm}>{busy ? 'Saving…' : 'Save contact'}</button>
    </form>
  );
}

function SharingForm({ prefs, contact, explanation, onSaved }) {
  const toast = useToast();
  const [form, setForm] = useState({ ...prefs, callback_phone: prefs.callback_phone || '', custom_note: prefs.custom_note || '', consent: false });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }));

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const saved = await api.put('/api/emergency/preferences', form);
      toast(saved.alerts_enabled ? 'Sharing preferences saved.' : 'Emergency messages are turned off.');
      onSaved(saved);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="stack" onSubmit={submit}>
      <div className="card tinted small stack-sm">
        <div><strong>What may be shared:</strong> {explanation.what}</div>
        <div><strong>With whom:</strong> {explanation.who}</div>
        <div><strong>How:</strong> {explanation.channel}</div>
        <div><strong>When:</strong> {explanation.when}</div>
        <div><strong>Limits:</strong> {explanation.limits}</div>
      </div>
      {error && <Alert kind="error">{error.message}</Alert>}
      <label className="check">
        <input type="checkbox" checked={form.alerts_enabled} onChange={set('alerts_enabled')} disabled={!contact} />
        <span><strong>Allow me to send emergency support messages to {contact?.name || 'my contact'}</strong></span>
      </label>
      {form.alerts_enabled && (
        <div className="stack" style={{ paddingLeft: 30 }}>
          <label className="check">
            <input type="checkbox" checked={form.share_name} onChange={set('share_name')} />
            <span>Include my name (otherwise the message says “a MindWell user who listed you as a trusted contact”)</span>
          </label>
          <label className="check">
            <input type="checkbox" checked={form.share_callback_phone} onChange={set('share_callback_phone')} />
            <span>Include a phone number they can call me back on</span>
          </label>
          {form.share_callback_phone && (
            <Field id="cb-phone" label="My callback number" error={error?.details?.callback_phone ? error.message : null}>
              <input id="cb-phone" className="input" type="tel" value={form.callback_phone} onChange={set('callback_phone')} />
            </Field>
          )}
          <label className="check">
            <input type="checkbox" checked={form.share_custom_note} onChange={set('share_custom_note')} />
            <span>Include a short note I write now</span>
          </label>
          {form.share_custom_note && (
            <Field id="cb-note" label="My note (max 200 characters)" hint="e.g. “I'm at my hostel, please call me.”">
              <textarea id="cb-note" className="textarea" style={{ minHeight: 70 }} maxLength={200} value={form.custom_note}
                onChange={set('custom_note')} />
            </Field>
          )}
          <label className="check">
            <input type="checkbox" checked={form.consent} onChange={set('consent')} />
            <span>I understand what will be shared, that messages are only sent when I press send and confirm, and that delivery can't be guaranteed.</span>
          </label>
        </div>
      )}
      <button className="btn btn-primary" disabled={busy || (form.alerts_enabled && !form.consent)}>{busy ? 'Saving…' : 'Save sharing preferences'}</button>
    </form>
  );
}

export default function Emergency() {
  const toast = useToast();
  const { data, setData, error, loading, reload } = useApi('/api/emergency');
  const alerts = useApi('/api/emergency/alerts');
  const [editing, setEditing] = useState(false);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    if (data && !data.contact) setEditing(true);
  }, [data]);

  if (loading) return <Loading />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  const { contact, preferences, channels_configured: channels, explanation } = data;
  const canMessage = contact && preferences.alerts_enabled && contact.preferred_method !== 'call_only';

  async function removeContact() {
    try {
      await api.del('/api/emergency/contact');
      toast('Contact removed.');
      reload();
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h1>Emergency support</h1>
          <p>Your trusted contact and helplines. This information is visible only to you — never to teachers.</p>
        </div>
      </div>

      <div className="grid grid-2">
        <section className="card stack" aria-labelledby="now-h">
          <h2 id="now-h">Reach someone now</h2>
          <div className="support-actions">
            {contact && (
              <a className="support-action urgent" href={contact.tel_href}>
                <span className="sa-icon"><Icon name="phone" /></span>
                <span><strong>Call {contact.name}</strong><span className="sub">{contact.relationship} · {contact.phone}</span></span>
              </a>
            )}
            {canMessage && (
              <button className="support-action" onClick={() => setSending(true)}>
                <span className="sa-icon"><Icon name="mail" /></span>
                <span><strong>Send {contact.name} a support message</strong><span className="sub">Preview first, then confirm</span></span>
              </button>
            )}
            <HelplineActions />
          </div>
          <p className="tiny muted" style={{ margin: 0 }}>
            Call buttons open your phone's dialer (tel: links). On a laptop or desktop they may do nothing unless calling is
            set up — dial the number directly instead. Pressing a button does not confirm a call was connected.
          </p>
        </section>

        <section className="card stack" aria-labelledby="tm-h">
          <h2 id="tm-h">About {HELPLINE.name}</h2>
          <p className="small" style={{ margin: 0 }}>
            <strong>{HELPLINE.full_name}</strong> — {HELPLINE.description} Run by the {HELPLINE.operator}.
          </p>
          <p className="small" style={{ margin: 0 }}>
            Call <strong>{HELPLINE.short_code}</strong> or <strong>{HELPLINE.toll_free}</strong>, {HELPLINE.hours}, in {HELPLINE.languages}.{' '}
            <a href={HELPLINE.website} target="_blank" rel="noreferrer">Official website</a>
          </p>
          <p className="tiny muted" style={{ margin: 0 }}>{SUPPORT.affiliation_disclaimer}</p>
        </section>
      </div>

      <section className="card" aria-labelledby="contact-h">
        <div className="card-header">
          <h2 id="contact-h">Your trusted contact</h2>
          {contact && !editing && (
            <div className="row">
              <button className="btn btn-secondary btn-sm" onClick={() => setEditing(true)}>Edit</button>
              <ConfirmButton confirmText="Remove contact?" onConfirm={removeContact}>Remove</ConfirmButton>
            </div>
          )}
        </div>
        {editing || !contact ? (
          <ContactForm contact={contact} channels={channels} onSaved={(c) => { setData({ ...data, contact: c }); setEditing(false); }} />
        ) : (
          <dl className="grid grid-2 small" style={{ margin: 0 }}>
            <div><dt className="muted">Name</dt><dd style={{ margin: 0 }}>{contact.name}</dd></div>
            <div><dt className="muted">Relationship</dt><dd style={{ margin: 0 }}>{contact.relationship}</dd></div>
            <div><dt className="muted">Phone</dt><dd style={{ margin: 0 }}>{contact.phone}</dd></div>
            <div><dt className="muted">Email</dt><dd style={{ margin: 0 }}>{contact.email || '—'}</dd></div>
            <div><dt className="muted">Message method</dt><dd style={{ margin: 0 }}>{{ call_only: 'Call only', email: 'Email', sms: 'SMS' }[contact.preferred_method]}</dd></div>
          </dl>
        )}
        {editing && contact && <button className="btn btn-ghost btn-sm" style={{ marginTop: 8 }} onClick={() => setEditing(false)}>Cancel</button>}
      </section>

      <section className="card" aria-labelledby="share-h">
        <h2 id="share-h">Emergency message sharing</h2>
        {!contact && <p className="small muted">Add a trusted contact first.</p>}
        {contact && (
          <SharingForm key={JSON.stringify(preferences)} prefs={preferences} contact={contact} explanation={explanation}
            onSaved={(p) => setData({ ...data, preferences: p })} />
        )}
        <p className="tiny muted" style={{ marginTop: 12 }}>
          Delivery providers on this server: email {channels.email ? 'configured' : 'not configured'}, SMS{' '}
          {channels.sms ? 'configured' : 'not configured'}{channels.dev_outbox ? ' (development outbox active — nothing is really sent)' : ''}.
        </p>
      </section>

      <section className="card" aria-labelledby="hist-h">
        <h2 id="hist-h">Messages you've sent</h2>
        {alerts.data?.length === 0 && <p className="small muted">None.</p>}
        <ul className="list">
          {(alerts.data || []).map((a) => (
            <li key={a.id} style={{ alignItems: 'flex-start' }}>
              <span className={`badge ${a.status === 'accepted_by_provider' ? '' : 'badge-warn'}`}>{a.status.replaceAll('_', ' ')}</span>
              <span className="small" style={{ flex: 1 }}>{a.channel} to {a.destination} — {a.status_text}</span>
              <span className="tiny muted">{formatDateTime(a.created_at)}</span>
            </li>
          ))}
        </ul>
      </section>

      <Modal open={sending} onClose={() => { setSending(false); alerts.reload(); }} title="Send a support message" labelledBy="send-alert">
        {sending && <AlertFlow contact={contact} onClose={() => { setSending(false); alerts.reload(); }} />}
      </Modal>
    </div>
  );
}
