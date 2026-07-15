import React, { useEffect, useMemo, useState } from 'react'
import { api } from '../api.js'
import { PageHead } from '../App.jsx'
import { useUsers } from '../user.jsx'
import { Drawer, Field, FField, StatusChip, Chip, ChoiceChips, PROJECT_STATUS, PROJECT_USAGES, ROBOT_TYPES, PROJECT_DIFFICULTIES, DIFFICULTY_KIND, ConfirmModal, Pager, Empty } from '../components.jsx'

const EMPTY = {
  name: '', usage: '', robot_model: '', description: '', difficulty: '',
  action: '', owner_id: '', member_ids: [], start_date: '',
  due_date: '', status: 'active', tags: '',
}

function ProjectDrawer({ initial, onSaved, onClose }) {
  const { users } = useUsers()
  const [err, setErr] = useState('')
  const [f, setF] = useState(initial ? {
    ...initial, owner_id: initial.owner_id || '',
    member_ids: initial.members.map(m => m.id),
    tags: initial.tags.join(', '),
  } : EMPTY)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const toggle = (k, id) => setF(prev => ({
    ...prev, [k]: prev[k].includes(id) ? prev[k].filter(x => x !== id) : [...prev[k], id],
  }))

  const save = async () => {
    if (!f.name.trim()) { setErr('프로젝트 이름을 입력하세요'); return }
    if (!f.usage) { setErr('프로젝트 Usage를 선택하세요'); return }
    if (!f.robot_model) { setErr('로봇 Type을 선택하세요'); return }
    if (!f.difficulty) { setErr('Difficulty를 선택하세요'); return }
    const body = {
      ...f, name: f.name.trim(),
      owner_id: f.owner_id ? +f.owner_id : null,
      tags: f.tags.split(',').map(t => t.trim()).filter(Boolean),
    }
    try {
      if (initial) await api.updateProject(initial.id, body)
      else await api.createProject(body)
      onSaved()
    } catch (e) { setErr(e.message) }
  }

  return (
    <Drawer title={initial ? '프로젝트 수정' : '새 프로젝트'} onClose={onClose} footer={
      <>
        <button onClick={onClose}>취소</button>
        <button className="primary" onClick={save}>{initial ? '저장' : '생성'}</button>
      </>
    }>
      {err && <div className="error">{err}</div>}
      <Field label="이름" required>
        <input value={f.name} onChange={set('name')} placeholder="프로젝트 이름" />
      </Field>
      <Field label="Usage" required>
        <ChoiceChips options={PROJECT_USAGES} value={f.usage}
          onChange={v => setF({ ...f, usage: v })} />
      </Field>
      <Field label="로봇 Type" required>
        <ChoiceChips options={ROBOT_TYPES} value={f.robot_model}
          onChange={v => setF({ ...f, robot_model: v })} />
        {f.robot_model && !ROBOT_TYPES.includes(f.robot_model) &&
          <div className="muted small">현재 값: {f.robot_model}</div>}
      </Field>
      <Field label="프로젝트 설명">
        <textarea rows={2} value={f.description} onChange={set('description')} placeholder="프로젝트 설명" />
      </Field>
      <Field label="Difficulty" required>
        <ChoiceChips options={PROJECT_DIFFICULTIES} value={f.difficulty}
          onChange={v => setF({ ...f, difficulty: v })} />
      </Field>
      <Field label="Owner">
        <select value={f.owner_id} onChange={set('owner_id')}>
          <option value="">선택 안 함</option>
          {users.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}
        </select>
      </Field>
      <Field label="Members">
        <div className="row">
          {users.map(u => (
            <label key={u.id} className="tag" style={{ cursor: 'pointer' }}>
              <input type="checkbox" checked={f.member_ids.includes(u.id)}
                onChange={() => toggle('member_ids', u.id)} /> {u.name}
            </label>
          ))}
          {users.length === 0 && <span className="muted small">User Center에서 프로필을 먼저 만드세요</span>}
        </div>
      </Field>
      <Field label="Action 정의">
        <textarea rows={3} value={f.action} onChange={set('action')}
          placeholder="이 프로젝트에서 수행할 Action을 텍스트로 정의" />
      </Field>
      <Field label="기간">
        <div className="row">
          <input type="date" value={f.start_date} onChange={set('start_date')} />
          <span className="muted">~</span>
          <input type="date" value={f.due_date} onChange={set('due_date')} />
        </div>
      </Field>
      <Field label="상태">
        <select value={f.status} onChange={set('status')}>
          {Object.entries(PROJECT_STATUS).map(([k, [label]]) => <option key={k} value={k}>{label}</option>)}
        </select>
      </Field>
      <Field label="태그">
        <input value={f.tags} onChange={set('tags')} placeholder="쉼표로 구분 (예: G2, pick-place)" />
      </Field>
    </Drawer>
  )
}

export default function Projects() {
  const [projects, setProjects] = useState([])
  const [drawer, setDrawer] = useState(null)     // null | 'new' | project object
  const [del, setDel] = useState(null)
  const [err, setErr] = useState('')
  const [fName, setFName] = useState('')
  const [fStatus, setFStatus] = useState('')

  const load = () => api.projects().then(setProjects).catch(e => setErr(e.message))
  useEffect(() => { load() }, [])

  const shown = useMemo(() => projects.filter(p =>
    (!fName || p.name.toLowerCase().includes(fName.toLowerCase()))
    && (!fStatus || p.status === fStatus)), [projects, fName, fStatus])

  return (
    <>
      <PageHead crumbs={[{ label: 'Project Center' }]} />
      <div className="page">
        {err && <div className="error" onClick={() => setErr('')}>{err}</div>}
        <section className="panel">
          <div className="filter-grid">
            <FField label="프로젝트 이름">
              <input placeholder="검색" value={fName} onChange={e => setFName(e.target.value)} />
            </FField>
            <FField label="상태">
              <select value={fStatus} onChange={e => setFStatus(e.target.value)}>
                <option value="">전체</option>
                {Object.entries(PROJECT_STATUS).map(([k, [label]]) => <option key={k} value={k}>{label}</option>)}
              </select>
            </FField>
          </div>
          <div className="row spread" style={{ marginBottom: 10 }}>
            <span className="muted small">{shown.length}개 프로젝트</span>
            <button className="primary" onClick={() => setDrawer('new')}>＋ 새 프로젝트</button>
          </div>
          <div className="tablewrap">
            <table>
              <thead><tr>
                <th>ID</th><th>이름</th><th>Usage</th><th>Difficulty</th><th>Owner</th><th>Members</th><th>로봇</th><th>태그</th>
                <th>진행 (Done/전체)</th><th>마감</th><th>상태</th><th>Operation</th>
              </tr></thead>
              <tbody>
                {shown.map(p => (
                  <tr key={p.id}>
                    <td>{p.id}</td>
                    <td><a href={`#/p/${p.id}`}><b>{p.name}</b></a></td>
                    <td>{p.usage ? <span className="tag">{p.usage}</span> : '—'}</td>
                    <td>{p.difficulty ? <Chip kind={DIFFICULTY_KIND[p.difficulty] || 'gray'}>{p.difficulty}</Chip> : '—'}</td>
                    <td>{p.owner || '—'}</td>
                    <td className="muted">{p.members.map(m => m.name).join(', ') || '—'}</td>
                    <td className="muted">{p.robot_model || '—'}</td>
                    <td>{p.tags.map(t => <span key={t} className="tag" style={{ marginRight: 4 }}>{t}</span>)}</td>
                    <td>
                      <div className="row" style={{ flexWrap: 'nowrap' }}>
                        <div className="hbar-track" style={{ width: 80 }}>
                          <div className="hbar-fill" style={{ width: `${p.episodes ? p.done / p.episodes * 100 : 0}%` }} />
                        </div>
                        <span className="muted small">{p.done}/{p.episodes}</span>
                      </div>
                    </td>
                    <td className="muted">{p.due_date || '—'}</td>
                    <td><StatusChip map={PROJECT_STATUS} value={p.status} /></td>
                    <td className="ops">
                      <a href={`#/p/${p.id}`}>Enter</a>
                      <a onClick={() => setDrawer(p)}>Edit</a>
                      <a className="danger" onClick={() => setDel(p)}>Delete</a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {shown.length === 0 && <Empty text="프로젝트가 없습니다" />}
          </div>
          <Pager total={shown.length} />
        </section>
      </div>

      {drawer && (
        <ProjectDrawer initial={drawer === 'new' ? null : drawer}
          onClose={() => setDrawer(null)}
          onSaved={() => { setDrawer(null); load() }} />
      )}
      {del && (
        <ConfirmModal title="프로젝트 삭제" onClose={() => setDel(null)}
          text={`'${del.name}' 프로젝트와 소속 Job·에피소드 레이블을 모두 삭제합니다. 계속할까요?`}
          onConfirm={async () => { try { await api.deleteProject(del.id); load() } catch (e) { setErr(e.message) } }} />
      )}
    </>
  )
}
