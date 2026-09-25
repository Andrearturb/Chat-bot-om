import { daysBetween, formatMonthLabel } from './date.js';
export const defaultFilters = {
    query: '',
    region: 'all',
    status: 'all',
    category: 'all',
    provider: 'all',
    analyst: 'all',
    startDate: '',
    endDate: '',
};
export const applyFilters = (records, filters) => records.filter((record) => {
    const normalizedQuery = filters.query.trim().toLowerCase();
    const matchesQuery = !normalizedQuery ||
        [record.ticketId, record.status, record.region, record.category, record.subcategory, record.provider, record.analyst]
            .join(' ')
            .toLowerCase()
            .includes(normalizedQuery);
    const matchesRegion = filters.region === 'all' || record.region === filters.region;
    const matchesStatus = filters.status === 'all' || record.status === filters.status;
    const matchesCategory = filters.category === 'all' || record.category === filters.category;
    const matchesProvider = filters.provider === 'all' || record.provider === filters.provider;
    const matchesAnalyst = filters.analyst === 'all' || record.analyst === filters.analyst;
    const requestDate = record.requestDate ? new Date(record.requestDate) : null;
    const matchesStartDate = !filters.startDate || !requestDate || requestDate >= new Date(filters.startDate);
    const matchesEndDate = !filters.endDate || !requestDate || requestDate <= new Date(`${filters.endDate}T23:59:59.999`);
    return (matchesQuery &&
        matchesRegion &&
        matchesStatus &&
        matchesCategory &&
        matchesProvider &&
        matchesAnalyst &&
        matchesStartDate &&
        matchesEndDate);
});
export const buildMetrics = (records) => {
    const total = records.length;
    const concluded = records.filter((record) => record.statusGroup === 'concluded').length;
    const inProgress = records.filter((record) => record.statusGroup === 'in_progress').length;
    const backlog = records.filter((record) => record.statusGroup === 'backlog').length;
    const rejected = records.filter((record) => record.statusGroup === 'rejected').length;
    const completionRate = total ? (concluded / total) * 100 : 0;
    const slaWithDates = records
        .map((record) => daysBetween(record.requestDate, record.conclusionDate))
        .filter((value) => value !== null);
    const avgSlaDays = slaWithDates.length ? slaWithDates.reduce((sum, value) => sum + value, 0) / slaWithDates.length : 0;
    return {
        total,
        concluded,
        inProgress,
        backlog,
        rejected,
        completionRate,
        avgSlaDays,
    };
};
export const buildRegionSeries = (_records, allRecords, filters) => {
    // volume: chamados criados no período filtrado (coluna BY = createdOn), usando os filtros não-data aplicados
    // concluded: chamados concluídos no período filtrado (coluna J = conclusionDate), mesmos filtros não-data
    // Determina o intervalo de datas do filtro
    const startDate = filters.startDate ? new Date(`${filters.startDate}T00:00:00`) : null;
    const endDate = filters.endDate ? new Date(`${filters.endDate}T23:59:59.999`) : null;
    // Aplica todos os filtros exceto o de data aos allRecords para calcular concluídos por conclusionDate
    const baseRecords = allRecords.filter((record) => {
        const normalizedQuery = filters.query.trim().toLowerCase();
        const matchesQuery = !normalizedQuery ||
            [record.ticketId, record.status, record.region, record.category, record.subcategory, record.provider, record.analyst]
                .join(' ')
                .toLowerCase()
                .includes(normalizedQuery);
        const matchesRegion = filters.region === 'all' || record.region === filters.region;
        const matchesStatus = filters.status === 'all' || record.status === filters.status;
        const matchesCategory = filters.category === 'all' || record.category === filters.category;
        const matchesProvider = filters.provider === 'all' || record.provider === filters.provider;
        const matchesAnalyst = filters.analyst === 'all' || record.analyst === filters.analyst;
        return matchesQuery && matchesRegion && matchesStatus && matchesCategory && matchesProvider && matchesAnalyst;
    });
    // Volume: registros de `records` (já filtrados por data de criação via requestDate em applyFilters)
    // mas usando createdOn para o período quando disponível; caso createdOn seja nulo, cai no requestDate
    // Na prática `records` já é o filteredRecords de applyFilters, mas o filtro de data lá usa requestDate.
    // Aqui recalculamos o volume filtrando por createdOn dentro do intervalo do filtro.
    const volumeRecords = baseRecords.filter((record) => {
        const dateStr = record.createdOn ?? record.requestDate;
        if (!dateStr)
            return false;
        const date = new Date(dateStr);
        if (Number.isNaN(date.getTime()))
            return false;
        if (startDate && date < startDate)
            return false;
        if (endDate && date > endDate)
            return false;
        return true;
    });
    // Concluded: registros de baseRecords cujo conclusionDate cai no período filtrado
    const concludedRecords = baseRecords.filter((record) => {
        if (record.statusGroup !== 'concluded')
            return false;
        const dateStr = record.conclusionDate;
        if (!dateStr)
            return false;
        const date = new Date(dateStr);
        if (Number.isNaN(date.getTime()))
            return false;
        if (startDate && date < startDate)
            return false;
        if (endDate && date > endDate)
            return false;
        return true;
    });
    const accumulator = new Map();
    for (const record of volumeRecords) {
        const current = accumulator.get(record.region) ?? { volume: 0, concluded: 0, inProgress: 0 };
        current.volume += 1;
        accumulator.set(record.region, current);
    }
    for (const record of concludedRecords) {
        const current = accumulator.get(record.region) ?? { volume: 0, concluded: 0, inProgress: 0 };
        current.concluded += 1;
        accumulator.set(record.region, current);
    }
    return [...accumulator.entries()]
        .map(([region, value]) => ({
        region,
        volume: value.volume,
        concluded: value.concluded,
        inProgress: value.inProgress,
        completionRate: value.volume ? (value.concluded / value.volume) * 100 : 0,
    }))
        .sort((left, right) => right.volume - left.volume);
};
export const buildMonthlySeries = (records) => {
    const accumulator = new Map();
    for (const record of records) {
        if (!record.requestDate) {
            continue;
        }
        const monthKey = record.requestDate.slice(0, 7);
        const current = accumulator.get(monthKey) ?? { month: formatMonthLabel(record.requestDate), concluded: 0, inProgress: 0 };
        if (record.statusGroup === 'concluded') {
            current.concluded += 1;
        }
        else if (record.statusGroup === 'in_progress') {
            current.inProgress += 1;
        }
        accumulator.set(monthKey, current);
    }
    return [...accumulator.entries()]
        .map(([monthKey, value]) => ({ monthKey, ...value }))
        .sort((left, right) => left.monthKey.localeCompare(right.monthKey));
};
const buildRank = (records, accessor) => {
    const accumulator = new Map();
    for (const record of records) {
        const label = accessor(record);
        if (!label) {
            continue;
        }
        const current = accumulator.get(label) ?? { volume: 0, concluded: 0, inProgress: 0, days: [] };
        current.volume += 1;
        if (record.statusGroup === 'concluded') {
            current.concluded += 1;
            const days = daysBetween(record.requestDate, record.conclusionDate);
            if (days !== null) {
                current.days.push(days);
            }
        }
        else if (record.statusGroup === 'in_progress') {
            current.inProgress += 1;
        }
        accumulator.set(label, current);
    }
    return [...accumulator.entries()]
        .map(([label, value]) => ({
        label,
        volume: value.volume,
        concluded: value.concluded,
        inProgress: value.inProgress,
        completionRate: value.volume ? (value.concluded / value.volume) * 100 : 0,
        averageDaysToConclusion: value.days.length ? value.days.reduce((sum, day) => sum + day, 0) / value.days.length : null,
    }))
        .sort((left, right) => right.volume - left.volume)
        .slice(0, 10);
};
export const buildProviderRanking = (records) => buildRank(records, (record) => record.provider);
export const buildCategoryRanking = (records) => {
    const ranking = buildRank(records, (record) => `${record.category} • ${record.subcategory}`);
    return ranking.map((item) => ({ label: item.label, volume: item.volume }));
};
const treemapPalette = ['#082B5B', '#0C7A75', '#2F6BFF', '#8B5CF6', '#D98E14', '#D94E4E', '#5E7EA6', '#2EA8A1'];
const toRgba = (hex, alpha) => {
    const normalized = hex.replace('#', '');
    const expanded = normalized.length === 3 ? normalized.split('').map((character) => character + character).join('') : normalized;
    const numeric = Number.parseInt(expanded, 16);
    const red = (numeric >> 16) & 255;
    const green = (numeric >> 8) & 255;
    const blue = numeric & 255;
    return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
};
export const buildCategoryTreemap = (records) => {
    const categories = new Map();
    for (const record of records) {
        const category = record.category || 'Não informado';
        const subcategory = record.subcategory || 'Não informado';
        const current = categories.get(category) ?? { total: 0, subcategories: new Map() };
        current.total += 1;
        current.subcategories.set(subcategory, (current.subcategories.get(subcategory) ?? 0) + 1);
        categories.set(category, current);
    }
    const total = records.length || 1;
    return [...categories.entries()]
        .sort((left, right) => right[1].total - left[1].total)
        .map(([category, value], categoryIndex) => {
        const baseColor = treemapPalette[categoryIndex % treemapPalette.length];
        const categoryNode = {
            name: category,
            category,
            value: value.total,
            total: value.total,
            shareOfCategory: 100,
            shareOfTotal: (value.total / total) * 100,
            fill: toRgba(baseColor, 0.14),
            stroke: toRgba(baseColor, 0.32),
            children: [...value.subcategories.entries()]
                .sort((left, right) => right[1] - left[1])
                .map(([subcategory, count], subcategoryIndex) => ({
                name: subcategory,
                category,
                subcategory,
                value: count,
                total: count,
                shareOfCategory: (count / value.total) * 100,
                shareOfTotal: (count / total) * 100,
                fill: toRgba(baseColor, Math.max(0.28, 0.74 - subcategoryIndex * 0.08)),
                stroke: toRgba(baseColor, 0.45),
            })),
        };
        return categoryNode;
    });
};
const getDateBounds = (records) => {
    const dates = records
        .map((record) => record.requestDate)
        .filter((value) => Boolean(value))
        .map((value) => new Date(value).getTime())
        .filter((value) => !Number.isNaN(value));
    if (!dates.length) {
        return null;
    }
    return {
        start: new Date(Math.min(...dates)),
        end: new Date(Math.max(...dates)),
    };
};
const filterByRange = (records, start, end) => records.filter((record) => {
    if (!record.requestDate) {
        return false;
    }
    const date = new Date(record.requestDate);
    return !Number.isNaN(date.getTime()) && date >= start && date <= end;
});
const buildPeriodRange = (records, filters) => {
    const hasCustomRange = Boolean(filters.startDate || filters.endDate);
    const dataBounds = getDateBounds(records);
    if (!dataBounds) {
        return null;
    }
    if (hasCustomRange) {
        const start = filters.startDate ? new Date(`${filters.startDate}T00:00:00`) : dataBounds.start;
        const end = filters.endDate ? new Date(`${filters.endDate}T23:59:59.999`) : dataBounds.end;
        const spanMs = Math.max(1, end.getTime() - start.getTime());
        const previousEnd = new Date(start.getTime() - 1);
        const previousStart = new Date(previousEnd.getTime() - spanMs);
        return { start, end, previousStart, previousEnd };
    }
    const currentEnd = dataBounds.end;
    const currentStart = new Date(currentEnd.getTime() - 29 * 24 * 60 * 60 * 1000);
    const previousEnd = new Date(currentStart.getTime() - 1);
    const previousStart = new Date(previousEnd.getTime() - 29 * 24 * 60 * 60 * 1000);
    return { start: currentStart, end: currentEnd, previousStart, previousEnd };
};
const formatShare = (value) => `${value.toFixed(1)}%`;
const buildCategoryVolumeMap = (records) => {
    const volumes = new Map();
    for (const record of records) {
        const category = record.category || 'Não informado';
        volumes.set(category, (volumes.get(category) ?? 0) + 1);
    }
    return [...volumes.entries()].sort((left, right) => right[1] - left[1]);
};
export const buildExecutiveSummary = (allRecords, filteredRecords, filters) => {
    const total = filteredRecords.length;
    const categoryBuckets = new Map();
    const subcategoryBuckets = new Map();
    for (const record of filteredRecords) {
        const category = record.category || 'Não informado';
        const subcategory = record.subcategory || 'Não informado';
        categoryBuckets.set(category, (categoryBuckets.get(category) ?? 0) + 1);
        const key = `${category}|||${subcategory}`;
        const current = subcategoryBuckets.get(key) ?? { category, volume: 0 };
        current.volume += 1;
        subcategoryBuckets.set(key, current);
    }
    const sortedCategories = [...categoryBuckets.entries()].sort((left, right) => right[1] - left[1]);
    const sortedSubcategories = [...subcategoryBuckets.entries()].sort((left, right) => right[1].volume - left[1].volume);
    const topCategory = sortedCategories[0]
        ? {
            label: sortedCategories[0][0],
            volume: sortedCategories[0][1],
            shareOfTotal: total ? (sortedCategories[0][1] / total) * 100 : 0,
        }
        : null;
    const topSubcategory = sortedSubcategories[0]
        ? {
            category: sortedSubcategories[0][1].category,
            label: sortedSubcategories[0][0].split('|||')[1],
            volume: sortedSubcategories[0][1].volume,
            shareOfCategory: sortedCategories.length ? (sortedSubcategories[0][1].volume / (categoryBuckets.get(sortedSubcategories[0][1].category) ?? 1)) * 100 : 0,
            shareOfTotal: total ? (sortedSubcategories[0][1].volume / total) * 100 : 0,
        }
        : null;
    const top3CategoriesShare = total
        ? sortedCategories.slice(0, 3).reduce((sum, [, volume]) => sum + volume, 0) / total * 100
        : 0;
    const periodRange = buildPeriodRange(allRecords, filters);
    let trend = null;
    if (periodRange) {
        const currentRecords = filterByRange(allRecords, periodRange.start, periodRange.end);
        const previousRecords = filterByRange(allRecords, periodRange.previousStart, periodRange.previousEnd);
        const currentCategory = buildCategoryVolumeMap(currentRecords)[0];
        const previousCategory = buildCategoryVolumeMap(previousRecords)[0];
        if (currentCategory && previousCategory) {
            const delta = currentCategory[1] - previousCategory[1];
            trend = {
                label: currentCategory[0],
                delta,
                current: currentCategory[1],
                previous: previousCategory[1],
            };
        }
    }
    const concentration = total ? (sortedCategories.slice(0, 3).reduce((sum, [, volume]) => sum + volume, 0) / total) * 100 : 0;
    const insights = [
        topCategory
            ? {
                icon: '◼',
                title: `${topCategory.label} lidera a concentração operacional`,
                description: `${topCategory.label} responde por ${formatShare(topCategory.shareOfTotal)} dos chamados do período (${topCategory.volume} registros).`,
                tone: 'teal',
            }
            : null,
        topSubcategory
            ? {
                icon: '▣',
                title: `${topSubcategory.label} é a subcategoria mais pressionada`,
                description: `${topSubcategory.label} concentra ${topSubcategory.volume} chamados dentro de ${topSubcategory.category}.`,
                tone: 'cyan',
            }
            : null,
        {
            icon: '↗',
            title: 'Concentração das principais categorias',
            description: `As 3 principais categorias concentram ${formatShare(concentration)} dos chamados exibidos no cenário atual.`,
            tone: 'violet',
        },
        trend
            ? {
                icon: trend.delta >= 0 ? '▲' : '▼',
                title: `${trend.label} versus período anterior`,
                description: `${trend.label} registrou ${trend.delta >= 0 ? 'alta' : 'queda'} de ${Math.abs(trend.delta)} chamados em relação ao período anterior.`,
                tone: trend.delta >= 0 ? 'amber' : 'rose',
            }
            : null,
    ].filter(Boolean);
    return {
        total,
        categoryCount: sortedCategories.length,
        subcategoryCount: sortedSubcategories.length,
        concentration,
        topCategory,
        topSubcategory,
        top3CategoriesShare,
        trend,
        insights,
    };
};
export const buildAnalystRanking = (records) => buildRank(records, (record) => record.analyst);
export const buildAnalystProductivity = (records, filters) => {
    // Step 1: only concluded tickets
    const concludedAll = records.filter((r) => r.statusGroup === 'concluded');
    // Step 2: filter by conclusionDate (col J) within the selected period
    const startDate = filters.startDate ? new Date(`${filters.startDate}T00:00:00`) : null;
    const endDate = filters.endDate ? new Date(`${filters.endDate}T23:59:59.999`) : null;
    const concluded = concludedAll.filter((r) => {
        if (!r.conclusionDate)
            return false;
        const d = new Date(r.conclusionDate);
        if (Number.isNaN(d.getTime()))
            return false;
        if (startDate && d < startDate)
            return false;
        if (endDate && d > endDate)
            return false;
        return true;
    });
    const acc = new Map();
    for (const record of concluded) {
        const name = record.analyst || 'Não informado';
        const current = acc.get(name) ?? { concluded: 0, days: [] };
        current.concluded += 1;
        // Duration: col BY (createdOn) → col J (conclusionDate)
        // col H (inAttendanceDate) is NOT used for analysts
        const start = record.createdOn;
        const end = record.conclusionDate;
        if (start && end) {
            const d = daysBetween(start, end);
            // Guard against negative durations (start after end)
            if (d !== null && d >= 0)
                current.days.push(d);
        }
        acc.set(name, current);
    }
    const rows = [...acc.entries()].map(([name, val]) => ({
        name,
        concluded: val.concluded,
        avgDays: val.days.length ? val.days.reduce((s, v) => s + v, 0) / val.days.length : null,
    }));
    if (rows.length === 0)
        return [];
    const avgConcluded = rows.reduce((s, r) => s + r.concluded, 0) / rows.length;
    const validDays = rows.filter((r) => r.avgDays !== null).map((r) => r.avgDays);
    const avgDays = validDays.length ? validDays.reduce((s, v) => s + v, 0) / validDays.length : 0;
    const classify = (r) => {
        const highVol = r.concluded >= avgConcluded;
        // null avgDays = no measurable time → never treated as fast (conservative)
        const fastTime = r.avgDays !== null && r.avgDays <= avgDays;
        if (highVol && fastTime)
            return 'high';
        if (highVol && !fastTime)
            return 'volume';
        if (!highVol && fastTime)
            return 'fast';
        return 'slow';
    };
    return rows
        .map((r) => ({ ...r, classification: classify(r) }))
        .sort((a, b) => b.concluded - a.concluded || (a.avgDays ?? Infinity) - (b.avgDays ?? Infinity));
};
// Removes leading CPF (000.000.000-00) or CNPJ (00.000.000/0000-00) and separator from provider names
export const normalizeSupplierName = (raw) => {
    if (!raw || !raw.trim())
        return 'Sem fornecedor';
    const cleaned = raw
        .trim()
        .replace(/^\d{2,3}\.\d{3}\.\d{3}\/\d{4}-\d{2}\s*[-–]\s*/, '') // CNPJ
        .replace(/^\d{3}\.\d{3}\.\d{3}-\d{2}\s*[-–]\s*/, '') // CPF
        .trim();
    return cleaned || raw.trim();
};
export const buildSupplierProductivity = (records, filters) => {
    // Step 1: only concluded tickets
    const concludedAll = records.filter((r) => r.statusGroup === 'concluded');
    // Step 2: filter by conclusionDate (col J) within the selected period
    const startDate = filters.startDate ? new Date(`${filters.startDate}T00:00:00`) : null;
    const endDate = filters.endDate ? new Date(`${filters.endDate}T23:59:59.999`) : null;
    const concluded = concludedAll.filter((r) => {
        if (!r.conclusionDate)
            return false;
        const d = new Date(r.conclusionDate);
        if (Number.isNaN(d.getTime()))
            return false;
        if (startDate && d < startDate)
            return false;
        if (endDate && d > endDate)
            return false;
        return true;
    });
    const acc = new Map();
    for (const record of concluded) {
        const name = normalizeSupplierName(record.provider);
        const current = acc.get(name) ?? { concluded: 0, days: [] };
        current.concluded += 1;
        // Duration: (col H || col BY) → col J
        const start = record.inAttendanceDate ?? record.createdOn;
        const end = record.conclusionDate;
        if (start && end) {
            const d = daysBetween(start, end);
            // Guard against negative durations (start after end)
            if (d !== null && d >= 0)
                current.days.push(d);
        }
        acc.set(name, current);
    }
    const rows = [...acc.entries()].map(([name, val]) => ({
        name,
        concluded: val.concluded,
        avgDays: val.days.length ? val.days.reduce((s, v) => s + v, 0) / val.days.length : null,
    }));
    if (rows.length === 0)
        return [];
    const avgConcluded = rows.reduce((s, r) => s + r.concluded, 0) / rows.length;
    const validDays = rows.filter((r) => r.avgDays !== null).map((r) => r.avgDays);
    const avgDays = validDays.length ? validDays.reduce((s, v) => s + v, 0) / validDays.length : 0;
    const classify = (r) => {
        const highVol = r.concluded >= avgConcluded;
        // null avgDays = no measurable time → never treated as fast (conservative)
        const fastTime = r.avgDays !== null && r.avgDays <= avgDays;
        if (highVol && fastTime)
            return 'high';
        if (highVol && !fastTime)
            return 'volume';
        if (!highVol && fastTime)
            return 'fast';
        return 'slow';
    };
    return rows
        .map((r) => ({ ...r, classification: classify(r) }))
        .sort((a, b) => b.concluded - a.concluded || (a.avgDays ?? Infinity) - (b.avgDays ?? Infinity));
};
export const buildInsight = (records) => {
    const regionRanking = buildRegionSeries(records, records, defaultFilters);
    const providerRanking = buildProviderRanking(records);
    const openIssues = records.filter((record) => record.statusGroup === 'in_progress' || record.statusGroup === 'backlog').length;
    const concluded = records.filter((record) => record.statusGroup === 'concluded').length;
    const topRegion = regionRanking[0];
    const topProvider = providerRanking.find((item) => item.volume >= 5) ?? providerRanking[0];
    const topBacklogStatus = records.reduce((accumulator, record) => {
        const key = record.status || 'Não informado';
        accumulator.set(key, (accumulator.get(key) ?? 0) + 1);
        return accumulator;
    }, new Map());
    const biggestStatus = [...topBacklogStatus.entries()].sort((left, right) => right[1] - left[1])[0];
    return {
        headline: topRegion
            ? `${topRegion.region} lidera o volume com ${topRegion.volume} chamados e ${topRegion.completionRate.toFixed(1)}% de conclusão.`
            : 'Carregue os dados para liberar a leitura de desempenho.',
        secondary: topProvider
            ? `${topProvider.label} concentra o melhor equilíbrio entre volume e fechamento, com ${topProvider.completionRate.toFixed(1)}% de conclusão.`
            : 'O ranking de fornecedores ficará visível após o carregamento dos dados.',
        action: openIssues > concluded
            ? `Há ${openIssues} itens em andamento; vale priorizar os status que mais concentram backlog, como ${biggestStatus?.[0] ?? 'n/d'}.`
            : 'A carteira está saudável e com mais entregas concluídas do que itens em andamento.',
    };
};
export const uniqueOptions = (records, selector) => [...new Set(records.map(selector).filter((value) => value && value !== 'Não informado'))].sort((left, right) => left.localeCompare(right, 'pt-BR'));
