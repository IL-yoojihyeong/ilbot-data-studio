import React, { createContext, useContext, useEffect, useState } from 'react'
import { api } from './api.js'

// No login by design (SPEC): a profile picked here is stamped on
// reviews/recordings. Persisted per-browser in localStorage.
const KEY = 'robolabel_user_id'

export const UserCtx = createContext({ me: null, users: [], setMeId: () => {}, reload: () => {} })
export const useUsers = () => useContext(UserCtx)

export function UserProvider({ children }) {
  const [users, setUsers] = useState([])
  const [meId, setMeIdState] = useState(+localStorage.getItem(KEY) || null)

  const reload = () => api.users().then(setUsers).catch(() => {})
  useEffect(() => { reload() }, [])

  const setMeId = (id) => {
    setMeIdState(id)
    if (id) localStorage.setItem(KEY, id)
    else localStorage.removeItem(KEY)
  }

  const me = users.find(u => u.id === meId) || null
  return (
    <UserCtx.Provider value={{ me, users, setMeId, reload }}>
      {children}
    </UserCtx.Provider>
  )
}

export function ProfileSelect() {
  const { me, users, setMeId, reload } = useUsers()

  const onChange = async (e) => {
    if (e.target.value === '__new__') {
      const name = window.prompt('새 프로필 이름')
      if (!name || !name.trim()) { e.target.value = me?.id || ''; return }
      try {
        const u = await api.createUser({ name: name.trim() })
        await reload()
        setMeId(u.id)
      } catch (err) { alert(err.message) }
    } else {
      setMeId(e.target.value ? +e.target.value : null)
    }
  }

  return (
    <span className="profile row">
      <span className="muted small">프로필</span>
      <select value={me?.id || ''} onChange={onChange}>
        <option value="">선택 안 함</option>
        {users.map(u => <option key={u.id} value={u.id}>{u.name} ({u.role})</option>)}
        <option value="__new__">＋ 새 프로필…</option>
      </select>
    </span>
  )
}
