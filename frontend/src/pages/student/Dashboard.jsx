import { Link } from 'react-router-dom';
import Icon from '../../components/Icon';
import { GetHelpButton } from '../../components/SupportPanel';
import { Empty, ErrorState, Loading, ProgressBar, useToast } from '../../components/ui';
import { ActivityCard, IndicatorBars, WellnessRing } from '../../components/WellnessBits';
import { api } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { formatDateTime, useApi } from '../../lib/hooks';

function greeting() {
  const h = new Date().getHours();
  if (h < 12) return 'Good morning';
  if (h < 17) return 'Good afternoon';
  return 'Good evening';
}

export default function Dashboard() {
  const { user } = useAuth();
  const toast = useToast();
  const wellness = useApi('/api/wellness/summary');
  const progress = useApi('/api/progress');
  const recs = useApi('/api/recommendations/today');
  const emergency = useApi('/api/emergency');

  async function dismiss(id) {
    try {
      await api.post(`/api/recommendations/${id}/dismiss`);
      recs.setData((list) => list.map((r) => (r.id === id ? { ...r, status: 'dismissed' } : r)));
      toast('No problem — skipped for today.');
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  const w = wellness.data;
  const p = progress.data;
  const latestIndex = w?.last_7_days?.averages?.wellness_index;
  const visibleRecs = (recs.data || []).filter((r) => r.status !== 'dismissed');
  const earned = (p?.badges || []).filter((b) => b.earned);

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h1>{greeting()}, {user.display_name}</h1>
          <p>Here's your space for today. Everything here is private to you.</p>
        </div>
        <div className="row">
          <Link className="btn btn-primary" to="/app/chat"><Icon name="chat" size={18} /> Talk to MindWell</Link>
        </div>
      </div>

      {w && !w.checked_in_today && (
        <div className="card tinted row" style={{ justifyContent: 'space-between' }}>
          <div>
            <h3 style={{ margin: 0 }}>How are you today?</h3>
            <p className="small muted" style={{ margin: 0 }}>A 1-minute check-in updates your wellness indicators. Skip any question you like.</p>
          </div>
          <Link className="btn btn-primary btn-sm" to="/app/checkin">Check in</Link>
        </div>
      )}

      <div className="dash-grid">
        <div className="stack">
          <section className="card" aria-labelledby="wellness-h">
            <div className="card-header">
              <h2 id="wellness-h">Wellness overview</h2>
              <span className="badge badge-self">Self-reported</span>
            </div>
            {wellness.loading && <Loading />}
            {wellness.error && <ErrorState error={wellness.error} onRetry={wellness.reload} />}
            {w && (w.latest ? (
              <div className="row" style={{ alignItems: 'flex-start', gap: 24 }}>
                <div style={{ textAlign: 'center' }}>
                  <WellnessRing value={latestIndex} />
                  <div className="tiny muted" style={{ maxWidth: 150 }}>
                    7-day wellness index · {w.last_7_days.checkins} check-in{w.last_7_days.checkins === 1 ? '' : 's'}
                  </div>
                </div>
                <div style={{ flex: 1, minWidth: 220 }}>
                  <IndicatorBars values={w.last_7_days.averages} />
                  <Link to="/app/wellness" className="small" style={{ display: 'inline-block', marginTop: 10 }}>
                    See trends & how this is calculated →
                  </Link>
                </div>
              </div>
            ) : (
              <Empty title="No check-ins yet" icon="chart">
                <p className="small">Your indicators come only from what you tell us in check-ins.</p>
                <Link className="btn btn-primary btn-sm" to="/app/checkin">Do your first check-in</Link>
              </Empty>
            ))}
            {w && <p className="tiny muted" style={{ margin: '12px 0 0' }}>{w.disclaimer}</p>}
          </section>

          <section aria-labelledby="today-h">
            <div className="card-header">
              <h2 id="today-h">Today's suggested activities</h2>
              <Link to="/app/activities" className="small">All activities</Link>
            </div>
            {recs.loading && <Loading />}
            {recs.error && <ErrorState error={recs.error} onRetry={recs.reload} />}
            {recs.data && !visibleRecs.length && (
              <div className="card"><Empty title="Nothing suggested right now">
                <p className="small">You've cleared today's list. Browse the full list any time — or just rest.</p>
              </Empty></div>
            )}
            <div className="grid grid-2">
              {visibleRecs.map((r) => (
                <ActivityCard key={r.id} activity={r.activity} reason={r.reason} status={r.status} source={r.source}
                  onDismiss={() => dismiss(r.id)} />
              ))}
            </div>
          </section>
        </div>

        <div className="stack">
          <section className="card dark" aria-labelledby="xp-h">
            {progress.error && <ErrorState error={progress.error} onRetry={progress.reload} />}
            {!p && !progress.error && <Loading />}
            {p && (
              <div className="stack-sm">
                <div className="row" style={{ justifyContent: 'space-between' }}>
                  <h2 id="xp-h" style={{ margin: 0 }}>Level {p.summary.level}</h2>
                  <span className="row" style={{ gap: 6, color: 'var(--amber)', fontWeight: 700 }}>
                    <Icon name="flame" size={18} />
                    {p.summary.current_streak}-day streak
                  </span>
                </div>
                <div className="row small" style={{ justifyContent: 'space-between', opacity: 0.9 }}>
                  <span>{p.summary.total_xp} XP</span>
                  <span>{p.summary.next_level_xp} XP for level {p.summary.level + 1}</span>
                </div>
                <ProgressBar value={p.summary.progress_pct} label="Progress to next level" />
                <Link to="/app/progress" className="btn btn-light btn-sm" style={{ alignSelf: 'flex-start', marginTop: 6 }}>
                  Badges & history
                </Link>
              </div>
            )}
          </section>

          <section className="card" aria-labelledby="support-h">
            <div className="card-header">
              <h2 id="support-h">Support</h2>
            </div>
            {emergency.data?.contact ? (
              <p className="small">Trusted contact: <strong>{emergency.data.contact.name}</strong> ({emergency.data.contact.relationship})</p>
            ) : (
              <p className="small muted">You haven't added a trusted contact yet.</p>
            )}
            <div className="row">
              <GetHelpButton className="btn btn-help" />
              <Link className="btn btn-ghost btn-sm" to="/app/support">Emergency settings</Link>
            </div>
          </section>

          <section className="card" aria-labelledby="badges-h">
            <div className="card-header">
              <h2 id="badges-h">Badges</h2>
              <Link to="/app/progress" className="small">View all</Link>
            </div>
            {p && !earned.length && <p className="small muted">Your first check-in or activity earns your first badge.</p>}
            <div className="chips">
              {earned.map((b) => (
                <span className="badge" key={b.code} title={b.description}><Icon name={b.icon} size={14} /> {b.name}</span>
              ))}
            </div>
          </section>

          <section className="card" aria-labelledby="recent-h">
            <h2 id="recent-h">Recent activity</h2>
            {p && !p.recent_completions.length && <p className="small muted">Completed activities will appear here.</p>}
            <ul className="list">
              {(p?.recent_completions || []).slice(0, 5).map((c, i) => (
                <li key={i}>
                  <Icon name="check" size={16} />
                  <span style={{ flex: 1 }} className="small">{c.title}</span>
                  <span className="tiny muted">{c.xp_awarded ? `+${c.xp_awarded} XP · ` : ''}{formatDateTime(c.at)}</span>
                </li>
              ))}
            </ul>
          </section>
        </div>
      </div>
    </div>
  );
}
