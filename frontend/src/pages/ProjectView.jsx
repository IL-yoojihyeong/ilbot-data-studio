import React, { useEffect, useRef, useState } from 'react'
import { api } from '../api.js'
import { PageHead } from '../App.jsx'
import { useUsers } from '../user.jsx'
import { Drawer, Modal, Field, StatusChip, Chip, PROJECT_STATUS, DIFFICULTY_KIND, ConfirmModal, Pager, Empty } from '../components.jsx'

const EMPTY_JOB = {
  name: '', canonical_instruction: '', assignee_id: '',
  object: '', success_criteria: '', description: '',
}

// Job 폼 공통 필드: Job 이름 / Canonical Instruction / 담당자 / Object /
// Success Criteria / 설명 (시나리오 확정 — 난이도는 프로젝트 레벨로 이동)
function JobFields({ f, set, users }) {
  return (
    <>
      <Field label="Job 이름" required>
        <input value={f.name} onChange={set('name')} placeholder="예: Pick Bottle" />
      </Field>
      <Field label="Canonical Instruction">
        <textarea rows={2} value={f.canonical_instruction} onChange={set('canonical_instruction')}
          placeholder="예: Pick up the bottle and place it into the tray." />
      </Field>
      <Field label="담당자">
        <select value={f.assignee_id} onChange={set('assignee_id')}>
          <option value="">선택 안 함</option>
          {users.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}
        </select>
      </Field>
      <Field label="Object">
        <input value={f.object} onChange={set('object')} placeholder="조작 대상 (예: bottle)" />
      </Field>
      <Field label="Success Criteria">
        <textarea rows={2} value={f.success_criteria} onChange={set('success_criteria')}
          placeholder="성공 판정 기준" />
      </Field>
      <Field label="Job 설명">
        <textarea rows={2} value={f.description} onChange={set('description')} />
      </Field>
    </>
  )
}

export function JobDrawer({ pid, initial, onSaved, onClose }) {
  const { users } = useUsers()
  const [err, setErr] = useState('')
  const [f, setF] = useState(initial
    ? { ...EMPTY_JOB, ...initial, assignee_id: initial.assignee_id || '' }
    : EMPTY_JOB)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })

  const save = async () => {
    if (!f.name.trim()) { setErr('Job 이름을 입력하세요'); return }
    const body = { ...f, name: f.name.trim(),
      assignee_id: f.assignee_id ? +f.assignee_id : null }
    try {
      if (initial) await api.updateJob(initial.id, body)
      else await api.createJob(pid, body)
      onSaved()
    } catch (e) { setErr(e.message) }
  }

  return (
    <Drawer title={initial ? 'Job 수정' : 'Add Job'} onClose={onClose} footer={
      <>
        <button onClick={onClose}>취소</button>
        <button className="primary" onClick={save}>{initial ? '저장' : '추가'}</button>
      </>
    }>
      {err && <div className="error">{err}</div>}
      <JobFields f={f} set={set} users={users} />
    </Drawer>
  )
}

// 데이터 불러오기 = Job 1개 생성 + 그 Job으로 에피소드 등록 (시나리오 확정:
// 모든 에피소드는 Job에 속해야 하므로 import가 곧 Job 생성이다)
function ImportDrawer({ pid, onStarted, onClose }) {
  const { users } = useUsers()
  const [path, setPath] = useState('')
  const [err, setErr] = useState('')
  const [f, setF] = useState(EMPTY_JOB)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })

  const start = async () => {
    if (!path.trim()) { setErr('경로를 입력하세요'); return }
    if (!f.name.trim()) { setErr('Job 이름을 입력하세요'); return }
    try {
      await api.createImport(pid, {
        path: path.trim(),
        job: { ...f, name: f.name.trim(),
          assignee_id: f.assignee_id ? +f.assignee_id : null },
      })
      onStarted()
    } catch (e) { setErr(e.message) }
  }

  return (
    <Drawer title="데이터 불러오기" onClose={onClose} footer={
      <>
        <button onClick={onClose}>취소</button>
        <button className="primary" onClick={start}>불러오기</button>
      </>
    }>
      {err && <div className="error">{err}</div>}
      <p className="muted small" style={{ marginTop: 0 }}>
        서버 경로 기준: Agibot G2 에피소드 폴더 / 상위 폴더 / LeRobot v3 루트를 지원합니다.
        불러온 데이터는 아래 정보로 생성되는 새 Job에 등록됩니다.
      </p>
      <Field label="경로" required>
        <input value={path} onChange={e => setPath(e.target.value)}
          placeholder="/path/to/data" />
      </Field>
      <JobFields f={f} set={set} users={users} />
    </Drawer>
  )
}

// Members 변경 — Owner 프로필로 선택 중일 때만 열 수 있다
function MembersModal({ project, users, onSaved, onClose }) {
  const [ids, setIds] = useState(project.members.map(m => m.id))
  const [err, setErr] = useState('')
  const toggle = (id) => setIds(prev =>
    prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id])

  const save = async () => {
    try {
      await api.updateProject(project.id, {
        name: project.name, description: project.description,
        usage: project.usage, difficulty: project.difficulty,
        action: project.action, owner_id: project.owner_id,
        start_date: project.start_date, due_date: project.due_date,
        status: project.status, tags: project.tags,
        robot_model: project.robot_model,
        member_ids: ids,
      })
      onSaved()
    } catch (e) { setErr(e.message) }
  }

  return (
    <Modal title="Members 변경" onClose={onClose} footer={
      <>
        <button onClick={onClose}>취소</button>
        <button className="primary" onClick={save}>저장</button>
      </>
    }>
      {err && <div className="error">{err}</div>}
      <div className="row">
        {users.map(u => (
          <label key={u.id} className="tag" style={{ cursor: 'pointer' }}>
            <input type="checkbox" checked={ids.includes(u.id)}
              onChange={() => toggle(u.id)} /> {u.name}
          </label>
        ))}
        {users.length === 0 && <span className="muted small">User Center에서 프로필을 먼저 만드세요</span>}
      </div>
    </Modal>
  )
}

export default function ProjectView({ pid }) {
  const { me, users } = useUsers()
  const [project, setProject] = useState(null)
  const [jobs, setJobs] = useState([])
  const [imports, setImports] = useState([])
  const [drawer, setDrawer] = useState(null)   // null | 'new' | job
  const [importing, setImporting] = useState(false)
  const [editMembers, setEditMembers] = useState(false)
  const [del, setDel] = useState(null)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const pollRef = useRef(null)

  const load = async () => {
    try {
      const [p, j, im] = await Promise.all([api.project(pid), api.jobs(pid), api.imports(pid)])
      setProject(p); setJobs(j); setImports(im)
      const active = im.some(t => t.status === 'pending' || t.status === 'running')
      clearTimeout(pollRef.current)
      if (active) pollRef.current = setTimeout(load, 2000)
    } catch (e) { setErr(e.message) }
  }
  useEffect(() => { load(); return () => clearTimeout(pollRef.current) }, [pid])

  if (!project) {
    return (
      <>
        <PageHead crumbs={[{ label: 'Project Center', href: '#/projects' }, { label: `#${pid}` }]} />
        <div className="page">{err ? <div className="error">{err}</div> : 'loading…'}</div>
      </>
    )
  }

  return (
    <>
      <PageHead crumbs={[{ label: 'Project Center', href: '#/projects' }, { label: `${project.name} — Job List` }]} />

      <div className="meta-strip">
        <span><span className="k">상태</span><StatusChip map={PROJECT_STATUS} value={project.status} /></span>
        {project.usage && <span><span className="k">Usage</span><span className="tag">{project.usage}</span></span>}
        {project.difficulty && (
          <span><span className="k">Difficulty</span>
            <Chip kind={DIFFICULTY_KIND[project.difficulty] || 'gray'}>{project.difficulty}</Chip></span>
        )}
        <span><span className="k">Owner</span><b>{project.owner || '—'}</b></span>
        <span><span className="k">기간</span><b>{project.start_date || '?'} ~ {project.due_date || '?'}</b></span>
        <span><span className="k">로봇</span><b>{project.robot_model || '미지정'}</b></span>
        <span>
          <span className="k">Members</span><b>{project.members.map(m => m.name).join(', ') || '—'}</b>
          {me && me.id === project.owner_id && (
            <a style={{ marginLeft: 6 }} onClick={() => setEditMembers(true)}>변경</a>
          )}
        </span>
        {project.tags.length > 0 && (
          <span>{project.tags.map(t => <span key={t} className="tag" style={{ marginRight: 4 }}>{t}</span>)}</span>
        )}
        {project.action && <span><span className="k">Action</span>{project.action}</span>}
        {project.description && <span className="muted">{project.description}</span>}
      </div>

      <div className="page">
        {msg && <div className="notice" onClick={() => setMsg('')}>{msg}</div>}
        {err && <div className="error" onClick={() => setErr('')}>{err}</div>}

        <section className="panel">
          <div className="row spread" style={{ marginBottom: 10 }}>
            <div className="row">
              <a href={`#/p/${pid}/episodes`}><button>전체 에피소드 보기</button></a>
              <button onClick={() => setImporting(true)}>📥 데이터 불러오기</button>
            </div>
            <button className="primary" onClick={() => setDrawer('new')}>＋ Add Job</button>
          </div>

          {imports.filter(t => t.status !== 'done').map(t => (
            <div key={t.id} className={t.status === 'failed' ? 'error' : 'notice'}>
              <code>{t.path}</code> — {t.status} {t.progress && `· ${t.progress}`}
            </div>
          ))}

          <div className="tablewrap">
            <table>
              <thead><tr>
                <th>ID</th><th>Job 이름</th><th>담당</th><th>Canonical Instruction</th>
                <th>Object</th><th>Success Criteria</th><th>설명</th><th>에피소드</th><th>Done</th><th>Operation</th>
              </tr></thead>
              <tbody>
                {jobs.map(j => (
                  <tr key={j.id}>
                    <td>{j.id}</td>
                    <td><a href={`#/p/${pid}/episodes/${j.id}`}><b>{j.name}</b></a></td>
                    <td>{j.assignee || '—'}</td>
                    <td className="ellipsis" title={j.canonical_instruction}>{j.canonical_instruction || <span className="muted">—</span>}</td>
                    <td className="muted">{j.object || '—'}</td>
                    <td className="ellipsis muted" title={j.success_criteria}>{j.success_criteria || '—'}</td>
                    <td className="ellipsis muted" title={j.description}>{j.description || '—'}</td>
                    <td>{j.episodes}</td>
                    <td>{j.done}</td>
                    <td className="ops">
                      <a href={`#/p/${pid}/episodes/${j.id}`}>Episodes</a>
                      <a onClick={() => setDrawer(j)}>Edit</a>
                      <a className="danger" onClick={() => setDel(j)}>Delete</a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {jobs.length === 0 && <Empty text="Job이 없습니다 — Add Job으로 생성하세요" />}
          </div>
          <Pager total={jobs.length} />
        </section>
      </div>

      {drawer && (
        <JobDrawer pid={pid} initial={drawer === 'new' ? null : drawer}
          onClose={() => setDrawer(null)}
          onSaved={() => { setDrawer(null); load() }} />
      )}
      {importing && (
        <ImportDrawer pid={pid} onClose={() => setImporting(false)}
          onStarted={() => { setImporting(false); setMsg('불러오기 시작됨 — 새 Job이 생성되었습니다'); load() }} />
      )}
      {editMembers && (
        <MembersModal project={project} users={users}
          onClose={() => setEditMembers(false)}
          onSaved={() => { setEditMembers(false); setMsg('Members가 변경되었습니다'); load() }} />
      )}
      {del && (
        <ConfirmModal title="Job 삭제" onClose={() => setDel(null)}
          text={`'${del.name}' Job을 삭제합니다. 에피소드가 속한 Job은 삭제할 수 없습니다.`}
          onConfirm={async () => { try { await api.deleteJob(del.id); load() } catch (e) { setErr(e.message) } }} />
      )}
    </>
  )
}
