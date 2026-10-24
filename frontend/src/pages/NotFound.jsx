import { Link } from 'react-router-dom';

export default function NotFound() {
  return (
    <main className="main" id="main">
      <div className="auth-wrap card">
        <h1>Page not found</h1>
        <p className="muted">That page doesn't exist or you don't have access to it.</p>
        <Link className="btn btn-primary" to="/">Go home</Link>
      </div>
    </main>
  );
}
