import Icon from '../../components/Icon';
import { ErrorState, Loading, ProgressBar } from '../../components/ui';
import { formatDateTime, useApi } from '../../lib/hooks';

export default function Progress() {
  const { data, error, loading, reload } = useApi('/api/progress');
  if (loading) return <Loading />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  const s = data.summary;
  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h1>Your progress</h1>
          <p>XP, levels and badges are calculated by MindWell from completed check-ins and activities.</p>
        </div>
      </div>
      <div className="grid grid-4">
        <div className="card stat"><span className="v">{s.level}</span><span className="l">Level</span></div>
        <div className="card stat"><span className="v">{s.total_xp}</span><span className="l">Total XP</span></div>
        <div className="card stat"><span className="v">{s.current_streak}</span><span className="l">Current streak (days)</span></div>
        <div className="card stat"><span className="v">{s.longest_streak}</span><span className="l">Longest streak (days)</span></div>
      </div>
      <section className="card dark">
        <div className="row small" style={{ justifyContent: 'space-between', marginBottom: 8 }}>
          <strong>Level {s.level} → {s.level + 1}</strong>
          <span>{s.total_xp - s.level_floor_xp} / {s.next_level_xp - s.level_floor_xp} XP</span>
        </div>
        <ProgressBar value={s.progress_pct} label="Progress to next level" />
      </section>

      <section className="card" aria-labelledby="badges-h">
        <h2 id="badges-h">Badges</h2>
        <div className="badge-grid">
          {data.badges.map((b) => (
            <div key={b.code} className={`badge-tile ${b.earned ? '' : 'locked'}`}>
              <div className="medal"><Icon name={b.earned ? b.icon : 'lock'} size={24} /></div>
              <div className="n">{b.name}</div>
              <div className="d">{b.description}</div>
              <div className="d" style={{ marginTop: 4 }}>{b.earned ? `Earned ${formatDateTime(b.earned_at)}` : 'Not yet'}</div>
            </div>
          ))}
        </div>
      </section>

      <div className="grid grid-2">
        <section className="card" aria-labelledby="xp-h">
          <h2 id="xp-h">XP history</h2>
          {!data.xp_history.length && <p className="small muted">No XP yet — a check-in or activity earns your first.</p>}
          <ul className="list">
            {data.xp_history.map((x, i) => (
              <li key={i}>
                <strong style={{ color: 'var(--teal-700)', minWidth: 52 }}>+{x.amount}</strong>
                <span className="small" style={{ flex: 1 }}>{x.reason}</span>
                <span className="tiny muted">{formatDateTime(x.at)}</span>
              </li>
            ))}
          </ul>
        </section>
        <section className="card" aria-labelledby="rules-h">
          <h2 id="rules-h">How it works</h2>
          <ul className="small" style={{ paddingLeft: 18, margin: 0 }}>
            <li>A daily check-in earns {data.rules.checkin_xp} XP (once per day).</li>
            <li>Each activity shows its XP. You can earn XP for the same activity up to {data.rules.daily_xp_cap} times a day.</li>
            <li>{data.rules.level_formula}.</li>
            <li>{data.rules.streak}</li>
            <li>Sharing feelings in chat never affects XP — you're never rewarded or penalised for what you disclose.</li>
          </ul>
        </section>
      </div>
    </div>
  );
}
