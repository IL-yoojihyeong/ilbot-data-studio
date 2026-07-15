import React from 'react'

// Right slide-over panel (Genie Studio "Add Object" pattern)
export function Drawer({ title, onClose, children, footer, width = 620 }) {
  return (
    <div className="overlay" onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}>
      <div className="drawer" style={{ width }}>
        <div className="drawer-head">
          <h3>{title}</h3>
          <button className="icon" onClick={onClose}>✕</button>
        </div>
        <div className="drawer-body">{children}</div>
        {footer && <div className="drawer-foot">{footer}</div>}
      </div>
    </div>
  )
}

// Centered popup for confirmations / short inputs
export function Modal({ title, onClose, children, footer }) {
  return (
    <div className="overlay center" onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}>
      <div className="modal">
        <div className="drawer-head">
          <h3>{title}</h3>
          <button className="icon" onClick={onClose}>✕</button>
        </div>
        <div className="drawer-body">{children}</div>
        {footer && <div className="drawer-foot">{footer}</div>}
      </div>
    </div>
  )
}

// Drawer form row: right-aligned label on the left, control on the right
export function Field({ label, required, children }) {
  return (
    <div className="field">
      <label>{required && <em>*</em>}{label}:</label>
      <div className="field-ctl">{children}</div>
    </div>
  )
}

// Filter-grid cell: bold label above the control
export function FField({ label, children }) {
  return (
    <div className="ffield">
      <label>{label}</label>
      {children}
    </div>
  )
}

export function Section({ title, children, right }) {
  return (
    <section className="panel">
      <div className="row spread" style={{ marginBottom: title ? 0 : 8 }}>
        {title && <div className="section-title">{title}</div>}
        {right}
      </div>
      {children}
    </section>
  )
}

export function Chip({ kind, children }) {
  return <span className={`chip ${kind}`}>{children}</span>
}

// Single-choice click chips (project Usage / robot Type / Difficulty)
export function ChoiceChips({ options, value, onChange }) {
  return (
    <div className="state-chips" style={{ margin: '4px 0 0' }}>
      {options.map(o => (
        <button key={o} type="button" className={value === o ? 'active' : ''}
          onClick={() => onChange(value === o ? '' : o)}>{o}</button>
      ))}
    </div>
  )
}

export const PROJECT_USAGES = ['Testing', 'Formal', 'R&D']
export const ROBOT_TYPES = ['G2', 'G2_Omnihand2025', 'G2_Omnipicker2025',
  'X2_Omnihand2025', 'X2_Omnipicker2025']
export const PROJECT_DIFFICULTIES = ['easy', 'middle', 'high']
export const DIFFICULTY_KIND = { easy: 'green', middle: 'orange', high: 'red' }

export const PROJECT_STATUS = {
  active: ['진행 중', 'orange'],
  completed: ['완료', 'green'],
  archived: ['보관', 'gray'],
}
export const REVIEW_STATUS = {
  unlabeled: ['미작업', 'gray'],
  labeled: ['리뷰 대기', 'orange'],
  rejected: ['반려', 'red'],
  done: ['Done', 'green'],
}
export const PASS_STATUS = {
  unlabeled: ['—', 'gray'],
  pass: ['Pass', 'green'],
  non_pass: ['Fail', 'red'],
}

export function StatusChip({ map, value }) {
  const [label, kind] = map[value] || [value, 'gray']
  return <Chip kind={kind}>{label}</Chip>
}

export function Empty({ text = 'No data' }) {
  return (
    <div className="empty">
      <div className="pic">📂</div>
      <div>{text}</div>
    </div>
  )
}

export function Pager({ total }) {
  return <div className="pager"><span>Total {total}</span></div>
}

// Confirm popup replacing window.confirm
export function ConfirmModal({ title = '확인', text, confirmLabel = '삭제', danger = true, onConfirm, onClose }) {
  return (
    <Modal title={title} onClose={onClose} footer={
      <>
        <button onClick={onClose}>취소</button>
        <button className={danger ? 'reject' : 'primary'} onClick={() => { onConfirm(); onClose() }}>{confirmLabel}</button>
      </>
    }>
      <p style={{ margin: 0 }}>{text}</p>
    </Modal>
  )
}
