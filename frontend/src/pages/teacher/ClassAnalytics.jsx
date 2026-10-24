import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import Icon from '../../components/Icon';
import LineChart from '../../components/LineChart';
import { Alert, ErrorState, Loading, ProgressBar, useToast } from '../../components/ui';
import { CATEGORY_LABELS } from '../../components/WellnessBits';
import { api } from '../../lib/api';
import { formatDate, formatDateTime, useApi } from '../../lib/hooks';

const CHART_METRICS = ['wellness_index', 'stress_level', 'academic_pressure_level', 'sleep_score'];

function weekLabel(w) {
  return `Wk of ${formatDate(w.week_start)}`;
}

export default function ClassAnalytics() {
  const { classId } = useParams();
  const toast = useToast();
  const [weeks, setWeeks] = useState(4);
  const { data, error, loading, reload, setData } = useApi(`/api/teacher/classes/${classId}/analytics?weeks=${weeks}`);
  const [generating, setGenerating] = useState(false);

  async function generate() {
    setGenerating(true);
    try {
      const insight = await api.post(`/api/teacher/classes/${classId}/insights`, { weeks });
      setData((d) => ({ ...d, latest_ai_insight: insight }));
      if (insight.ai_status !== 'generated') toast('No AI narrative was generated — see the note below.', 'error');
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      setGenerating(false);
    }
  }

  if (loading && !data) return <Loading />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  const { statistics: s, observations, suggestions, latest_ai_insight: ai } = data;
  const visible = s.weeks.filter((w) => !w.suppressed);
  const latest = visible[visible.length - 1];
  const latestParticipation = s.weeks[s.weeks.length - 1]?.participation;

  return (
    <div className="stack">
      <Link to="/teacher" className="small row" style={{ gap: 4 }}><Icon name="arrowLeft" size={16} /> All classes</Link>
      <div className="page-header">
        <div>
          <h1>{s.class_name}</h1>
          <p>{s.member_count} members · {s.contributing_members ? `${s.contributing_members} sharing anonymous data` : `fewer than ${s.min_cohort_size} sharing anonymous data`}</p>
        </div>
        <div className="row">
          <label htmlFor="period" className="small">Period</label>
          <select id="period" className="select" style={{ width: 'auto' }} value={weeks} onChange={(e) => setWeeks(Number(e.target.value))}>
            {[4, 8, 12].map((n) => <option key={n} value={n}>Last {n} weeks</option>)}
          </select>
        </div>
      </div>

      <Alert kind="info" icon="lock">
        Aggregated, self-reported data only. Weeks with fewer than {s.min_cohort_size} contributing students are hidden.
        Figures are descriptive averages (0–100) and have not been tested for statistical significance.
      </Alert>

      {!s.sufficient_data ? (
        <div className="card">
          <h2>Not enough data to show class trends</h2>
          <p className="muted small">
            At least {s.min_cohort_size} students need to opt in to sharing anonymous numbers before anything is shown. Students
            can choose this when they join with the class code, or later in their settings.
          </p>
        </div>
      ) : (
        <>
          <div className="grid grid-4">
            {[['wellness_index', 'Avg wellness index'], ['stress_level', 'Avg stress level'], ['academic_pressure_level', 'Avg academic pressure']].map(([k, label]) => (
              <div className="card stat" key={k}>
                <span className="v">{latest?.metrics?.[k] ?? '—'}</span>
                <span className="l">{label}</span>
                <span className="tiny muted">{latest ? `${weekLabel(latest)} · ${latest.contributors} contributors` : 'No week above threshold'}</span>
              </div>
            ))}
            <div className="card stat">
              <span className="v">{latestParticipation?.participation_pct ?? '—'}%</span>
              <span className="l">Activity participation</span>
              <span className="tiny muted">This week · {latestParticipation?.completions ?? 0} completions</span>
            </div>
          </div>

          <div className="grid grid-2">
            {CHART_METRICS.map((k) => (
              <section className="card" key={k} aria-labelledby={`ch-${k}`}>
                <h3 id={`ch-${k}`}>{s.metric_labels[k]}</h3>
                <LineChart
                  title={`${s.metric_labels[k]} by week`}
                  valueLabel="Average"
                  points={s.weeks.map((w) => ({ x: w.week_start, y: w.suppressed ? null : w.metrics[k], label: formatDate(w.week_start) }))}
                  emptyText="All weeks in this period are below the privacy threshold."
                />
              </section>
            ))}
            <section className="card" aria-labelledby="ch-part">
              <h3 id="ch-part">Activity participation (% of opted-in students)</h3>
              <LineChart title="Weekly activity participation" valueLabel="Participation %"
                points={s.weeks.map((w) => ({ x: w.week_start, y: w.participation.participation_pct, label: formatDate(w.week_start) }))} />
            </section>
            <section className="card" aria-labelledby="ch-str">
              <h3 id="ch-str">What's weighing on students {latest ? `(${weekLabel(latest)})` : ''}</h3>
              <p className="tiny muted">% of contributing students who selected each area in a check-in.</p>
              {!latest?.stressors_pct || !Object.keys(latest.stressors_pct).length ? (
                <p className="small muted">No data.</p>
              ) : (
                <div className="stack-sm">
                  {Object.entries(latest.stressors_pct).sort((a, b) => b[1] - a[1]).map(([code, pct]) => (
                    <div className="indicator" key={code}>
                      <div className="top"><span>{s.stressor_labels[code]}</span><span className="muted">{pct}%</span></div>
                      <ProgressBar value={pct} label={`${s.stressor_labels[code]} ${pct}%`} />
                    </div>
                  ))}
                </div>
              )}
              {latestParticipation?.by_category && (
                <>
                  <h3 style={{ marginTop: 16 }}>Activities completed this week</h3>
                  <ul className="list small">
                    {Object.entries(latestParticipation.by_category).map(([cat, n]) => (
                      <li key={cat}><span style={{ flex: 1 }}>{CATEGORY_LABELS[cat] || cat}</span><strong>{n}</strong></li>
                    ))}
                  </ul>
                </>
              )}
            </section>
          </div>
        </>
      )}

      <div className="grid grid-2">
        <section className="card" aria-labelledby="obs-h">
          <div className="card-header">
            <h2 id="obs-h">Observations</h2>
            <span className="badge">Computed from recorded data</span>
          </div>
          <ul className="small" style={{ paddingLeft: 18, margin: 0 }}>
            {observations.map((o, i) => <li key={i} style={{ marginBottom: 6 }}>{o.text}</li>)}
          </ul>
          {suggestions.length > 0 && (
            <>
              <h3 style={{ marginTop: 14 }}>General suggestions</h3>
              <ul className="small" style={{ paddingLeft: 18, margin: 0 }}>
                {suggestions.map((t, i) => <li key={i}>{t}</li>)}
              </ul>
            </>
          )}
        </section>

        <section className="card" aria-labelledby="ai-h">
          <div className="card-header">
            <h2 id="ai-h">AI insight</h2>
            <span className="badge badge-ai">AI-generated interpretation</span>
          </div>
          <p className="tiny muted">
            Gemini receives only the anonymous weekly averages shown on this page — no student identities or messages. Its
            output is checked for diagnostic or surveillance language before display. Treat it as a discussion aid.
          </p>
          {ai?.ai_narrative ? (
            <div className="stack-sm small">
              <strong>Observations</strong>
              <ul style={{ paddingLeft: 18, margin: 0 }}>{ai.ai_narrative.observations.map((o, i) => <li key={i}>{o.text}</li>)}</ul>
              <strong>Suggestions</strong>
              <ul style={{ paddingLeft: 18, margin: 0 }}>{ai.ai_narrative.suggestions.map((o, i) => <li key={i}>{o}</li>)}</ul>
              <strong>Caveats</strong>
              <ul style={{ paddingLeft: 18, margin: 0 }}>{ai.ai_narrative.caveats.map((o, i) => <li key={i}>{o}</li>)}</ul>
              <span className="tiny muted">Generated {formatDateTime(ai.created_at)} for the last {ai.period_weeks} weeks.</span>
            </div>
          ) : ai ? (
            <Alert kind="warn">
              {ai.ai_status === 'skipped_insufficient_data'
                ? 'There was not enough aggregate data, so no AI insight was requested.'
                : `The AI insight could not be generated (${ai.ai_status.replace('ai_unavailable:', '')}). The observations on the left are still valid.`}
            </Alert>
          ) : (
            <p className="small muted">No AI insight generated for this period yet.</p>
          )}
          <button className="btn btn-secondary" style={{ marginTop: 12 }} onClick={generate} disabled={generating}>
            <Icon name="sparkle" size={16} /> {generating ? 'Generating…' : 'Generate AI insight'}
          </button>
        </section>
      </div>
    </div>
  );
}
