import { Link, Navigate } from 'react-router-dom';
import Icon from '../components/Icon';
import { HelplineActions } from '../components/SupportPanel';
import { useAuth } from '../lib/auth';
import { HELPLINE, SUPPORT } from '../lib/support';

const FEATURES = [
  { icon: 'chat', title: 'Talk it through', text: 'An AI companion for reflecting on stress, exams, sleep or loneliness — clearly an AI, never a therapist.' },
  { icon: 'chart', title: 'Notice patterns', text: 'Quick daily check-ins turn into simple, transparent wellness indicators that only you can see.' },
  { icon: 'bolt', title: 'Small, doable steps', text: 'Guided breathing, journaling and short breaks. Earn XP and badges — never penalties for taking a break.' },
  { icon: 'lifebuoy', title: 'Help in one tap', text: `Call your trusted contact or ${HELPLINE.name} (${HELPLINE.short_code}) from any screen.` },
];

export default function Landing() {
  const { user, loading } = useAuth();
  if (!loading && user) return <Navigate to={user.role === 'teacher' ? '/teacher' : '/app'} replace />;
  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="topbar-inner">
          <Link to="/" className="brand">
            <span className="brand-mark"><Icon name="heart" size={18} /></span>
            MindWell
          </Link>
          <div className="topbar-actions">
            <Link className="btn btn-ghost btn-sm" to="/login">Sign in</Link>
            <Link className="btn btn-primary btn-sm" to="/register">Create account</Link>
          </div>
        </div>
      </header>
      <main className="main" id="main">
        <section className="hero">
          <div>
            <span className="badge">For students</span>
            <h1 style={{ marginTop: 12 }}>A private space to check in with yourself between classes.</h1>
            <p className="lead">
              MindWell combines an AI wellbeing companion, simple self check-ins and short guided activities — with
              support options always one tap away.
            </p>
            <div className="row" style={{ marginTop: 18 }}>
              <Link className="btn btn-primary btn-lg" to="/register">Get started</Link>
              <Link className="btn btn-secondary btn-lg" to="/login">I have an account</Link>
            </div>
            <p className="small muted" style={{ marginTop: 14 }}>
              Teacher? <Link to="/teacher/login">Sign in to the teacher dashboard</Link> — class-level, anonymous
              statistics only.
            </p>
          </div>
          <div className="card">
            <h2 id="help-now">Need to talk to someone right now?</h2>
            <p className="small muted">No account needed.</p>
            <div className="support-actions">
              <HelplineActions />
            </div>
            <p className="tiny muted" style={{ marginTop: 10, marginBottom: 0 }}>{SUPPORT.affiliation_disclaimer}</p>
          </div>
        </section>
        <section className="grid grid-4" aria-label="Features">
          {FEATURES.map((f) => (
            <div className="card" key={f.title}>
              <div className="feature-icon"><Icon name={f.icon} /></div>
              <h3>{f.title}</h3>
              <p className="small muted" style={{ margin: 0 }}>{f.text}</p>
            </div>
          ))}
        </section>
        <div className="alert alert-info" style={{ marginTop: 24 }}>
          <Icon name="info" />
          <div>
            MindWell is a wellbeing companion and student project, <strong>not</strong> a substitute for professional
            care, diagnosis or emergency services. Conversations with the AI are processed by Google's Gemini service.
          </div>
        </div>
      </main>
    </div>
  );
}
