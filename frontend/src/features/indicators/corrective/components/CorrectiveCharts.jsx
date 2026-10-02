import {
  Bar, BarChart, CartesianGrid, Legend, Line, LineChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'

export default function CorrectiveCharts({ analystSeries, monthlySeries }) {
  return (
    <section className="corrective-charts">
      <article className="corrective-chart">
        <h3>Chamados por analistas</h3>
        {analystSeries.length === 0 ? (
          <p className="corrective-empty">Sem dados para o filtro atual.</p>
        ) : (
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={analystSeries}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(5,56,98,0.12)" />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} interval={0} angle={-20} textAnchor="end" height={60} />
              <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="total" name="Chamados" fill="#2f6fb3" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </article>

      <article className="corrective-chart">
        <h3>Chamados concluídos x chamados totais</h3>
        {monthlySeries.length === 0 ? (
          <p className="corrective-empty">Sem dados para o filtro atual.</p>
        ) : (
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={monthlySeries}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(5,56,98,0.12)" />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="total" name="Total" stroke="#2f6fb3" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="concluidos" name="Concluídos" stroke="#1f9d6b" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </article>
    </section>
  )
}
