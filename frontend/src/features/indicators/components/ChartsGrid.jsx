import { CategoryTreemapCard } from './charts/CategoryTreemapCard';
import { RegionVolumeCard } from './charts/RegionVolumeCard';
import { ExecutiveSummary } from './ExecutiveSummary';
export const ChartsGrid = ({ regions, categoryTree, executiveSummary }) => {
    return (<section className="charts-grid">
      <RegionVolumeCard regions={regions}/>
      <article className="chart-card chart-card--wide">
        <ExecutiveSummary summary={executiveSummary}/>
      </article>
      <CategoryTreemapCard categoryTree={categoryTree}/>
    </section>);
};
