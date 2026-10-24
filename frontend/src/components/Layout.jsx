import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../lib/auth';
import Icon from './Icon';
import { GetHelpButton } from './SupportPanel';

function Brand({ to }) {
  return (
    <Link to={to} className="brand" aria-label="MindWell home">
      <span className="brand-mark">
        <Icon name="heart" size={18} stroke={1.8} className="" />
      </span>
      MindWell
    </Link>
  );
}

const STUDENT_NAV = [
  { to: '/app', label: 'Home', icon: 'home', end: true },
  { to: '/app/chat', label: 'Chat', icon: 'chat' },
  { to: '/app/wellness', label: 'Wellness', icon: 'chart' },
  { to: '/app/activities', label: 'Activities', icon: 'bolt' },
  { to: '/app/support', label: 'Emergency', icon: 'lifebuoy' },
];

function UserMenu() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  return (
    <>
      {user?.is_demo && <span className="badge badge-demo">DEMO<span className="hide-xs"> account</span></span>}
      <span className="small muted user-name">{user?.display_name}</span>
      {user?.role === 'student' && (
        <NavLink to="/app/settings" className="icon-btn" aria-label="Settings" style={{ color: 'inherit' }}>
          <Icon name="settings" />
        </NavLink>
      )}
      <button
        className="icon-btn"
        aria-label="Sign out"
        title="Sign out"
        onClick={async () => {
          await logout();
          navigate('/');
        }}
      >
        <Icon name="logout" />
      </button>
    </>
  );
}

export function StudentLayout() {
  return (
    <div className="app-shell">
      <a href="#main" className="skip-link">Skip to content</a>
      <header className="topbar">
        <div className="topbar-inner">
          <Brand to="/app" />
          <nav className="nav" aria-label="Main">
            {STUDENT_NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.end}>
                <Icon name={n.icon} size={17} />
                {n.label}
              </NavLink>
            ))}
          </nav>
          <div className="topbar-actions">
            <GetHelpButton />
            <UserMenu />
          </div>
        </div>
      </header>
      <main id="main" className="main">
        <Outlet />
      </main>
      <nav className="bottom-nav" aria-label="Main">
        {STUDENT_NAV.map((n) => (
          <NavLink key={n.to} to={n.to} end={n.end}>
            <Icon name={n.icon} size={21} />
            {n.label}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}

export function TeacherLayout() {
  return (
    <div className="app-shell">
      <a href="#main" className="skip-link">Skip to content</a>
      <header className="topbar">
        <div className="topbar-inner">
          <Brand to="/teacher" />
          <span className="badge">Teacher</span>
          <div className="topbar-actions">
            <UserMenu />
          </div>
        </div>
      </header>
      <main id="main" className="main" style={{ paddingBottom: 40 }}>
        <Outlet />
      </main>
    </div>
  );
}
