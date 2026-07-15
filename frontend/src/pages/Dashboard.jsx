import React, { useEffect, useState } from 'react'
import { api } from '../api.js'
import { PageHead } from '../App.jsx'
import { FField, Empty } from '../components.jsx'

function Metric({ val, lbl }) {
  return (
    <div className="metric">
      <div className="val">{val}</div>
      <div className="lbl">{lbl}</div>
    </div>
  )
}

// Genie-style horizontal collected/uncollected bars, one per job
function JobBars({ rows }) {
  if (!rows.length) return <Empty text="Job이 없습니다" />
  const max = Math.max(...rows.map(r => Math.max(r.target, r.collected)), 1)
  return (
    <>
      <div className="legend">
        <span><i style={{ background: 'var(--accent)' }} />수집됨</span>
        <span><i style={{ background: '#dbe6ff' }} />목표까지 남음</span>
      </div>
      {rows.map(r => (
        <div key={r.job} className="hbar-row">
          <span className="hbar-name" title={r.job}>{r.job}</span>
          <div className="hbar-track" style={{ maxWidth: `${Math.max(r.target, r.collected) / max * 100}%` }}>
            <div className="hbar-fill"
              style={{ width: `${Math.max(r.target, r.collected) ? r.collected / Math.max(r.target, r.collected) * 100 : 0}%` }} />
          </div>
          <span className="hbar-num">{r.collected} / {r.target || '—'}</span>
        </div>
      ))}
    </>
  )
}

function TrendChart({ points }) {
  if (!points.length) return <Empty text="수집일 데이터가 없습니다" />
  const W = 720, H = 180, PX = 40, PY = 24
  const max = Math.max(...points.map(p => p.count), 1)
  const x = (i) => PX + (points.length === 1 ? (W - 2 * PX) / 2 : (i / (points.length - 1)) * (W - 2 * PX))
  const y = (v) => H - PY - (v / max) * (H - 2 * PY)
  const line = points.map((p, i) => `${i ? 'L' : 'M'}${x(i)},${y(p.count)}`).join('')
  const area = `${line} L${x(points.length - 1)},${H - PY} L${x(0)},${H - PY} Z`
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', maxWidth: 900 }}>
      {[0, max].map(v => (
        <text key={v} x={PX - 8} y={y(v) + 4} textAnchor="end" fontSize="11" fill="#86909c">{v}</text>
      ))}
      <line x1={PX} x2={W - PX} y1={H - PY} y2={H - PY} stroke="#e5e7eb" />
      <path d={area} fill="rgba(19,194,194,.12)" />
      <path d={line} fill="none" stroke="var(--teal)" strokeWidth="2" />
      {points.map((p, i) => (
        <g key={p.date}>
          <circle cx={x(i)} cy={y(p.count)} r="3.5" fill="#fff" stroke="var(--teal)" strokeWidth="2" />
          <text x={x(i)} y={y(p.count) - 8} textAnchor="middle" fontSize="11" fill="#4e5969">{p.count}</text>
          <text x={x(i)} y={H - PY + 14} textAnchor="middle" fontSize="10" fill="#86909c">{p.date}</text>
        </g>
      ))}
    </svg>
  )
}

export default function Dashboard() {
  const [projects, setProjects] = useState([])
  const [pid, setPid] = useState('')
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')

  useEffect(() => { api.projects().then(setProjects).catch(e => setErr(e.message)) }, [])
  useEffect(() => {
    api.dashboard(pid || undefined).then(setD).catch(e => setErr(e.message))
  }, [pid])

  return (
    <>
      <PageHead crumbs={[{ label: 'Dashboard' }]} />
      <div className="page">
        {err && <div className="error">{err}</div>}
        <section className="panel">
          <div className="filter-grid">
            <FField label="Project">
              <select value={pid} onChange={e => setPid(e.target.value)}>
                <option value="">전체 프로젝트</option>
                {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </FField>
          </div>

          {d && (
            <>
              <div className="section-title">핵심 지표</div>
              <div className="metric-row">
                <Metric val={d.core.projects} lbl="Projects" />
                <Metric val={d.core.jobs} lbl="Jobs" />
                <Metric val={d.core.episodes} lbl="Episodes" />
                <Metric val={d.core.frames.toLocaleString()} lbl="총 프레임" />
                <Metric val={d.core.hours} lbl="수집 시간 (h)" />
                <Metric val={d.core.robots} lbl="로봇 기종" />
              </div>

              <div className="section-title" style={{ marginTop: 24 }}>효율 지표</div>
              <div className="metric-row">
                <Metric val={`${d.efficiency.pass_rate}%`} lbl="성공(Pass) 비율" />
                <Metric val={`${d.efficiency.review_pass_rate}%`} lbl="리뷰 통과율" />
                <Metric val={`${d.efficiency.done_rate}%`} lbl="리뷰 완료(Done) 진행률" />
              </div>

              <div className="section-title" style={{ marginTop: 24 }}>리소스 · 백로그</div>
              <div className="metric-row">
                <Metric val={d.backlog.recorders} lbl="Recorder 수" />
                <Metric val={d.backlog.pending_review} lbl="리뷰 대기 백로그" />
                <Metric val={d.backlog.rejected} lbl="반려 (재작업 필요)" />
              </div>
            </>
          )}
        </section>

        {d && (
          <div className="cols" style={{ gridTemplateColumns: '3fr 2fr' }}>
            <section className="panel">
              <div className="section-title">Job별 수집 진행</div>
              <JobBars rows={d.job_progress} />
            </section>
            <section className="panel">
              <div className="section-title">Recorder 랭킹</div>
              {d.recorder_rank.length === 0 ? <Empty /> : (
                <table>
                  <thead><tr><th>Recorder</th><th>수집</th><th>Pass</th><th>Pass Rate</th></tr></thead>
                  <tbody>
                    {d.recorder_rank.map(r => (
                      <tr key={r.recorder}>
                        <td>{r.recorder}</td><td>{r.collected}</td><td>{r.passed}</td><td>{r.pass_rate}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>
          </div>
        )}

        {d && (
          <section className="panel">
            <div className="section-title">수집 트렌드</div>
            <TrendChart points={d.trend} />
          </section>
        )}
      </div>
    </>
  )
}
