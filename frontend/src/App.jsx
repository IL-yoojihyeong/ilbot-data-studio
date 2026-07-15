import React, { useEffect, useState } from 'react'
import Dashboard from './pages/Dashboard.jsx'
import Projects from './pages/Projects.jsx'
import ProjectView from './pages/ProjectView.jsx'
import Episodes from './pages/Episodes.jsx'
import EpisodeView from './pages/EpisodeView.jsx'
import Users from './pages/Users.jsx'
import Datasets from './pages/Datasets.jsx'
import { UserProvider, ProfileSelect } from './user.jsx'

function parseHash() {
  const h = window.location.hash.replace(/^#\/?/, '')
  const parts = h.split('/')
  if (parts[0] === 'p' && parts[1]) {
    if (parts[2] === 'episodes') {
      return { page: 'episodes', id: +parts[1], jobId: parts[3] ? +parts[3] : null }
    }
    return { page: 'project', id: +parts[1] }
  }
  if (parts[0] === 'e' && parts[1]) return { page: 'episode', id: +parts[1] }
  if (parts[0] === 'projects') return { page: 'projects' }
  if (parts[0] === 'users') return { page: 'users' }
  if (parts[0] === 'datasets') return { page: 'datasets' }
  return { page: 'dashboard' }
}

export function nav(path) {
  window.location.hash = path
}

const NAV = [
  {
    group: '데이터 수집', items: [
      ['dashboard', 'Dashboard', ''],
      ['projects', 'Project Center', 'projects'],
    ],
  },
  {
    group: '데이터셋 관리', items: [
      ['datasets', 'Dataset / Export', 'datasets'],
    ],
  },
  {
    group: '사용자', items: [
      ['users', 'User Center', 'users'],
    ],
  },
]

function Sidebar({ page }) {
  const activeKey = { project: 'projects', episodes: 'projects', episode: 'projects' }[page] || page
  return (
    <aside className="sidebar">
      <a className="brand" href="#/">IL-BOT Data Studio</a>
      {NAV.map(g => (
        <div key={g.group}>
          <div className="nav-group">{g.group}</div>
          {g.items.map(([key, label, path]) => (
            <a key={key} className={`nav-item ${activeKey === key ? 'active' : ''}`}
              href={`#/${path}`}>{label}</a>
          ))}
        </div>
      ))}
    </aside>
  )
}

export default function App() {
  const [route, setRoute] = useState(parseHash())
  useEffect(() => {
    const on = () => setRoute(parseHash())
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])

  return (
    <UserProvider>
      <div className="app">
        <Sidebar page={route.page} />
        <div className="content">
          {route.page === 'dashboard' && <Dashboard />}
          {route.page === 'projects' && <Projects />}
          {route.page === 'project' && <ProjectView pid={route.id} />}
          {route.page === 'episodes' && <Episodes pid={route.id} jobId={route.jobId} />}
          {route.page === 'episode' && <EpisodeView eid={route.id} />}
          {route.page === 'users' && <Users />}
          {route.page === 'datasets' && <Datasets />}
        </div>
      </div>
    </UserProvider>
  )
}

export function PageHead({ crumbs }) {
  return (
    <div className="pagehead">
      <h1 className="crumb">
        {crumbs.map((c, i) => (
          <span key={i}>
            {i > 0 && <span className="sep">/</span>}
            {c.href ? <a href={c.href}>{c.label}</a> : c.label}
          </span>
        ))}
      </h1>
      <span className="grow" />
      <ProfileSelect />
    </div>
  )
}
