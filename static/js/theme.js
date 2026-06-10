/* ============================================================
   Race Timing -- Theme Engine
   ============================================================ */

(function () {
    var saved = localStorage.getItem('race-timing-theme');
    if (!saved) {
        saved = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
    document.documentElement.setAttribute('data-theme', saved);
})();

window.toggleTheme = function () {
    var current = document.documentElement.getAttribute('data-theme');
    var next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('race-timing-theme', next);

    var btn = document.getElementById('themeToggle');
    if (btn) {
        var icon = btn.querySelector('[data-lucide]');
        if (icon) {
            icon.setAttribute('data-lucide', next === 'dark' ? 'sun' : 'moon');
        }
    }
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }
    if (typeof window.updateChartTheme === 'function') {
        window.updateChartTheme();
    }
};

window.getThemeColors = function () {
    var cs = getComputedStyle(document.documentElement);
    return {
        grid: cs.getPropertyValue('--chart-grid').trim(),
        gridMajor: cs.getPropertyValue('--chart-grid-major').trim(),
        text: cs.getPropertyValue('--chart-text').trim(),
        tooltipBg: cs.getPropertyValue('--chart-tooltip-bg').trim(),
        tooltipText: cs.getPropertyValue('--chart-tooltip-text').trim(),
        accentCyan: cs.getPropertyValue('--accent-cyan').trim(),
        accentViolet: cs.getPropertyValue('--accent-violet').trim(),
        bgSurface: cs.getPropertyValue('--bg-surface').trim(),
        textPrimary: cs.getPropertyValue('--text-primary').trim(),
        textSecondary: cs.getPropertyValue('--text-secondary').trim(),
        borderDefault: cs.getPropertyValue('--border-default').trim(),
        bgCardHeader: cs.getPropertyValue('--bg-card-header').trim(),
    };
};

document.addEventListener('DOMContentLoaded', function () {
    var theme = document.documentElement.getAttribute('data-theme');
    var btn = document.getElementById('themeToggle');
    if (btn) {
        var icon = btn.querySelector('[data-lucide]');
        if (icon) {
            icon.setAttribute('data-lucide', theme === 'dark' ? 'sun' : 'moon');
        }
    }

    var items = document.querySelectorAll('.stagger-item');
    items.forEach(function (el, index) {
        el.style.animationDelay = (index * 0.06) + 's';
    });
});
