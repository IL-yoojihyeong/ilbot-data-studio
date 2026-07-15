import React, { useEffect, useMemo, useState } from 'react'
import { api } from '../api.js'
import { PageHead } from '../App.jsx'
import { Drawer, Field, Modal, Chip, StatusChip, PASS_STATUS, ConfirmModal, Pager, Empty } from '../components.jsx'

const SPLITS = ['train', 'val', 'test']
const EXPORT_STATUS = {
  pending: ['대기', 'gray'],
  running: ['진행 중', 'orange'],
  done: ['완료', 'green'],
  failed: ['실패', 'red'],
}
const EMPTY = {
  name: '', description: '', job_ids: [], review_filter: 'done',
  include_non_pass: false, ratios: { train: 80, val: 10, test: 10 },
  seed: 42, job_splits: {},
}

const platform = (robotModel) => (robotModel || '').split('_')[0].toLowerCase()

function DatasetDrawer({ initial, projects, jobsByProject, onSaved, onClose }) {
  const [err, setErr] = useState('')
  const [f, setF] = useState(initial ? {
    name: initial.name, description: initial.description,
    job_ids: initial.job_ids, review_filter: initial.review_filter,
    include_non_pass: initial.include_non_pass,
    ratios: { ...initial.ratios }, seed: initial.seed,
    job_splits: { ...initial.job_splits },
  } : EMPTY)

  // robot platform locked by the first selected job's project
  const lockedPlatform = useMemo(() => {
    for (const p of projects) {
      if ((jobsByProject[p.id] || []).some(j => f.job_ids.includes(j.id)) && p.robot_model) {
        return platform(p.robot_model)
      }
    }
    return ''
  }, [f.job_ids, projects, jobsByProject])

  const toggleJob = (id) => setF(prev => {
    const on = prev.job_ids.includes(id)
    const job_splits = { ...prev.job_splits }
    if (on) delete job_splits[String(id)]
    return {
      ...prev, job_splits,
      job_ids: on ? prev.job_ids.filter(x => x !== id) : [...prev.job_ids, id],
    }
  })
  const setOverride = (id, sp) => setF(prev => {
    const job_splits = { ...prev.job_splits }
    if (sp) job_splits[String(id)] = sp
    else delete job_splits[String(id)]
    return { ...prev, job_splits }
  })
  const setRatio = (sp) => (e) => setF(prev => ({
    ...prev, ratios: { ...prev.ratios, [sp]: e.target.value === '' ? 0 : +e.target.value },
  }))

  const save = async () => {
    if (!f.name.trim()) { setErr('Dataset 이름을 입력하세요'); return }
    if (f.job_ids.length === 0) { setErr('Job을 1개 이상 선택하세요'); return }
    const body = { ...f, seed: +f.seed || 0 }
    try {
      if (initial) await api.updateTrainingDataset(initial.id, body)
      else await api.createTrainingDataset(body)
      onSaved()
    } catch (e) { setErr(e.message) }
  }

  return (
    <Drawer title={initial ? 'Dataset 수정' : '새 Dataset'} width={700} onClose={onClose} footer={
      <>
        <button onClick={onClose}>취소</button>
        <button className="primary" onClick={save}>{initial ? '저장' : '생성'}</button>
      </>
    }>
      {err && <div className="error">{err}</div>}
      <Field label="이름" required>
        <input value={f.name} onChange={e => setF({ ...f, name: e.target.value })}
          placeholder="예: g2-pick-place-v1" />
      </Field>
      <Field label="설명">
        <textarea rows={2} value={f.description}
          onChange={e => setF({ ...f, description: e.target.value })} />
      </Field>
      <Field label="Jobs" required>
        <div>
          {projects.map(p => {
            const jobs = jobsByProject[p.id] || []
            if (jobs.length === 0) return null
            const incompatible = lockedPlatform && p.robot_model
              && platform(p.robot_model) !== lockedPlatform
            return (
              <div key={p.id} style={{ marginBottom: 8 }}>
                <div className="muted small" style={{ marginBottom: 2 }}>
                  {p.name} {p.robot_model && <span className="tag">{p.robot_model}</span>}
                  {incompatible && <span className="warn small"> (로봇 기종 불일치 — 선택 불가)</span>}
                </div>
                {jobs.map(j => {
                  const on = f.job_ids.includes(j.id)
                  return (
                    <div key={j.id} className="row" style={{ marginLeft: 12, marginBottom: 2 }}>
                      <label className="row small" style={{ cursor: incompatible ? 'not-allowed' : 'pointer' }}>
                        <input type="checkbox" checked={on} disabled={incompatible && !on}
                          onChange={() => toggleJob(j.id)} />
                        {j.name} <span className="muted">({j.done ?? '?'}/{j.episodes} done)</span>
                      </label>
                      {on && (
                        <select value={f.job_splits[String(j.id)] || ''}
                          onChange={e => setOverride(j.id, e.target.value)}>
                          <option value="">비율 분할 (자동)</option>
                          {SPLITS.map(sp => <option key={sp} value={sp}>{sp} 전체 배정</option>)}
                        </select>
                      )}
                    </div>
                  )
                })}
              </div>
            )
          })}
          {projects.every(p => (jobsByProject[p.id] || []).length === 0) &&
            <span className="muted small">Job이 없습니다 — 프로젝트에서 데이터를 먼저 수집하세요</span>}
        </div>
      </Field>
      <Field label="포함 범위">
        <div className="row">
          <select value={f.review_filter}
            onChange={e => setF({ ...f, review_filter: e.target.value })}>
            <option value="done">리뷰 완료(Done)만</option>
            <option value="any">전체 (리뷰 상태 무관)</option>
          </select>
          <label className="row small">
            <input type="checkbox" checked={f.include_non_pass}
              onChange={e => setF({ ...f, include_non_pass: e.target.checked })} />
            실패(non-pass) 에피소드 포함
          </label>
        </div>
      </Field>
      <Field label="스플릿 비율">
        <div className="row">
          {SPLITS.map(sp => (
            <label key={sp} className="row small muted">{sp}
              <input type="number" min="0" style={{ width: 64 }}
                value={f.ratios[sp]} onChange={setRatio(sp)} />
            </label>
          ))}
          <span className="muted small">에피소드 단위 셔플 분할 (Job 전체 배정 제외)</span>
        </div>
      </Field>
      <Field label="Seed">
        <input type="number" style={{ width: 100 }} value={f.seed}
          onChange={e => setF({ ...f, seed: e.target.value })} />
        <span className="muted small" style={{ marginLeft: 8 }}>같은 seed면 항상 같은 분할</span>
      </Field>
    </Drawer>
  )
}

function PreviewModal({ tds, onClose }) {
  const [pv, setPv] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => {
    api.tdsPreview(tds.id).then(setPv).catch(e => setErr(e.message))
  }, [tds.id])
  return (
    <Modal title={`스플릿 미리보기 — ${tds.name}`} onClose={onClose}
      footer={<button onClick={onClose}>닫기</button>}>
      {err && <div className="error">{err}</div>}
      {!pv && !err && 'loading…'}
      {pv && (
        <div style={{ maxHeight: '60vh', overflow: 'auto' }}>
          {pv.warnings.map((w, i) => <div key={i} className="notice">⚠ {w}</div>)}
          {SPLITS.map(sp => (
            <div key={sp} style={{ marginBottom: 10 }}>
              <div className="section-title">{sp} · {pv.splits[sp].length}개</div>
              {pv.splits[sp].length > 0 && (
                <div className="tablewrap">
                  <table>
                    <thead><tr>
                      <th>Episode</th><th>프로젝트 / Job</th><th>Frames</th>
                      <th>Pass</th><th>구간</th><th>Instruction</th>
                    </tr></thead>
                    <tbody>
                      {pv.splits[sp].map(e => (
                        <tr key={e.episode_id}>
                          <td><a href={`#/e/${e.episode_id}`}>#{e.episode_id}</a></td>
                          <td className="muted">{e.project} / {e.job}</td>
                          <td>{e.length}</td>
                          <td><StatusChip map={PASS_STATUS} value={e.pass_status} /></td>
                          <td>{e.segments || '—'}</td>
                          <td className="muted small">{e.task_text || '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </Modal>
  )
}

function HistoryModal({ tds, onClose }) {
  const [xs, setXs] = useState(null)
  useEffect(() => {
    const load = () => api.tdsExports(tds.id).then(setXs).catch(() => { })
    load()
    const t = setInterval(load, 2000)
    return () => clearInterval(t)
  }, [tds.id])
  return (
    <Modal title={`Export 이력 — ${tds.name}`} onClose={onClose}
      footer={<button onClick={onClose}>닫기</button>}>
      {!xs && 'loading…'}
      {xs && xs.length === 0 && <Empty text="Export 이력이 없습니다" />}
      {xs && xs.length > 0 && (
        <div className="tablewrap" style={{ maxHeight: '55vh', overflow: 'auto' }}>
          <table>
            <thead><tr><th>ID</th><th>일시</th><th>상태</th><th>구성</th><th>경로 / 진행</th></tr></thead>
            <tbody>
              {xs.map(x => (
                <tr key={x.id}>
                  <td>{x.id}</td>
                  <td className="muted">{x.created_at}</td>
                  <td><StatusChip map={EXPORT_STATUS} value={x.status} /></td>
                  <td className="muted small">
                    {x.config.counts
                      ? SPLITS.map(sp => `${sp} ${x.config.counts[sp]}`).join(' · ')
                        + ` · ${x.config.total_frames}f`
                      : '—'}
                  </td>
                  <td className="mono small">{x.status === 'done' ? x.out_path : x.progress}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Modal>
  )
}

export default function Datasets() {
  const [list, setList] = useState([])
  const [projects, setProjects] = useState([])
  const [jobsByProject, setJobsByProject] = useState({})
  const [drawer, setDrawer] = useState(null)     // null | 'new' | tds
  const [preview, setPreview] = useState(null)
  const [history, setHistory] = useState(null)
  const [del, setDel] = useState(null)
  const [err, setErr] = useState('')

  const load = () => api.trainingDatasets().then(setList).catch(e => setErr(e.message))
  useEffect(() => {
    load()
    api.projects().then(async ps => {
      setProjects(ps)
      const entries = await Promise.all(ps.map(async p => [p.id, await api.jobs(p.id)]))
      setJobsByProject(Object.fromEntries(entries))
    }).catch(e => setErr(e.message))
  }, [])

  // poll while an export is running
  const running = list.some(t => t.last_export
    && ['pending', 'running'].includes(t.last_export.status))
  useEffect(() => {
    if (!running) return
    const t = setInterval(load, 2500)
    return () => clearInterval(t)
  }, [running])

  const startExport = async (t) => {
    try { await api.startExport(t.id); load() } catch (e) { setErr(e.message) }
  }

  return (
    <>
      <PageHead crumbs={[{ label: 'Dataset / Export' }]} />
      <div className="page">
        {err && <div className="error" onClick={() => setErr('')}>{err}</div>}
        <section className="panel">
          <div className="row spread" style={{ marginBottom: 10 }}>
            <span className="muted small">
              Job들을 묶어 Train/Val/Test를 구성하고 LeRobot v3로 export합니다
              (세그먼트는 per-frame task로 반영).
            </span>
            <button className="primary" onClick={() => setDrawer('new')}>＋ 새 Dataset</button>
          </div>
          <div className="tablewrap">
            <table>
              <thead><tr>
                <th>ID</th><th>이름</th><th>로봇</th><th>Jobs</th>
                <th>Train / Val / Test</th><th>포함 범위</th>
                <th>최근 Export</th><th>Operation</th>
              </tr></thead>
              <tbody>
                {list.map(t => (
                  <tr key={t.id}>
                    <td>{t.id}</td>
                    <td>
                      <b>{t.name}</b>
                      {t.description && <div className="muted small">{t.description}</div>}
                    </td>
                    <td className="muted">{t.robot_models.join(', ') || '—'}</td>
                    <td className="muted small">
                      {t.jobs.map(j => `${j.project}/${j.name}`).join(', ') || '—'}
                    </td>
                    <td>
                      <span className="mono">{SPLITS.map(sp => t.counts[sp]).join(' / ')}</span>
                      {t.warnings.length > 0 &&
                        <span className="warn small" title={t.warnings.join('\n')}> ⚠{t.warnings.length}</span>}
                    </td>
                    <td className="muted small">
                      {t.review_filter === 'done' ? 'Done만' : '전체'}
                      {t.include_non_pass ? ' · non-pass 포함' : ''}
                    </td>
                    <td>
                      {t.last_export ? (
                        <div className="row" style={{ flexWrap: 'nowrap' }}>
                          <StatusChip map={EXPORT_STATUS} value={t.last_export.status} />
                          <span className="muted small">{t.last_export.created_at}</span>
                        </div>
                      ) : <span className="muted">—</span>}
                      {t.last_export && ['pending', 'running'].includes(t.last_export.status) &&
                        <div className="muted small">{t.last_export.progress}</div>}
                    </td>
                    <td className="ops">
                      <a onClick={() => startExport(t)}>Export</a>
                      <a onClick={() => setPreview(t)}>미리보기</a>
                      <a onClick={() => setHistory(t)}>이력</a>
                      <a onClick={() => setDrawer(t)}>Edit</a>
                      <a className="danger" onClick={() => setDel(t)}>Delete</a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {list.length === 0 && <Empty text="Dataset이 없습니다 — Job들을 묶어 첫 Dataset을 만드세요" />}
          </div>
          <Pager total={list.length} />
        </section>
      </div>

      {drawer && (
        <DatasetDrawer initial={drawer === 'new' ? null : drawer}
          projects={projects} jobsByProject={jobsByProject}
          onClose={() => setDrawer(null)}
          onSaved={() => { setDrawer(null); load() }} />
      )}
      {preview && <PreviewModal tds={preview} onClose={() => setPreview(null)} />}
      {history && <HistoryModal tds={history} onClose={() => setHistory(null)} />}
      {del && (
        <ConfirmModal title="Dataset 삭제" onClose={() => setDel(null)}
          text={`'${del.name}' Dataset 구성을 삭제합니다 (이미 export된 파일은 디스크에 남습니다). 계속할까요?`}
          onConfirm={async () => { try { await api.deleteTrainingDataset(del.id); load() } catch (e) { setErr(e.message) } }} />
      )}
    </>
  )
}
