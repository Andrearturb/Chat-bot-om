import { ResponsiveContainer, Tooltip, Treemap } from 'recharts';
import './categoryTreemap.css';
const CATEGORY_COLORS = [
    '#1D5FAF',
    '#0F8F83',
    '#7C5FD6',
    '#D89A16',
    '#D94F5C',
    '#2AA198',
    '#64748B',
];
const formatPercent = (value) => typeof value === 'number' ? `${value.toFixed(1).replace('.', ',')}%` : '-';
const formatNumber = (value) => typeof value === 'number' ? value.toLocaleString('pt-BR') : '-';
const getCategoryHeaderLabel = (name, width) => {
    const maxLength = width >= 220 ? 28 : width >= 150 ? 22 : 16;
    return name.length > maxLength ? `${name.slice(0, maxLength - 1)}…` : name;
};
const getSmartTruncatedLabel = (label, maxLength) => {
    const normalized = label.replace(/\s+/g, ' ').trim();
    if (normalized.length <= maxLength)
        return normalized;
    const slice = normalized.slice(0, Math.max(1, maxLength - 1));
    const cutIndex = Math.max(slice.lastIndexOf(' '), slice.lastIndexOf('/'));
    if (cutIndex > 4) {
        return `${slice.slice(0, cutIndex).trim()}…`;
    }
    return `${slice.trimEnd()}…`;
};
const getSubcategoryTextMode = (width, height) => {
    const area = width * height;
    if (width <= 55 || height <= 40 || area <= 1800)
        return 'hidden';
    if (width > 140 && height > 90 && area > 13000)
        return 'full';
    if (width > 90 && height > 60 && area > 6000)
        return 'medium';
    return 'compact';
};
const getVisibleSubcategoryCount = (categoryShare) => {
    if (categoryShare >= 20)
        return 3;
    if (categoryShare >= 10)
        return 2;
    if (categoryShare >= 5)
        return 1;
    return 0;
};
const buildCategoryChildren = (category, color) => {
    const visibleCount = getVisibleSubcategoryCount(category.shareOfTotal);
    const sortedChildren = [...(category.children ?? [])].sort((a, b) => b.value - a.value);
    const visibleChildren = sortedChildren.slice(0, visibleCount);
    const hiddenChildren = sortedChildren.slice(visibleCount);
    const result = visibleChildren.map((child, childIndex) => ({
        ...child,
        fill: `${color}${childIndex === 0 ? '28' : childIndex === 1 ? '20' : '16'}`,
        stroke: 'rgba(255,255,255,0.9)',
    }));
    if (hiddenChildren.length > 0) {
        const hiddenValue = hiddenChildren.reduce((sum, item) => sum + item.value, 0);
        const hiddenShareOfTotal = hiddenChildren.reduce((sum, item) => sum + item.shareOfTotal, 0);
        const hiddenShareOfCategory = hiddenChildren.reduce((sum, item) => sum + item.shareOfCategory, 0);
        result.push({
            name: 'Outras subcategorias',
            category: category.category,
            subcategory: 'Outras subcategorias',
            value: hiddenValue,
            total: hiddenValue,
            shareOfCategory: hiddenShareOfCategory,
            shareOfTotal: hiddenShareOfTotal,
            fill: `${color}10`,
            stroke: 'rgba(255,255,255,0.72)',
        });
    }
    return result;
};
const transformValueForLayout = (value) => {
    // Use square root to maintain order but reduce proportionality
    return Math.sqrt(value);
};
const buildExecutiveTreemap = (tree) => {
    const sortedCategories = [...tree].sort((a, b) => b.value - a.value);
    const mainCategories = sortedCategories.filter((c) => c.shareOfTotal >= 5);
    const smallCategories = sortedCategories.filter((c) => c.shareOfTotal < 5);
    const result = mainCategories.map((category, index) => {
        const color = CATEGORY_COLORS[index % CATEGORY_COLORS.length];
        return {
            ...category,
            fill: color,
            value: transformValueForLayout(category.value),
            children: buildCategoryChildren(category, color).map((child) => ({
                ...child,
                value: transformValueForLayout(child.value),
            })),
        };
    });
    if (smallCategories.length > 0) {
        const othersValue = smallCategories.reduce((sum, item) => sum + item.value, 0);
        const othersTotal = smallCategories.reduce((sum, item) => sum + item.total, 0);
        const othersShareOfTotal = smallCategories.reduce((sum, item) => sum + item.shareOfTotal, 0);
        result.push({
            name: 'Outras',
            category: 'Outras',
            value: transformValueForLayout(othersValue),
            total: othersTotal,
            shareOfCategory: 100,
            shareOfTotal: othersShareOfTotal,
            fill: '#94A3B8',
            stroke: '#E2E8F0',
            isOtherCategory: true,
        });
    }
    return result;
};
const TreemapTooltip = ({ active, payload, }) => {
    if (!active || !payload?.length || !payload[0]?.payload)
        return null;
    const node = payload[0].payload;
    const isSubcategory = Boolean(node.subcategory);
    return (<div className="category-treemap-tooltip">
      <div className="category-treemap-tooltip__title">
        {isSubcategory ? node.subcategory : node.category ?? node.name}
      </div>

      {isSubcategory && (<div className="category-treemap-tooltip__row">
          <span>Categoria</span>
          <strong>{node.category}</strong>
        </div>)}

      <div className="category-treemap-tooltip__row">
        <span>Chamados</span>
        <strong className="category-treemap-tooltip__value--primary">
          {formatNumber(node.total ?? node.value)}
        </strong>
      </div>

      {isSubcategory && (<div className="category-treemap-tooltip__row">
          <span>% da categoria</span>
          <strong>{formatPercent(node.shareOfCategory)}</strong>
        </div>)}

      <div className="category-treemap-tooltip__row">
        <span>% do total</span>
        <strong>{formatPercent(node.shareOfTotal)}</strong>
      </div>
    </div>);
};
const TreemapCell = (props) => {
    const { x = 0, y = 0, width = 0, height = 0, depth = 1, name = '', value = 0, total = 0, shareOfTotal = 0, fill = '#E8F1FA', subcategory, isOtherCategory, } = props;
    if (width < 46 || height < 34)
        return null;
    const isCategory = depth === 1 && !subcategory;
    const isSubcategory = depth >= 2 || Boolean(subcategory);
    const label = subcategory ?? name;
    if (isOtherCategory) {
        const headerHeight = 26;
        const bodyValue = formatNumber(total ?? value);
        const bodyShare = formatPercent(shareOfTotal);
        return (<g>
        <rect x={x} y={y} width={width} height={height} fill="#E5E7EB" stroke="none" rx={14} ry={14}/>

        <rect x={x} y={y} width={width} height={headerHeight} fill="#64748B" stroke="none" rx={0} ry={0}/>

        {/* faixa para esconder os cantos inferiores arredondados do header */}
        <rect x={x} y={y + headerHeight} width={width} height={14} fill="#E5E7EB" stroke="none"/>

        <text x={x + 10} y={y + 17} fill="#ffffff" fontSize={10} fontWeight={700} pointerEvents="none">
          Outras categorias
        </text>

        <text x={x + width - 10} y={y + 17} fill="#ffffff" fontSize={9} fontWeight={700} textAnchor="end" opacity={0.95} pointerEvents="none">
          {formatPercent(shareOfTotal)}
        </text>

        <text x={x + width / 2} y={y + headerHeight + (height - headerHeight) / 2 - 4} fill="#0f172a" textAnchor="middle" pointerEvents="none">
          <tspan x={x + width / 2} fontSize={22} fontWeight={900}>
            {bodyValue}
          </tspan>
          <tspan x={x + width / 2} dy="24" fontSize={11} fontWeight={600}>
            {bodyShare} do total
          </tspan>
        </text>
      </g>);
    }
    if (isCategory) {
        const headerHeight = 34;
        const labelText = getCategoryHeaderLabel(label, width);
        const categoryValue = formatNumber(total ?? value);
        const categoryShare = formatPercent(shareOfTotal);
        return (<g>
        <rect x={x} y={y} width={width} height={height} fill="#f8f8f8" stroke="none" rx={14} ry={14}/>

        <rect x={x} y={y} width={width} height={headerHeight} fill={fill} stroke="none" rx={0} ry={0}/>

        {/* faixa para esconder os cantos inferiores arredondados do header */}
        <rect x={x} y={y + headerHeight} width={width} height={14} fill="#f8f8f8" stroke="none"/>

        {width >= 92 && height >= 34 && (<text x={x + 12} y={y + 14} fill="#ffffff" fontSize={11} fontWeight={700} pointerEvents="none">
            {labelText}
          </text>)}

        {width >= 92 && height >= 34 && (<text x={x + 12} y={y + 27} fill="#ffffff" fontSize={9.5} fontWeight={600} opacity={0.92} pointerEvents="none">
            {categoryValue} • {categoryShare}
          </text>)}
      </g>);
    }
    if (!isSubcategory)
        return null;
    const subcategoryMode = getSubcategoryTextMode(width, height);
    if (subcategoryMode === 'hidden') {
        return (<g>
        <rect x={x} y={y} width={width} height={height} fill={fill} stroke="none" rx={0} ry={0}/>
      </g>);
    }
    const categoryLabel = label;
    const compactLabel = getSmartTruncatedLabel(categoryLabel, width >= 130 ? 24 : width >= 110 ? 18 : 14);
    return (<g>
      <rect x={x} y={y} width={width} height={height} fill={fill} stroke="none" rx={0} ry={0}/>

      {subcategoryMode === 'full' && (<text x={x + 12} y={y + 62} fill="#0f172a" fontSize={11} fontWeight={700} pointerEvents="none">
          <tspan x={x + 12}>{label.substring(0, 22)}</tspan>
          <tspan x={x + 12} dy="21" fontSize={17} fontWeight={900}>
            {formatNumber(total ?? value)}
          </tspan>
          <tspan x={x + 12} dy="15" fontSize={10} fontWeight={600}>
            {formatPercent(shareOfTotal)}
          </tspan>
        </text>)}

      {subcategoryMode === 'medium' && (<text x={x + 12} y={y + 50} fill="#0f172a" fontSize={9} fontWeight={700} pointerEvents="none">
          <tspan x={x + 12}>{compactLabel}</tspan>
          <tspan x={x + 12} dy={17} fontSize={15} fontWeight={900}>
            {formatNumber(total ?? value)}
          </tspan>
        </text>)}

      {subcategoryMode === 'compact' && (<text x={x + width / 2} y={y + height / 2} fill="#0f172a" textAnchor="middle" dominantBaseline="middle" fontSize={15} fontWeight={900} pointerEvents="none" opacity={0.98}>
          {formatNumber(total ?? value)}
        </text>)}
    </g>);
};
export const CategoryTreemapCard = ({ categoryTree }) => {
    const data = buildExecutiveTreemap(categoryTree);
    return (<article className="chart-card chart-card--wide chart-card--treemap">
      <div className="chart-header">
        <div>
          <p className="indicators-eyebrow">Categorias</p>
          <h3>Categorias e Subcategorias com mais chamados</h3>
          <p className="muted chart-subtitle">
            Hierarquia executiva por categoria e subcategoria
          </p>
        </div>
      </div>

      <section className="treemap-shell">
        <ResponsiveContainer width="100%" height={580}>
          <Treemap data={data} dataKey="value" nameKey="name" aspectRatio={2.8} content={<TreemapCell />} isAnimationActive={false}>
            <Tooltip content={<TreemapTooltip />}/>
          </Treemap>
        </ResponsiveContainer>
      </section>

      <div className="treemap-legendless-note">
        Cada grupo representa uma categoria. Os blocos internos representam subcategorias,
        com tamanho proporcional ao volume de chamados.
      </div>
    </article>);
};
