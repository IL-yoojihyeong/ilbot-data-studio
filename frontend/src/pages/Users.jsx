import React, { useState } from 'react'
import { api } from '../api.js'
import { PageHead } from '../App.jsx'
import { useUsers } from '../user.jsx'
import { Chip, ConfirmModal, Pager, Empty } from '../components.jsx'

const ROLE_KIND = { admin: 'blue', labeler: 'gray', reviewer: 'green' }

export default function Users() {
  const { me, users, reload, setMeId } = useUsers()
  const [name, setName] = useState('')
  const [role, setRole] = useState('labeler')
  const [del, setDel] = useState(null)
  const [err, setErr] = useState('')

  const add = async (e) => {
    e.preventDefault()
    if (!name.trim()) return
    try {
      await api.createUser({ name: name.trim(), role })
      setName(''); setErr(''); reload()
    } catch (e2) { setErr(e2.message) }
  }

  return (
    <>
      <PageHead crumbs={[{ label: 'User Center' }]} />
      <div className="page">
        {err && <div className="error" onClick={() => setErr('')}>{err}</div>}
        <section className="panel">
          <div className="section-title">프로필</div>
          <p className="muted small" style={{ marginTop: -6 }}>
            로그인 없이 프로필 선택으로 동작합니다 — 화면 우측 상단에서 자신의 프로필을 선택하면
            리뷰·수집 기록에 이름이 남습니다.
          </p>
          <form className="row" style={{ marginBottom: 14 }} onSubmit={add}>
            <input placeholder="이름" value={name} onChange={e => setName(e.target.value)} />
            <select value={role} onChange={e => setRole(e.target.value)}>
              <option value="labeler">labeler</option>
              <option value="reviewer">reviewer</option>
              <option value="admin">admin</option>
            </select>
            <button type="submit" className="primary">＋ 프로필 추가</button>
          </form>
          <div className="tablewrap">
            <table>
              <thead><tr><th>ID</th><th>이름</th><th>역할</th><th></th><th>Operation</th></tr></thead>
              <tbody>
                {users.map(u => (
                  <tr key={u.id}>
                    <td>{u.id}</td>
                    <td><b>{u.name}</b></td>
                    <td><Chip kind={ROLE_KIND[u.role] || 'gray'}>{u.role}</Chip></td>
                    <td>{me?.id === u.id
                      ? <Chip kind="blue">현재 프로필</Chip>
                      : <a className="small" onClick={() => setMeId(u.id)}>이 프로필 사용</a>}</td>
                    <td className="ops">
                      <a className="danger" onClick={() => setDel(u)}>Delete</a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {users.length === 0 && <Empty text="프로필이 없습니다" />}
          </div>
          <Pager total={users.length} />
        </section>
      </div>

      {del && (
        <ConfirmModal title="프로필 삭제" onClose={() => setDel(null)}
          text={`'${del.name}' 프로필을 삭제합니다. 담당/리뷰 기록의 이름 연결이 해제됩니다.`}
          onConfirm={async () => {
            try { await api.deleteUser(del.id); if (me?.id === del.id) setMeId(null); reload() }
            catch (e) { setErr(e.message) }
          }} />
      )}
    </>
  )
}
