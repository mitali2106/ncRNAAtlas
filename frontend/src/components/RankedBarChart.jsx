import { Table2, BarChart3 } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Bar, BarChart, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

/**
 * Horizontal ranked bar chart (single measure) with hover tooltip, direct value
 * labels and a table view. Bars may carry an entity color (e.g. RNA type) that
 * follows the entity, never its rank; a legend is rendered whenever colors encode
 * a category.
 */
export default function RankedBarChart({ rows, valueKey, nameKey, linkPrefix, valueLabel, colorFor, legend }) {
  const [asTable, setAsTable] = useState(false)
  const height = Math.max(160, rows.length * 30 + 24)

  return (
    <div className="chart">
      <div className="chart-toolbar">
        {legend && (
          <ul className="legend" aria-label="Legend">
            {legend.map(([name, color]) => (
              <li key={name}>
                <span className="swatch" style={{ background: color }} aria-hidden /> {name}
              </li>
            ))}
          </ul>
        )}
        <button type="button" className="btn btn-small btn-ghost" onClick={() => setAsTable((t) => !t)}>
          {asTable ? <BarChart3 size={14} aria-hidden /> : <Table2 size={14} aria-hidden />}
          {asTable ? 'Chart view' : 'Table view'}
        </button>
      </div>
      {asTable ? (
        <table className="table compact">
          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col" className="num">
                {valueLabel}
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>
                  <Link to={`${linkPrefix}/${r.id}`}>{r[nameKey]}</Link>
                </td>
                <td className="num">{r[valueKey].toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div style={{ width: '100%', height }} role="img" aria-label={`${valueLabel} by ${nameKey}`}>
          <ResponsiveContainer>
            <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 40, bottom: 4, left: 8 }} barCategoryGap={6}>
              <XAxis type="number" hide />
              <YAxis
                type="category"
                dataKey={nameKey}
                width={190}
                tickLine={false}
                axisLine={false}
                tick={{ fill: '#3f4a59', fontSize: 12 }}
                tickFormatter={(v) => (v.length > 28 ? `${v.slice(0, 27)}…` : v)}
              />
              <Tooltip
                cursor={{ fill: 'rgba(18,53,91,0.06)' }}
                formatter={(v) => [v.toLocaleString(), valueLabel]}
                contentStyle={{ borderRadius: 8, border: '1px solid #d8dee6', fontSize: 13 }}
              />
              <Bar dataKey={valueKey} radius={[0, 4, 4, 0]} maxBarSize={18} isAnimationActive={false}>
                {rows.map((r) => (
                  <Cell key={r.id} fill={colorFor ? colorFor(r) : '#2a78d6'} />
                ))}
                <LabelList dataKey={valueKey} position="right" style={{ fill: '#3f4a59', fontSize: 12 }} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}
