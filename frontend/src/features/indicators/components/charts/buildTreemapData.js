const MAX_CATEGORIES = 6;
function groupTopItems(items, maxItems, othersName = "Outros") {
    const sorted = [...items].sort((a, b) => b.value - a.value);
    const visible = sorted.slice(0, maxItems);
    const hidden = sorted.slice(maxItems);
    const othersTotal = hidden.reduce((sum, item) => sum + item.value, 0);
    if (othersTotal > 0) {
        visible.push({
            name: othersName,
            value: othersTotal,
        });
    }
    return visible;
}
function getSubcategoryLimit(shareOfTotal) {
    if (shareOfTotal >= 15)
        return 3;
    if (shareOfTotal >= 7)
        return 2;
    return 1;
}
export function buildTreemapData(data) {
    const totalGeral = data.reduce((sum, item) => sum + item.total, 0);
    const categoryMap = new Map();
    data.forEach((item) => {
        if (!categoryMap.has(item.categoria)) {
            categoryMap.set(item.categoria, []);
        }
        categoryMap.get(item.categoria).push(item);
    });
    const categories = Array.from(categoryMap.entries()).map(([categoria, items]) => ({
        categoria,
        total: items.reduce((sum, item) => sum + item.total, 0),
        items,
    }));
    const limitedCategories = groupTopItems(categories.map((category) => ({
        name: category.categoria,
        value: category.total,
        items: category.items,
    })), MAX_CATEGORIES, "Outras Categorias");
    return limitedCategories.map((category) => {
        const shareOfTotal = totalGeral > 0
            ? (category.value / totalGeral) * 100
            : 0;
        if (category.name === "Outras Categorias") {
            return {
                name: category.name,
                category: category.name,
                value: category.value,
                total: category.value,
                shareOfCategory: 100,
                shareOfTotal,
                fill: "#334155",
                stroke: "#475569",
                children: [],
            };
        }
        const subcategories = category.items.map((item) => ({
            name: item.subcategoria || "Sem subcategoria",
            value: item.total,
            raw: item,
        }));
        const subcategoryLimit = getSubcategoryLimit(shareOfTotal);
        const groupedSubcategories = groupTopItems(subcategories, subcategoryLimit, "Outras Subcategorias");
        return {
            name: category.name,
            category: category.name,
            value: category.value,
            total: category.value,
            shareOfCategory: 100,
            shareOfTotal,
            fill: "#0f172a",
            stroke: "#1e293b",
            children: groupedSubcategories.map((sub) => ({
                name: sub.name,
                category: category.name,
                subcategory: sub.name,
                value: sub.value,
                total: sub.value,
                shareOfCategory: category.value > 0
                    ? (sub.value / category.value) * 100
                    : 0,
                shareOfTotal: totalGeral > 0
                    ? (sub.value / totalGeral) * 100
                    : 0,
                fill: "#1d4ed8",
                stroke: "#2563eb",
            })),
        };
    });
}
