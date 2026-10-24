import { Link } from 'react-router-dom';
import Icon from './Icon';
import { ProgressBar } from './ui';

export const INDICATORS = [
  { key: 'mood_level', label: 'Mood', higherIsBetter: true },
  { key: 'stress_level', label: 'Stress', higherIsBetter: false },
  { key: 'anxiety_level', label: 'Worry', higherIsBetter: false },
  { key: 'sleep_score', label: 'Sleep', higherIsBetter: true },
  { key: 'academic_pressure_level', label: 'Academic pressure', higherIsBetter: false },
];

export const CATEGORY_LABELS = {
  breathing: 'Breathing', mindfulness: 'Mindfulness', journaling: 'Journaling', gratitude: 'Gratitude',
  movement: 'Movement', study_break: 'Study break', relaxation: 'Relaxation', sleep: 'Sleep', time_management: 'Planning',
};

export function WellnessRing({ value, caption }) {
  const r = 58;
  const c = 2 * Math.PI * r;
  const has = value !== null && value !== undefined;
  return (
    <div className="ring-wrap">
      <svg width="150" height="150" viewBox="0 0 150 150" style={{ transform: 'rotate(-90deg)' }} aria-hidden="true">
        <circle cx="75" cy="75" r={r} fill="none" stroke="var(--border)" strokeWidth="11" />
        {has && (
          <circle cx="75" cy="75" r={r} fill="none" stroke="var(--teal-700)" strokeWidth="11" strokeLinecap="round"
            strokeDasharray={c} strokeDashoffset={c * (1 - value / 100)} />
        )}
      </svg>
      <div className="center">
        <div style={{ fontSize: 34, fontWeight: 800, lineHeight: 1 }}>{has ? Math.round(value) : '—'}</div>
        <div className="tiny muted">{caption || (has ? 'out of 100' : 'not enough data')}</div>
      </div>
    </div>
  );
}

export function IndicatorBars({ values }) {
  return (
    <div className="stack-sm">
      {INDICATORS.map((ind) => {
        const v = values?.[ind.key];
        return (
          <div className="indicator" key={ind.key}>
            <div className="top">
              <span>
                {ind.label} <span className="tiny muted">({ind.higherIsBetter ? 'higher is better' : 'higher means more'})</span>
              </span>
              <span className="muted">{v == null ? 'no answer' : Math.round(v)}</span>
            </div>
            <ProgressBar value={v ?? 0} label={`${ind.label} ${v == null ? 'no answer' : Math.round(v)} out of 100`} />
          </div>
        );
      })}
    </div>
  );
}

export function ActivityCard({ activity, reason, status, source, onDismiss }) {
  const done = status === 'completed';
  return (
    <div className="card activity-card">
      <div className="row" style={{ alignItems: 'flex-start' }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <h3 style={{ marginBottom: 2 }}>{activity.title}</h3>
          <div className="meta">
            <span>{activity.duration_minutes} min</span>
            <span>·</span>
            <span>{CATEGORY_LABELS[activity.category] || activity.category}</span>
            <span>·</span>
            <span>+{activity.xp_reward} XP</span>
            {activity.source === 'ai' && <span className="badge badge-ai">AI-generated</span>}
          </div>
        </div>
        {done && <span className="badge"><Icon name="check" size={14} /> Done today</span>}
      </div>
      <p className="small" style={{ margin: 0 }}>{activity.description}</p>
      {reason && (
        <p className="tiny muted" style={{ margin: 0 }}>
          Why this: {reason} {source === 'rule' && '(from your check-in)'}{source === 'chat' && '(from chat)'}
        </p>
      )}
      <div className="row">
        <Link className={`btn ${done ? 'btn-secondary' : 'btn-primary'} btn-sm`} to={`/app/activities/${activity.id}`}>
          {done ? 'Do it again' : 'Start'}
        </Link>
        {onDismiss && status === 'suggested' && (
          <button className="btn btn-ghost btn-sm" onClick={onDismiss}>Not today</button>
        )}
      </div>
    </div>
  );
}
