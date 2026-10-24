import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import Icon from '../components/Icon';
import { GetHelpButton } from '../components/SupportPanel';
import { Alert, Field } from '../components/ui';
import { useAuth } from '../lib/auth';

export default function Login({ teacher = false }) {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const user = await login(email, password, teacher ? 'teacher' : 'student');
      const next = params.get('next');
      const home = user.role === 'teacher' ? '/teacher' : '/app';
      navigate(next && next.startsWith(home) ? next : home, { replace: true });
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="main" id="main">
      <div className="auth-wrap">
        <Link to="/" className="brand" style={{ marginBottom: 20 }}>
          <span className="brand-mark"><Icon name="heart" size={18} /></span>
          MindWell
        </Link>
        <div className="card">
          <h1>{teacher ? 'Teacher sign in' : 'Welcome back'}</h1>
          <p className="muted small">
            {teacher
              ? 'Teacher accounts are created by your administrator.'
              : 'Sign in to continue to your private space.'}
          </p>
          <form className="stack" onSubmit={submit} noValidate>
            {error && <Alert kind="error">{error.message}</Alert>}
            <Field id="email" label="Email">
              <input id="email" className="input" type="email" autoComplete="email" required value={email}
                onChange={(e) => setEmail(e.target.value)} />
            </Field>
            <Field id="password" label="Password">
              <input id="password" className="input" type="password" autoComplete="current-password" required
                value={password} onChange={(e) => setPassword(e.target.value)} />
            </Field>
            <button className="btn btn-primary btn-block" disabled={busy || !email || !password}>
              {busy ? 'Signing in…' : 'Sign in'}
            </button>
          </form>
          <p className="small" style={{ marginTop: 16, marginBottom: 0 }}>
            {teacher ? (
              <Link to="/login">Student sign in</Link>
            ) : (
              <>New here? <Link to="/register">Create a student account</Link> · <Link to="/teacher/login">Teacher sign in</Link></>
            )}
          </p>
        </div>
        <div className="row" style={{ justifyContent: 'center', marginTop: 16 }}>
          <GetHelpButton label="Need help right now?" />
        </div>
      </div>
    </main>
  );
}
