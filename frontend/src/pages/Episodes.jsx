import React, { useEffect, useMemo, useState } from 'react'
import { api } from '../api.js'
import { PageHead } from '../App.jsx'
import { FField, StatusChip, REVIEW_STATUS, PASS_STATUS, Pager, Empty } from '../components.jsx'

export default function Episodes({ pid, jobId }) {
  const [project, setProject] = useState(null)
  const [jobs, setJobs] = useState([])
  const [episodes, setEpisodes] = useState([])
  const [fJob, setFJob] = useState(jobId ? String(jobId) : '')
  const [fReview, setFReview] = useState('')
  const [err, setErr] = useState('')

  useEffect(() => { setFJob(jobId ? String(jobId) : '') }, [jobId])

  useEffect(() => {
    Promise.all([api.project(pid), api.jobs(pid)])
      .then(([p, j]) => { setProject(p); setJobs(j) })
      .catch(e => setErr(e.message))
  }, [pid])

  useEffect(() => {
    api.episodes(pid, { job_id: fJob }).then(setEpisodes).catch(e => setErr(e.message))
  }, [pid, fJob])

  const counts = useMemo(() => {
    const c = { all: episodes.length }
    for (const k of Object.keys(REVIEW_STATUS)) c[k] = episodes.filter(e => e.review_status === k).length
    return c
  }, [episodes])

  const shown = fReview ? episodes.filter(e => e.review_status === fReview) : episodes
  const jobName = (id) => jobs.find(j => j.id === id)?.name || '—'
  const curJob = jobs.find(j => j.id === +fJob)

  return (
    <>
      <PageHead crumbs={[
        { label: 'Project Center', href: '#/projects' },
        { label: project ? project.name : `#${pid}`, href: `#/p/${pid}` },
        { label: curJob ? `${curJob.name} — Episodes` : 'Episodes' },
      ]} />
      {curJob && (
        <div className="meta-strip">
          <span><span className="k">담당</span><b>{curJob.assignee || '—'}</b></span>
          <span><span className="k">Instruction</span><b>{curJob.canonical_instruction || '—'}</b></span>
          <span><span className="k">Object</span><b>{curJob.object || '—'}</b></span>
          <span><span className="k">에피소드</span><b>{curJob.episodes}</b></span>
          <span><span className="k">성공 기준</span>{curJob.success_criteria || '—'}</span>
        </div>
      )}
      <div className="page">
        {err && <div className="error" onClick={() => setErr('')}>{err}</div>}
        <section className="panel">
          <div className="filter-grid">
            <FField label="Job">
              <select value={fJob} onChange={e => { setFJob(e.target.value); window.location.hash = `#/p/${pid}/episodes${e.target.value ? '/' + e.target.value : ''}` }}>
                <option value="">모든 Job</option>
                {jobs.map(j => <option key={j.id} value={j.id}>{j.name}</option>)}
              </select>
            </FField>
          </div>

          <div className="state-chips">
            <button className={fReview === '' ? 'active' : ''} onClick={() => setFReview('')}>
              All ({counts.all})</button>
            {Object.entries(REVIEW_STATUS).map(([k, [label]]) => (
              <button key={k} className={fReview === k ? 'active' : ''} onClick={() => setFReview(k)}>
                {label} ({counts[k]})</button>
            ))}
          </div>

          <div className="tablewrap">
            <table>
              <thead><tr>
                <th>ID</th><th>ep</th><th>frames</th><th>Job</th><th>Recorder</th><th>수집일</th>
                <th>로봇 S/N</th><th>Instruction</th><th>구간</th><th>Success</th><th>Review</th>
                <th>Reviewer</th><th>Operation</th>
              </tr></thead>
              <tbody>
                {shown.map(e => (
                  <tr key={e.id}>
                    <td>{e.id}</td>
                    <td>{e.episode_index}</td>
                    <td>{e.length}</td>
                    <td className="muted">{jobName(e.job_id)}</td>
                    <td className="muted">{e.recorder || '—'}</td>
                    <td className="muted">{e.recorded_at || '—'}</td>
                    <td className="muted">{e.robot_serial || '—'}</td>
                    <td className="ellipsis" title={e.task_text}>{e.task_text || <span className="muted">—</span>}</td>
                    <td>{e.segments.length}</td>
                    <td><StatusChip map={PASS_STATUS} value={e.pass_status} /></td>
                    <td><StatusChip map={REVIEW_STATUS} value={e.review_status} /></td>
                    <td className="muted">{e.reviewer || '—'}</td>
                    <td className="ops">
                      <a href={`#/e/${e.id}`}>{e.review_status === 'done' ? 'View'
                        : e.review_status === 'labeled' ? 'Review' : 'Label'}</a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {shown.length === 0 && <Empty text="에피소드가 없습니다" />}
          </div>
          <Pager total={shown.length} />
        </section>
      </div>
    </>
  )
}
