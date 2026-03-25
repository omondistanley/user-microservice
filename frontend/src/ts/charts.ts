// @ts-nocheck
/**
 * ApexCharts helpers for expense tracker. Requires ApexCharts to be loaded first.
 * Each helper destroys any existing chart in the container before rendering.
 */
(function() {
    'use strict';

    var CHART_INSTANCE_KEY = 'apexcharts-instance';
    var CURRENCY_SYMBOLS = { USD: '$', EUR: 'EUR ', GBP: 'GBP ', KES: 'KES ', JPY: 'JPY ', CAD: 'CAD ', AUD: 'AUD ' };

    function destroyExisting(container) {
        if (!container) return;
        var existing = container[CHART_INSTANCE_KEY];
        if (existing && typeof existing.destroy === 'function') {
            existing.destroy();
            container[CHART_INSTANCE_KEY] = null;
        }
    }

    function showEmptyMessage(container, message) {
        if (!container) return;
        destroyExisting(container);
        container.innerHTML = '<p class="empty-chart-message">' + (message || 'No data for this range') + '</p>';
    }

    function ensureChartDiv(container) {
        if (!container) return null;
        container.innerHTML = '';
        var wrapper = document.createElement('div');
        wrapper.className = 'chart-inner';
        wrapper.style.minHeight = '200px';
        container.appendChild(wrapper);
        return wrapper;
    }

    function defaultTheme() {
        return {
            mode: 'dark',
            palette: 'palette2',
            monochrome: { enabled: false }
        };
    }

    function getCurrencySymbol() {
        var currency = 'USD';
        try {
            var stored = localStorage.getItem('default_currency');
            if (stored) currency = String(stored).toUpperCase();
        } catch (e) {}
        return CURRENCY_SYMBOLS[currency] || (currency + ' ');
    }

    function formatAmountLabel(val) {
        var n = Number(val || 0);
        if (!isFinite(n)) return '0';
        return getCurrencySymbol() + n.toLocaleString(undefined, { maximumFractionDigits: 0 });
    }

    function defaultChartOptions() {
        return {
            chart: { fontFamily: '"Source Sans 3", sans-serif', toolbar: { show: false }, background: 'transparent' },
            theme: defaultTheme(),
            grid: { borderColor: 'rgba(255,255,255,0.06)' },
            noData: { text: 'No chart data for this range' },
            tooltip: { y: { formatter: function(v) { return formatAmountLabel(v); } } },
            yaxis: { labels: { formatter: function(v) { return formatAmountLabel(v); } } },
            responsive: [{ options: {} }]
        };
    }

    window.ExpenseCharts = {
        renderCategoryChart: function(containerId, summaryItems, options) {
            var container = document.getElementById(containerId);
            if (!container) return;
            if (!summaryItems || summaryItems.length === 0) {
                showEmptyMessage(container, 'No data for this range');
                return;
            }
            var wrapper = ensureChartDiv(container);
            if (!wrapper) return;
            destroyExisting(container);
            var series = summaryItems.map(function(i) { return Number(i.total_amount); });
            var labels = summaryItems.map(function(i) { return i.label || i.group_key || ''; });
            var opts = Object.assign({}, defaultChartOptions(), {
                series: series,
                chart: Object.assign({ type: 'donut' }, defaultChartOptions().chart),
                labels: labels,
                legend: { position: 'bottom' },
                plotOptions: { pie: { donut: { size: '60%' } } }
            }, options || {});
            var chart = new ApexCharts(wrapper, opts);
            container[CHART_INSTANCE_KEY] = chart;
            chart.render();
        },

        renderMonthlyTrendChart: function(containerId, summaryItems, options) {
            var container = document.getElementById(containerId);
            if (!container) return;
            if (!summaryItems || summaryItems.length === 0) {
                showEmptyMessage(container, 'No data for this range');
                return;
            }
            var sorted = summaryItems.slice().sort(function(a, b) {
                return (a.group_key || '').localeCompare(b.group_key || '');
            });
            var categories = sorted.map(function(i) {
                var key = i.group_key || i.label || '';
                if (key.length === 7) {
                    var parts = key.split('-');
                    var months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
                    var mi = parseInt(parts[1], 10) - 1;
                    return (months[mi] || parts[1]) + ' ' + (parts[0] || '');
                }
                return key;
            });
            var seriesData = sorted.map(function(i) { return Number(i.total_amount); });
            var wrapper = ensureChartDiv(container);
            if (!wrapper) return;
            destroyExisting(container);
            var opts = Object.assign({}, defaultChartOptions(), {
                series: [{ name: 'Spending', data: seriesData }],
                chart: Object.assign({ type: 'line', zoom: { enabled: false } }, defaultChartOptions().chart),
                xaxis: { categories: categories },
                yaxis: { title: { text: 'Amount' }, labels: { formatter: function(v) { return formatAmountLabel(v); } } },
                stroke: { curve: 'smooth', width: 2 },
                dataLabels: { enabled: false }
            }, options || {});
            var chart = new ApexCharts(wrapper, opts);
            container[CHART_INSTANCE_KEY] = chart;
            chart.render();
        },

        renderBudgetVsSpentChart: function(containerId, budgetItemsWithSpent) {
            var container = document.getElementById(containerId);
            if (!container) return;
            if (!budgetItemsWithSpent || budgetItemsWithSpent.length === 0) {
                showEmptyMessage(container, 'No budgets set');
                return;
            }
            var categories = budgetItemsWithSpent.map(function(b) { return b.label || ''; });
            var budgetSeries = budgetItemsWithSpent.map(function(b) { return Number(b.budgetAmount); });
            var spentSeries = budgetItemsWithSpent.map(function(b) { return Number(b.spentAmount); });
            var wrapper = ensureChartDiv(container);
            if (!wrapper) return;
            destroyExisting(container);
            var opts = Object.assign({}, defaultChartOptions(), {
                series: [
                    { name: 'Budget', data: budgetSeries },
                    { name: 'Spent', data: spentSeries }
                ],
                chart: Object.assign({ type: 'bar' }, defaultChartOptions().chart),
                plotOptions: {
                    bar: {
                        horizontal: false,
                        columnWidth: '60%',
                        dataLabels: { position: 'top' }
                    }
                },
                colors: ['#4b5563', '#dc3545'],
                xaxis: { categories: categories },
                yaxis: { title: { text: 'Amount' }, labels: { formatter: function(v) { return formatAmountLabel(v); } } },
                legend: { position: 'top' },
                dataLabels: { enabled: true }
            }, options || {});
            var chart = new ApexCharts(wrapper, opts);
            container[CHART_INSTANCE_KEY] = chart;
            chart.render();
        },

        renderSparkline: function(containerId, summaryItems) {
            var container = document.getElementById(containerId);
            if (!container) return;
            if (!summaryItems || summaryItems.length === 0) {
                showEmptyMessage(container, '');
                return;
            }
            var sorted = summaryItems.slice().sort(function(a, b) {
                return (a.group_key || '').localeCompare(b.group_key || '');
            });
            var seriesData = sorted.map(function(i) { return Number(i.total_amount); });
            var wrapper = ensureChartDiv(container);
            if (!wrapper) return;
            destroyExisting(container);
            var opts = {
                series: [{ name: 'Spending', data: seriesData }],
                chart: {
                    type: 'line',
                    sparkline: { enabled: true },
                    height: 60,
                    toolbar: { show: false },
                    fontFamily: '"Source Sans 3", sans-serif'
                },
                stroke: { curve: 'smooth', width: 2 },
                theme: defaultTheme(),
                tooltip: { enabled: true }
            };
            var chart = new ApexCharts(wrapper, opts);
            container[CHART_INSTANCE_KEY] = chart;
            chart.render();
        },

        renderBalanceOverTimeChart: function(containerId, balanceHistoryItems) {
            var container = document.getElementById(containerId);
            if (!container) return;
            if (!balanceHistoryItems || balanceHistoryItems.length === 0) {
                showEmptyMessage(container, 'No data for this range');
                return;
            }
            var sorted = balanceHistoryItems.slice().sort(function(a, b) {
                return (a.date || '').localeCompare(b.date || '');
            });
            var categories = sorted.map(function(i) { return i.date || ''; });
            var seriesData = sorted.map(function(i) { return Number(i.balance); });
            var wrapper = ensureChartDiv(container);
            if (!wrapper) return;
            destroyExisting(container);
            var opts = Object.assign({}, defaultChartOptions(), {
                series: [{ name: 'Balance', data: seriesData }],
                chart: Object.assign({ type: 'line', zoom: { enabled: false } }, defaultChartOptions().chart),
                xaxis: { categories: categories },
                yaxis: { title: { text: 'Balance' }, labels: { formatter: function(v) { return formatAmountLabel(v); } } },
                stroke: { curve: 'smooth', width: 2 },
                dataLabels: { enabled: false }
            });
            var chart = new ApexCharts(wrapper, opts);
            container[CHART_INSTANCE_KEY] = chart;
            chart.render();
        }
    };
})();
