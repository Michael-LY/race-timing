// Shared table sorting utilities

function parseSortValue(cell) {
    const text = cell.textContent.trim();
    if (text === '-' || text === '') return { val: Infinity, type: 'empty' };
    const timeMatch = text.match(/^[+-]?(\d+):(\d{2})\.(\d+)/);
    if (timeMatch) {
        let val = parseInt(timeMatch[1]) * 60 + parseInt(timeMatch[2]) + parseInt(timeMatch[3]) / 1000;
        if (text.startsWith('-')) val = -val;
        return { val, type: 'time' };
    }
    const floatMatch = text.match(/^[+-]?[\d,.]+$/);
    if (floatMatch) return { val: parseFloat(text.replace(/,/g, '')), type: 'number' };
    const carMatch = text.match(/^#(\d+)$/);
    if (carMatch) return { val: parseInt(carMatch[1]), type: 'number' };
    const badge = cell.querySelector('.badge');
    if (badge) return { val: badge.textContent.trim(), type: 'string' };
    return { val: text.toLowerCase(), type: 'string' };
}

function initTableSort(tables) {
    tables = tables || document.querySelectorAll('.sortable-table, .themed-table');
    tables.forEach(table => {
        table.querySelectorAll('th.sortable').forEach(th => {
            th.addEventListener('click', function() {
                const tbody = table.querySelector('tbody');
                const colIdx = Array.from(this.parentNode.children).indexOf(this);
                const rows = Array.from(tbody.querySelectorAll('tr:not([data-sort-ignore="true"])'));

                const isAsc = this.classList.contains('asc');
                table.querySelectorAll('th.sortable').forEach(h => h.classList.remove('asc', 'desc'));
                this.classList.add(isAsc ? 'desc' : 'asc');

                rows.sort((a, b) => {
                    // For classification tables, keep grouped sort on position column
                    if (colIdx === 0 && (a.dataset.sortGroup || b.dataset.sortGroup)) {
                        const aGroup = a.dataset.sortGroup === 'ranked' ? 0 : 1;
                        const bGroup = b.dataset.sortGroup === 'ranked' ? 0 : 1;
                        if (aGroup !== bGroup) return aGroup - bGroup;
                        const aValue = parseInt(a.dataset.sortValue || '999999', 10);
                        const bValue = parseInt(b.dataset.sortValue || '999999', 10);
                        const cmp = aValue < bValue ? -1 : aValue > bValue ? 1 : 0;
                        return isAsc ? cmp : -cmp;
                    }

                    const aCell = a.children[colIdx];
                    const bCell = b.children[colIdx];
                    if (!aCell || !bCell) return 0;
                    const av = parseSortValue(aCell);
                    const bv = parseSortValue(bCell);
                    if (av.type === 'empty' && bv.type === 'empty') return 0;
                    if (av.type === 'empty') return 1;
                    if (bv.type === 'empty') return -1;
                    const cmp = av.val < bv.val ? -1 : av.val > bv.val ? 1 : 0;
                    return isAsc ? -cmp : cmp;
                });

                rows.forEach(row => tbody.appendChild(row));
            });
        });
    });
}
