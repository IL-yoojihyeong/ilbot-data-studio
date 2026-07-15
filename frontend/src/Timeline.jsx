import React, { useRef } from 'react'

// SVG timeline: joint curves + playhead + segment track. Click/drag to seek.
export default function Timeline({ chart, frames, length, fps, time, segments, markIn, onSeek }) {
  const W = 1200, H = 220, SEG_H = 26, PAD = 4
  const plotH = H - SEG_H - PAD
  const svgRef = useRef(null)

  const all = chart.flatMap(c => c.values)
  const min = Math.min(...all), max = Math.max(...all)
  const span = max - min || 1
  const x = (frame) => (frame / Math.max(1, length - 1)) * W
  const y = (v) => plotH - ((v - min) / span) * (plotH - 8) - 4

  const pathFor = (c) =>
    c.values.map((v, i) => `${i ? 'L' : 'M'}${x(frames[i]).toFixed(1)},${y(v).toFixed(1)}`).join('')

  const seekFromEvent = (e) => {
    const rect = svgRef.current.getBoundingClientRect()
    const fx = ((e.clientX - rect.left) / rect.width) * (length - 1)
    onSeek(fx / fps)
  }
  const onMouseDown = (e) => {
    seekFromEvent(e)
    const move = (ev) => seekFromEvent(ev)
    const up = () => { window.removeEventListener('mousemove', move); window.removeEventListener('mouseup', up) }
    window.addEventListener('mousemove', move)
    window.addEventListener('mouseup', up)
  }

  const playX = x(time * fps)

  return (
    <svg ref={svgRef} className="timeline" viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="none" onMouseDown={onMouseDown}>
      <rect x="0" y="0" width={W} height={plotH} className="tl-bg" />
      {chart.map((c, i) => (
        <path key={i} d={pathFor(c)} fill="none" stroke={c.color} strokeWidth="1.2" />
      ))}

      {/* segment track */}
      <rect x="0" y={plotH + PAD} width={W} height={SEG_H} className="tl-seg-bg" />
      {segments.map((sg, i) => (
        <g key={i}>
          <rect x={x(sg.start_frame)} y={plotH + PAD}
            width={Math.max(2, x(sg.end_frame) - x(sg.start_frame))} height={SEG_H}
            className="tl-seg" />
          <text x={x(sg.start_frame) + 4} y={plotH + PAD + SEG_H / 2 + 4}
            className="tl-seg-text">{sg.text || `#${i + 1}`}</text>
        </g>
      ))}
      {markIn !== null && (
        <line x1={x(markIn)} x2={x(markIn)} y1="0" y2={H} className="tl-markin" />
      )}
      <line x1={playX} x2={playX} y1="0" y2={H} className="tl-playhead" />
    </svg>
  )
}
