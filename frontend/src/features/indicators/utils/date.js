export const formatMonthLabel = (value) => {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return 'Sem data';
    }
    return new Intl.DateTimeFormat('pt-BR', { month: 'short', year: 'numeric' }).format(date);
};
export const formatDateInput = (value) => {
    if (!value) {
        return '';
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return '';
    }
    return date.toISOString().slice(0, 10);
};
export const daysBetween = (start, end) => {
    if (!start || !end) {
        return null;
    }
    const startDate = new Date(start);
    const endDate = new Date(end);
    if (Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime())) {
        return null;
    }
    return Math.max(0, (endDate.getTime() - startDate.getTime()) / (1000 * 60 * 60 * 24));
};
