import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import Icon from '../components/Icon';
import { GetHelpButton } from '../components/SupportPanel';
import { Alert, Field } from '../components/ui';
import { useAuth } from '../lib/auth';

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ display_name: '', email: '', password: '', accept_terms: false, ai_processing_consent: false });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }));
  const fieldError = (k) => (error?.details?.[k] ? error.message : null);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await register(form);
      navigate('/app', { replace: true });
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="main" id="main">
      <div className="auth-wrap" style={{ maxWidth: 560 }}>
        <Link to="/" className="brand" style={{ marginBottom: 20 }}>
          <span className="brand-mark"><Icon name="heart" size={18} /></span>
          MindWell
        </Link>
        <div className="card">
          <h1>Create your student account</h1>
          <form className="stack" onSubmit={submit} noValidate>
            {error && !Object.keys(error.details || {}).length && <Alert kind="error">{error.message}</Alert>}
            <Field id="name" label="What should we call you?" hint="A first name or nickname is fine." error={fieldError('display_name')}>
              <input id="name" className="input" autoComplete="nickname" value={form.display_name} onChange={set('display_name')} required />
            </Field>
            <Field id="email" label="Email" error={fieldError('email')}>
              <input id="email" className="input" type="email" autoComplete="email" value={form.email} onChange={set('email')}
                aria-invalid={!!fieldError('email')} required />
            </Field>
            <Field id="password" label="Password" hint="At least 10 characters, with a letter and a number." error={fieldError('password')}>
              <input id="password" className="input" type="password" autoComplete="new-password" value={form.password}
                onChange={set('password')} aria-invalid={!!fieldError('password')} required />
            </Field>

            <div className="card tinted stack-sm">
              <h3 style={{ margin: 0 }}>How MindWell handles your data</h3>
              <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>
                <li>Your chats, check-ins, journal and emergency contact are visible only to you.</li>
                <li>Teachers only ever see anonymous class averages — and only if you choose to share them, in groups of at least 5.</li>
                <li>If you allow AI processing, your chat messages are sent to Google's Gemini service to generate replies. Your name, email and contacts are not sent.</li>
                <li>You can delete conversations, memory, or your whole account at any time.</li>
                <li>MindWell is not a medical service and cannot guarantee it will recognise a crisis.</li>
              </ul>
            </div>
            <label className="check">
              <input type="checkbox" checked={form.accept_terms} onChange={set('accept_terms')} />
              <span>I have read how MindWell handles my data and understand it is not a substitute for professional care. <em>(required)</em></span>
            </label>
            {fieldError('accept_terms') && <span className="field-error small">{error.message}</span>}
            <label className="check">
              <input type="checkbox" checked={form.ai_processing_consent} onChange={set('ai_processing_consent')} />
              <span>Allow my chat messages to be processed by the AI (Google Gemini) so I can use the chatbot. <em>(optional — you can change this later)</em></span>
            </label>
            <button className="btn btn-primary btn-block" disabled={busy}>
              {busy ? 'Creating account…' : 'Create account'}
            </button>
          </form>
          <p className="small" style={{ marginTop: 16, marginBottom: 0 }}>
            Already registered? <Link to="/login">Sign in</Link>
          </p>
        </div>
        <div className="row" style={{ justifyContent: 'center', marginTop: 16 }}>
          <GetHelpButton label="Need help right now?" />
        </div>
      </div>
    </main>
  );
}
