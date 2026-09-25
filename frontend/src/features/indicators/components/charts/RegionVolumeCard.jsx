import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis, } from 'recharts';
const sortRegionsByVolume = (regions) => [...regions].sort((left, right) => right.volume - left.volume);
const RegionTooltip = ({ active, payload, }) => {
    if (!active || !payload?.length || !payload[0]?.payload) {
        return null;
    }
    const region = payload[0].payload;
    return (<div className="chart-tooltip chart-tooltip--executive">
      <div className="chart-tooltip__title">{region.region}</div>

      <div className="chart-tooltip__row">
        <span className="chart-tooltip__label">Volume:</span>
        <strong className="chart-tooltip__value chart-tooltip__value--volume">
          {region.volume}
        </strong>
      </div>

      <div className="chart-tooltip__row">
        <span className="chart-tooltip__label">Concluídos:</span>
        <strong className="chart-tooltip__value chart-tooltip__value--concluded">
          {region.concluded}
        </strong>
      </div>

      <div className="chart-tooltip__row">
        <span className="chart-tooltip__label">Taxa de conclusão:</span>
        <strong className="chart-tooltip__value chart-tooltip__value--rate">
          {region.completionRate.toFixed(0)}%
        </strong>
      </div>
    </div>);
};
export const RegionVolumeCard = ({ regions }) => {
    const totalVolume = regions.reduce((sum, r) => sum + r.volume, 0);
    const totalConcluded = regions.reduce((sum, r) => sum + r.concluded, 0);
    return (<article className="chart-card chart-card--wide">
      <div className="chart-header">
        <div>
          <p className="indicators-eyebrow">Região</p>
          <h3>Volume e conclusão por praça</h3>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={320}>
        <BarChart data={sortRegionsByVolume(regions)} barCategoryGap="26%" barGap={10} margin={{ top: 10, right: 18, bottom: 34, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(5,56,98,0.08)" vertical={false}/>

          <XAxis dataKey="region" interval={0} tickLine={false} axisLine={{
            stroke: 'rgba(5,56,98,0.22)',
            strokeWidth: 1.2,
        }} tickMargin={12} height={68} angle={-18} textAnchor="end" tick={{
            fill: '#0f172a',
            fontSize: 11,
            fontWeight: 500,
        }}/>

          <YAxis tickLine={false} axisLine={{
            stroke: 'rgba(5,56,98,0.22)',
            strokeWidth: 1.2,
        }} tick={{
            fill: '#0f172a',
            fontSize: 12,
            fontWeight: 500,
        }} width={44}/>

          <Tooltip content={<RegionTooltip />}/>

          <Legend wrapperStyle={{ paddingTop: 8 }}/>

          <Bar dataKey="volume" name="Volume" fill="#082B5B" radius={[8, 8, 0, 0]}/>

          <Bar dataKey="concluded" name="Concluídos" fill="#0C7A75" radius={[8, 8, 0, 0]}/>
        </BarChart>
      </ResponsiveContainer>

      <div className="region-totals">
        <div className="region-totals__item region-totals__item--volume">
          <span className="region-totals__label">Total de volume</span>
          <strong className="region-totals__value">{totalVolume.toLocaleString('pt-BR')}</strong>
        </div>
        <div className="region-totals__item region-totals__item--concluded">
          <span className="region-totals__label">Total de concluídos</span>
          <strong className="region-totals__value">{totalConcluded.toLocaleString('pt-BR')}</strong>
        </div>
      </div>
    </article>);
};
