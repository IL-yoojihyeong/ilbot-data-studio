import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api.js'
import { PageHead } from '../App.jsx'
import Timeline from '../Timeline.jsx'
import { useUsers } from '../user.jsx'
import { Modal, Field, StatusChip, REVIEW_STATUS } from '../components.jsx'

// Joint curve colors tuned for a light background
const COLORS = ['#1a66ff', '#fa8c16', '#389e0d', '#f5222d', '#722ed1', '#eb2f96',
  '#7cb305', '#2f54eb', '#d4b106', '#13c2c2', '#fa541c', '#9254de',
  '#874d00', '#5c7080', '#5b8c00', '#597ef7', '#08979c', '#237804',
  '#cf1322', '#531dab', '#006d75', '#ad8b00', '#ad4e00', '#434343']

export default function EpisodeView({ eid }) {
  const { me, users } = useUsers()
  const [ep, setEp] = useState(null)
  const [ts, setTs] = useState(null)
  const [time, setTime] = useState(0)         // episode-local seconds
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(1)
  const [dims, setDims] = useState([])        // selected joint indices
  const [showAction, setShowAction] = useState(false)
  const [segments, setSegments] = useState([])
  const [taskText, setTaskText] = useState('')
  const [passStatus, setPassStatus] = useState('unlabeled')
  const [failureReason, setFailureReason] = useState('')
  const [recorderId, setRecorderId] = useState('')
  const [recordedAt, setRecordedAt] = useState('')
  const [robotSerial, setRobotSerial] = useState('')
  const [reviewStatus, setReviewStatus] = useState('unlabeled')
  const [reviewNote, setReviewNote] = useState('')
  const [reviewer, setReviewer] = useState(null)
  const [rejecting, setRejecting] = useState(false)
  const [rejectNote, setRejectNote] = useState('')
  const [markIn, setMarkIn] = useState(null)
  const [dirty, setDirty] = useState(false)
  const [savedMsg, setSavedMsg] = useState('')
  const [err, setErr] = useState('')
  const videoRefs = useRef({})

  const applyEp = (e) => {
    setEp(e)
    setSegments(e.segments)
    setTaskText(e.task_text)
    setPassStatus(e.pass_status)
    setFailureReason(e.failure_reason)
    setRecorderId(e.recorder_id || '')
    setRecordedAt(e.recorded_at)
    setRobotSerial(e.robot_serial)
    setReviewStatus(e.review_status)
    setReviewNote(e.review_note)
    setReviewer(e.reviewer)
  }

  useEffect(() => {
    api.episode(eid).then(applyEp).catch(e => setErr(e.message))
    api.timeseries(eid).then(t => {
      setTs(t)
      setDims(t.names.slice(0, 4).map((_, i) => i))
    })
  }, [eid])

  const locked = reviewStatus === 'done'      // view-only: no annotation edits

  const fps = ep?.fps || 30
  const duration = ep ? ep.length / fps : 0
  const videoKeys = ep ? Object.keys(ep.videos) : []
  const master = videoKeys[0]
  const fromTs = (k) => ep.videos[k].from_ts || 0

  // --- playback control: master video drives the clock -------------------
  const setAll = useCallback((fn) => {
    videoKeys.forEach(k => { const v = videoRefs.current[k]; if (v) fn(v, k) })
  }, [videoKeys.join()])

  const seek = useCallback((t) => {
    const clamped = Math.max(0, Math.min(t, duration - 1e-3))
    setAll((v, k) => { v.currentTime = fromTs(k) + clamped })
    setTime(clamped)
  }, [duration, setAll])

  const togglePlay = useCallback(() => {
    if (!master) return
    if (playing) { setAll(v => v.pause()); setPlaying(false) }
    else {
      if (time >= duration - 0.05) seek(0)
      setAll(v => { v.play() }); setPlaying(true)
    }
  }, [playing, master, time, duration, seek, setAll])

  useEffect(() => { setAll(v => { v.playbackRate = speed }) }, [speed, setAll])

  // master timeupdate -> episode clock + drift correction + window end
  useEffect(() => {
    const v = videoRefs.current[master]
    if (!v || !ep) return
    let raf
    const tick = () => {
      const t = v.currentTime - fromTs(master)
      setTime(t)
      if (t >= duration) { setAll(x => x.pause()); setPlaying(false) }
      videoKeys.slice(1).forEach(k => {
        const o = videoRefs.current[k]
        if (o && Math.abs((o.currentTime - fromTs(k)) - t) > 0.12) {
          o.currentTime = fromTs(k) + t
        }
      })
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [master, ep, duration, videoKeys.join()])

  // --- segments -----------------------------------------------------------
  const curFrame = Math.round(time * fps)

  const markStart = () => { if (!locked) setMarkIn(curFrame) }
  const markEnd = () => {
    if (locked || markIn === null || curFrame <= markIn) return
    setSegments(sg => [...sg, { start_frame: markIn, end_frame: curFrame, text: '', skill: '' }]
      .sort((a, b) => a.start_frame - b.start_frame))
    setMarkIn(null)
    setDirty(true)
  }
  const updateSeg = (i, patch) => {
    setSegments(sg => sg.map((x, j) => j === i ? { ...x, ...patch } : x))
    setDirty(true)
  }
  const removeSeg = (i) => { setSegments(sg => sg.filter((_, j) => j !== i)); setDirty(true) }

  const save = async () => {
    const e = await api.saveLabels(eid, {
      pass_status: passStatus, task_text: taskText,
      failure_reason: failureReason,
      recorder_id: recorderId ? +recorderId : 0,
      recorded_at: recordedAt, robot_serial: robotSerial,
      segments: segments.map(({ start_frame, end_frame, text, skill }) =>
        ({ start_frame, end_frame, text, skill })),
    }).catch(e2 => { setErr(e2.message); return null })
    if (!e) return false
    setSegments(e.segments)
    setDirty(false)
    setErr('')
    setSavedMsg('저장됨 ✓')
    setTimeout(() => setSavedMsg(''), 2000)
    return true
  }

  const doReview = async (action, note = '') => {
    if (action === 'submit' && dirty && !(await save())) return
    try {
      const e = await api.review(eid, { action, user_id: me?.id || null, note })
      applyEp(e)
      setErr('')
    } catch (e2) { setErr(e2.message) }
  }

  // --- keyboard shortcuts -------------------------------------------------
  useEffect(() => {
    const on = (ev) => {
      if (ev.target.tagName === 'INPUT' || ev.target.tagName === 'TEXTAREA') return
      if (ev.code === 'Space') { ev.preventDefault(); togglePlay() }
      else if (ev.key === 'ArrowLeft') seek(time - (ev.shiftKey ? 1 : 1 / fps))
      else if (ev.key === 'ArrowRight') seek(time + (ev.shiftKey ? 1 : 1 / fps))
      else if (ev.key === 'i' || ev.key === 'I') markStart()
      else if (ev.key === 'o' || ev.key === 'O') markEnd()
    }
    window.addEventListener('keydown', on)
    return () => window.removeEventListener('keydown', on)
  }, [togglePlay, seek, time, fps, markIn, curFrame, locked])

  const chart = useMemo(() => {
    if (!ts) return null
    const src = showAction ? ts.action : ts.state
    return dims.map(d => ({
      name: ts.names[d], color: COLORS[d % COLORS.length],
      values: src.map(row => row[d]),
    }))
  }, [ts, dims, showAction])

  const crumbs = [
    { label: 'Project Center', href: '#/projects' },
    ...(ep ? [
      { label: ep.project || `#${ep.project_id}`, href: `#/p/${ep.project_id}` },
      { label: 'Episodes', href: `#/p/${ep.project_id}/episodes${ep.job_id ? '/' + ep.job_id : ''}` },
      { label: `ep ${ep.episode_index}` },
    ] : [{ label: `episode #${eid}` }]),
  ]

  if (!ep) {
    return (
      <>
        <PageHead crumbs={crumbs} />
        <div className="page">{err ? <div className="error">{err}</div> : 'loading…'}</div>
      </>
    )
  }

  return (
    <>
      <PageHead crumbs={crumbs} />
      <div className="page wide">
        <div className="row spread" style={{ marginBottom: 8 }}>
          <div className="row">
            <StatusChip map={REVIEW_STATUS} value={reviewStatus} />
            <span className="muted small">{ep.length} frames · {fps}fps · {ep.robot_model || 'robot?'}
              {robotSerial && ` · S/N ${robotSerial}`}</span>
          </div>
          <div className="row">
            {savedMsg && <span className="ok">{savedMsg}</span>}
            {dirty && !locked && <span className="warn">저장 안 됨</span>}
            {!locked && <button className="primary" onClick={save}>저장</button>}
            {(reviewStatus === 'unlabeled' || reviewStatus === 'rejected') &&
              <button onClick={() => doReview('submit')}>레이블 완료로 제출 →</button>}
            {reviewStatus === 'labeled' && (
              <>
                <button className="accept" disabled={!me} title={me ? '' : '우측 상단에서 프로필을 선택하세요'}
                  onClick={() => doReview('accept')}>✓ Accept</button>
                <button className="reject" disabled={!me} title={me ? '' : '우측 상단에서 프로필을 선택하세요'}
                  onClick={() => { setRejectNote(''); setRejecting(true) }}>✗ Reject</button>
              </>
            )}
            {locked && <button className="small" onClick={() => doReview('reopen')}>reopen</button>}
          </div>
        </div>

        {err && <div className="error" onClick={() => setErr('')}>{err}</div>}
        {locked && (
          <div className="notice">🔒 Done 상태입니다 — 보기만 가능합니다. 수정하려면 reopen 하세요.
            {reviewer && <span className="muted"> (리뷰: {reviewer})</span>}
          </div>
        )}
        {reviewStatus === 'rejected' && (
          <div className="error">반려됨{reviewer ? ` (리뷰: ${reviewer})` : ''}{reviewNote ? ` — ${reviewNote}` : ''} · 수정 후 다시 제출하세요.</div>
        )}

        <div className="video-grid" data-count={videoKeys.length}>
          {videoKeys.map(k => (
            <figure key={k}>
              <video
                ref={el => { videoRefs.current[k] = el }}
                src={`/api/episodes/${eid}/video/${k}`}
                preload="auto" muted playsInline
                onLoadedMetadata={e => { e.target.currentTime = fromTs(k) }}
                onClick={togglePlay}
              />
              <figcaption>{k.replace('observation.images.', '')}</figcaption>
            </figure>
          ))}
        </div>

        <div className="controls row">
          <button onClick={togglePlay}>{playing ? '⏸' : '▶'}</button>
          <button onClick={() => seek(time - 1 / fps)}>⏮ frame</button>
          <button onClick={() => seek(time + 1 / fps)}>frame ⏭</button>
          <select value={speed} onChange={e => setSpeed(+e.target.value)}>
            {[0.25, 0.5, 1, 1.5, 2, 4].map(s => <option key={s} value={s}>{s}×</option>)}
          </select>
          <span className="mono">{Math.max(0, time).toFixed(2)}s / {duration.toFixed(2)}s · frame {Math.max(0, curFrame)}</span>
          <span className="muted small">Space 재생 · ←/→ 프레임{!locked && ' · I 구간시작 · O 구간끝'}</span>
        </div>

        {ts && (
          <Timeline
            chart={chart} frames={ts.frames} length={ep.length} fps={fps}
            time={time} segments={segments} markIn={markIn}
            onSeek={seek}
          />
        )}

        {ts && (
          <div className="dim-select row">
            <label className="row small">
              <input type="checkbox" checked={showAction} onChange={e => setShowAction(e.target.checked)} />
              action 표시 (기본: state)
            </label>
            {ts.names.map((n, i) => (
              <label key={i} className="dim-chip" style={{ '--c': COLORS[i % COLORS.length] }}>
                <input type="checkbox" checked={dims.includes(i)}
                  onChange={e => setDims(d => e.target.checked ? [...d, i] : d.filter(x => x !== i))} />
                {n}
              </label>
            ))}
          </div>
        )}

        <div className="cols">
          <section className="panel">
            <h2>에피소드 레이블</h2>
            <div className="row">
              <button disabled={locked} className={`pass ${passStatus === 'pass' ? 'active' : ''}`}
                onClick={() => { setPassStatus('pass'); setDirty(true) }}>PASS</button>
              <button disabled={locked} className={`nonpass ${passStatus === 'non_pass' ? 'active' : ''}`}
                onClick={() => { setPassStatus('non_pass'); setDirty(true) }}>NON-PASS</button>
              <button disabled={locked} onClick={() => { setPassStatus('unlabeled'); setDirty(true) }}>초기화</button>
            </div>
            {passStatus === 'non_pass' && (
              <input style={{ marginTop: 8, width: '100%' }} disabled={locked}
                placeholder="실패 사유 (failure reason)"
                value={failureReason} onChange={e => { setFailureReason(e.target.value); setDirty(true) }} />
            )}
            <textarea rows={2} style={{ marginTop: 8 }} disabled={locked}
              placeholder="에피소드 대표 instruction (예: pick up the cup and place it on the tray)"
              value={taskText} onChange={e => { setTaskText(e.target.value); setDirty(true) }} />
            <div className="row" style={{ marginTop: 8 }}>
              <label className="row small muted">Recorder
                <select disabled={locked} value={recorderId}
                  onChange={e => { setRecorderId(e.target.value); setDirty(true) }}>
                  <option value="">—</option>
                  {users.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}
                </select>
              </label>
              <label className="row small muted">수집일
                <input type="date" disabled={locked} value={recordedAt}
                  onChange={e => { setRecordedAt(e.target.value); setDirty(true) }} />
              </label>
              <label className="row small muted">S/N
                <input style={{ width: 120 }} disabled={locked} placeholder="로봇 S/N" value={robotSerial}
                  onChange={e => { setRobotSerial(e.target.value); setDirty(true) }} />
              </label>
            </div>
          </section>

          <section className="panel">
            <h2>구간 레이블 <span className="muted">({segments.length})</span>
              {markIn !== null && <span className="warn small"> 시작 마킹: frame {markIn} — O로 구간 확정</span>}
            </h2>
            {segments.map((sg, i) => (
              <div key={i} className="seg-row">
                <button className="small" onClick={() => seek(sg.start_frame / fps)}>▶</button>
                <span className="mono small">{sg.start_frame}–{sg.end_frame}</span>
                <input className="grow" placeholder="구간 텍스트 (VLA instruction)" disabled={locked}
                  value={sg.text} onChange={e => updateSeg(i, { text: e.target.value })} />
                <input className="skill" placeholder="skill" disabled={locked}
                  value={sg.skill} onChange={e => updateSeg(i, { skill: e.target.value })} />
                {!locked && <button className="small danger" onClick={() => removeSeg(i)}>✕</button>}
              </div>
            ))}
            {segments.length === 0 && !locked &&
              <p className="muted small">영상 위치에서 I(시작)·O(끝)로 구간을 추가하세요.</p>}
          </section>
        </div>
      </div>

      {rejecting && (
        <Modal title="반려 (Reject)" onClose={() => setRejecting(false)} footer={
          <>
            <button onClick={() => setRejecting(false)}>취소</button>
            <button className="reject" onClick={() => { setRejecting(false); doReview('reject', rejectNote) }}>반려</button>
          </>
        }>
          <Field label="반려 사유">
            <textarea rows={3} autoFocus value={rejectNote} onChange={e => setRejectNote(e.target.value)}
              placeholder="작업자에게 전달할 사유" />
          </Field>
        </Modal>
      )}
    </>
  )
}
