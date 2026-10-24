import { useState } from 'react';
import { Link } from 'react-router-dom';
import Icon from '../../components/Icon';
import LineChart from '../../components/LineChart';
import { ConfirmButton, Empty, ErrorState, Loading, Modal, useToast } from '../../components/ui';
import { INDICATORS, IndicatorBars, WellnessRing } from '../../components/WellnessBits';
import { api } from '../../lib/api';
import { formatDate, useApi } from '../../lib/hooks';
import { CheckInForm, STRESSORS } from './CheckIn';

function TrendText({ trend, higherIsBetter }) {
  if (!trend) return <span className="tiny muted">Need 2+ check-ins in each of the last two weeks for a trend</span>;
  if (trend.direction === 'steady') return <span className="tiny muted">About the same as the week before</span>;
  const up = trend.direction === 'up';
  return (
    <span className="tiny muted">
      {up ? 'Up' : 'Down'} {Math.abs(trend.change)} vs the week before
      {higherIsBetter !== undefined && ` (${up === higherIsBetter ? 'higher is better' : 'higher means more'})`}
    </span>
  );
}

export default function Wellness() {
  const toast = useToast();
  const summary = useApi('/api/wellness/summary');
  const history = useApi('/api/checkins?days=60');
  const method = useApi('/api/wellness/methodology');
  const [metric, setMetric] = useState('wellness_index');
  const [editing, setEditing] = useState(null);
  const [busy, setBusy] = useState(false);

  async function saveEdit(body) {
    setBusy(true);
    try {
      await api.patch(`/api/checkins/${editing.id}`, body);
      toast('Check-in corrected.');
      setEditing(null);
      summary.reload();
      history.reload();
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      setBusy(false);
    }
  }

  async function remove(id) {
    try {
      await api.del(`/api/checkins/${id}`);
      toast('Check-in deleted.');
      summary.reload();
      history.reload();
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  if (summary.loading && !summary.data) return <Loading />;
  if (summary.error) return <ErrorState error={summary.error} onRetry={summary.reload} />;
  const s = summary.data;
  const metricOptions = [{ key: 'wellness_index', label: 'Wellness index' }, ...INDICATORS];
  const metricLabel = metricOptions.find((m) => m.key === metric).label;

  // Fill missing days so gaps are visible rather than interpolated.
  const points = [];
  const byDate = Object.fromEntries(s.history.map((h) => [h.date, h]));
  for (let i = 29; i >= 0; i -= 1) {
    const d = new Date();
    d.setDate(d.getDate() - i);
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    points.push({ x: key, y: byDate[key]?.[metric] ?? null });
  }

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h1>Your wellness indicators</h1>
          <p>Built only from your own check-in answers. A reflection aid — not a clinical score or diagnosis.</p>
        </div>
        <Link className="btn btn-primary" to="/app/checkin">{s.checked_in_today ? "Update today's check-in" : 'Check in now'}</Link>
      </div>

      {!s.latest ? (
        <div className="card">
          <Empty title="No check-ins yet" icon="chart">
            <p className="small">Once you check in, your indicators and trends will show up here.</p>
            <Link className="btn btn-primary btn-sm" to="/app/checkin">Do your first check-in</Link>
          </Empty>
        </div>
      ) : (
        <>
          <div className="grid grid-2">
            <section className="card row" style={{ alignItems: 'center', gap: 24 }} aria-labelledby="idx-h">
              <WellnessRing value={s.last_7_days.averages.wellness_index} />
              <div style={{ flex: 1, minWidth: 180 }}>
                <h2 id="idx-h">Last 7 days</h2>
                <p className="small muted" style={{ marginBottom: 6 }}>
                  Average of {s.last_7_days.checkins} check-in{s.last_7_days.checkins === 1 ? '' : 's'}.
                </p>
                <TrendText trend={s.trends.wellness_index} higherIsBetter />
                <div style={{ marginTop: 8 }}><span className="badge badge-self">Self-reported</span></div>
              </div>
            </section>
            <section className="card" aria-labelledby="ind-h">
              <h2 id="ind-h">Indicators (7-day average)</h2>
              <IndicatorBars values={s.last_7_days.averages} />
            </section>
          </div>

          <section className="card" aria-labelledby="trend-h">
            <div className="card-header">
              <h2 id="trend-h">Last 30 days</h2>
              <label className="row small" htmlFor="metric-select">
                Show
                <select id="metric-select" className="select" style={{ width: 'auto', minHeight: 36, padding: '4px 10px' }}
                  value={metric} onChange={(e) => setMetric(e.target.value)}>
                  {metricOptions.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
                </select>
              </label>
            </div>
            <LineChart points={points} title={`${metricLabel}, last 30 days`} valueLabel={metricLabel}
              emptyText="No values for this indicator in the last 30 days." />
            <p className="tiny muted">{s.definitions[metric]} Days without a check-in are left as gaps.</p>
          </section>
        </>
      )}

      <section className="card" aria-labelledby="hist-h">
        <h2 id="hist-h">Your check-ins</h2>
        <p className="small muted">You can correct or delete any check-in. (XP already earned is kept.)</p>
        {history.loading && <Loading />}
        {history.error && <ErrorState error={history.error} onRetry={history.reload} />}
        {history.data?.length === 0 && <p className="small muted">No check-ins in the last 60 days.</p>}
        {history.data?.length > 0 && (
          <div className="table-scroll">
            <table className="data">
              <thead>
                <tr>
                  <th scope="col">Date</th><th scope="col">Mood</th><th scope="col">Stress</th><th scope="col">Worry</th>
                  <th scope="col">Sleep</th><th scope="col">Academic</th><th scope="col">Index</th><th scope="col">Weighing on you</th>
                  <th scope="col"><span className="sr-only">Actions</span></th>
                </tr>
              </thead>
              <tbody>
                {history.data.map((c) => (
                  <tr key={c.id}>
                    <td>{formatDate(c.date)}</td>
                    <td>{c.inputs.mood ?? '—'}</td>
                    <td>{c.inputs.stress ?? '—'}</td>
                    <td>{c.inputs.anxiety ?? '—'}</td>
                    <td>{c.inputs.sleep_quality ?? '—'}{c.inputs.sleep_hours != null && ` · ${c.inputs.sleep_hours}h`}</td>
                    <td>{c.inputs.academic_pressure ?? '—'}</td>
                    <td>{c.indicators.wellness_index != null ? Math.round(c.indicators.wellness_index) : '—'}</td>
                    <td className="small">{c.stressors.map((x) => STRESSORS[x]).join(', ') || '—'}</td>
                    <td>
                      <div className="row" style={{ flexWrap: 'nowrap', gap: 4 }}>
                        <button className="btn btn-ghost btn-sm" onClick={() => setEditing(c)}>Edit</button>
                        <ConfirmButton confirmText="Delete?" onConfirm={() => remove(c.id)}>Delete</ConfirmButton>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card" aria-labelledby="how-h">
        <h2 id="how-h"><Icon name="info" size={18} /> How these indicators are calculated</h2>
        {method.data && (
          <div className="stack-sm small">
            <p style={{ margin: 0 }}><strong>Version {method.data.version}.</strong> {method.data.clinical_status}</p>
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {Object.entries(method.data.definitions).map(([k, v]) => <li key={k}>{v}</li>)}
            </ul>
            <p style={{ margin: 0 }}><strong>Normalising:</strong> each 1–5 answer becomes {method.data.normalisation.likert}. Sleep hours: {method.data.normalisation.sleep_hours}.</p>
            <p style={{ margin: 0 }}>
              <strong>Wellness index weights:</strong>{' '}
              {Object.entries(method.data.weights).map(([k, v]) => `${k.replace('_', ' ')} ${Math.round(v * 100)}%`).join(', ')}.
              Unanswered items are left out and the weights are re-balanced; at least {method.data.min_components_for_index} of 5 are needed, otherwise no index is shown.
            </p>
            <p style={{ margin: 0 }}>Indicators are recalculated whenever you save or correct a check-in. Nothing is inferred from your chats.</p>
          </div>
        )}
      </section>

      <Modal open={!!editing} onClose={() => setEditing(null)} title={`Correct check-in · ${editing ? formatDate(editing.date) : ''}`} labelledBy="edit-checkin">
        {editing && (
          <CheckInForm
            initial={{ ...editing.inputs, sleep_hours: editing.inputs.sleep_hours ?? '', stressors: editing.stressors, note: editing.note || '' }}
            onSubmit={saveEdit} busy={busy} submitLabel="Save correction" />
        )}
      </Modal>
    </div>
  );
}
