// UI Renderer - All DOM manipulation and rendering
class UIRenderer {
    /**
     * Update dashboard header statistics
     * @param {Object} metrics - Metrics object from DataProcessor
     */
    static updateHeaderStats(metrics) {
        if (!metrics) return;

        document.getElementById('stat-total-bacon').textContent =
            DataProcessor.formatNumber(metrics.totalBaconDistributed);
        document.getElementById('stat-contributors').textContent =
            metrics.totalActiveContributors;

        if (metrics.recentTransaction) {
            document.getElementById('stat-recent-user').textContent =
                metrics.recentTransaction.username;
            document.getElementById('stat-recent-amount').textContent =
                metrics.recentTransaction.amount;
            document.getElementById('stat-recent-time').textContent =
                DataProcessor.formatTimeAgo(new Date(metrics.recentTransaction.timestamp));
        }
    }

    /**
     * Render leaderboard table with contributors
     * @param {Array} contributors - Normalized contributors array
     */
    static renderLeaderboardTable(contributors) {
        const tbody = document.getElementById('table-body');
        tbody.innerHTML = '';

        contributors.forEach((contributor) => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td class="rank">
                    <span class="inline-flex items-center justify-center w-8 h-8 rounded-full bg-blt-red-100 text-blt-red font-bold">
                        #${contributor.rank}
                    </span>
                </td>
                <td class="username">
                    <a href="https://github.com/${contributor.username}" target="_blank" class="text-blt-red hover:underline">
                        ${contributor.username}
                    </a>
                </td>
                <td class="text-right font-semibold text-gray-900">
                    ${DataProcessor.formatNumber(contributor.totalBacon)}
                </td>
                <td class="text-right text-gray-700">
                    ${contributor.prCount}
                </td>
                <td class="text-right text-gray-700">
                    ${contributor.avgValue.toFixed(2)}
                </td>
                <td class="text-center">
                    <span class="badge ${contributor.tier.class}">
                        ${contributor.tier.name}
                    </span>
                </td>
                <td class="wallet" title="${contributor.wallet}">
                    <code>${DataProcessor.truncateWallet(contributor.wallet)}</code>
                    <i class="fas fa-copy opacity-0 hover:opacity-100 transition ml-2" onclick="copyToClipboard('${contributor.wallet}')"></i>
                </td>
            `;
            tbody.appendChild(row);
        });

        this.showLeaderboardTable();
    }

    /**
     * Update pagination controls
     * @param {Object} paginationInfo - Pagination info from DataProcessor.paginate()
     */
    static updatePagination(paginationInfo) {
        document.getElementById('current-page').textContent = paginationInfo.page;
        document.getElementById('total-pages').textContent = paginationInfo.totalPages;
        document.getElementById('total-count').textContent = DataProcessor.formatNumber(paginationInfo.total);

        const prevBtn = document.getElementById('prev-page');
        const nextBtn = document.getElementById('next-page');

        prevBtn.disabled = !paginationInfo.hasPrevious;
        nextBtn.disabled = !paginationInfo.hasMore;
    }

    /**
     * Update transaction list
     * @param {Array} transactions - Normalized transactions array
     */
    static renderTransactionsList(transactions) {
        const list = document.getElementById('transactions-list');
        list.innerHTML = '';

        if (transactions.length === 0) {
            list.innerHTML = '<p class="text-center text-gray-500 py-8">No recent transactions</p>';
            document.getElementById('transactions-pagination').classList.add('hidden');
            return;
        }

        transactions.forEach((tx) => {
            const item = document.createElement('div');
            item.className = 'transaction-item';
            item.innerHTML = `
                <div class="transaction-avatar">
                    <i class="fas fa-award"></i>
                </div>
                <div class="transaction-content">
                    <span class="transaction-username font-semibold text-gray-900">
                        ${tx.username} received ${tx.amount} BACON
                    </span>
                    <span class="text-sm text-gray-600">
                        ${tx.getTimeAgo()}
                    </span>
                    ${tx.explorerUrl ? `
                        <a href="${tx.explorerUrl}" target="_blank" class="transaction-link">
                            View on Solana Explorer →
                        </a>
                    ` : ''}
                </div>
            `;
            list.appendChild(item);
        });
    }

    /**
     * Update transaction pagination
     * @param {Object} paginationInfo - Pagination info
     */
    static updateTransactionPagination(paginationInfo) {
        document.getElementById('tx-current-page').textContent = paginationInfo.page;
        document.getElementById('tx-total-pages').textContent = paginationInfo.totalPages;

        const pagination = document.getElementById('transactions-pagination');
        if (paginationInfo.totalPages > 1) {
            pagination.classList.remove('hidden');
        } else {
            pagination.classList.add('hidden');
        }

        const prevBtn = document.getElementById('tx-prev-page');
        const nextBtn = document.getElementById('tx-next-page');

        prevBtn.disabled = !paginationInfo.hasPrevious;
        nextBtn.disabled = !paginationInfo.hasMore;
    }

    /**
     * Switch between tabs
     * @param {string} tabName - Tab name ('leaderboard', 'charts', 'transactions')
     */
    static switchTab(tabName) {
        // Hide all tab contents
        document.querySelectorAll('.tab-content').forEach(tab => {
            tab.classList.add('hidden');
            tab.classList.remove('active');
        });

        // Deactivate all tab buttons
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.classList.remove('active');
            btn.classList.add('text-gray-600');
            btn.classList.remove('text-gray-900');
        });

        // Show selected tab
        const selectedTab = document.getElementById(`${tabName}-tab`);
        if (selectedTab) {
            selectedTab.classList.remove('hidden');
            selectedTab.classList.add('active');
        }

        // Activate selected button
        const selectedBtn = document.querySelector(`[data-tab="${tabName}"]`);
        if (selectedBtn) {
            selectedBtn.classList.add('active');
            selectedBtn.classList.remove('text-gray-600');
            selectedBtn.classList.add('text-gray-900');
        }

        // Trigger resize for charts
        if (tabName === 'charts') {
            setTimeout(() => {
                window.dispatchEvent(new Event('resize'));
            }, 100);
        }
    }

    /**
     * Show loading state
     */
    static showLoadingState() {
        document.getElementById('table-loading').classList.remove('hidden');
        document.getElementById('table-container').classList.add('hidden');
        document.getElementById('table-error').classList.add('hidden');
    }

    /**
     * Hide loading state and show table
     */
    static showLeaderboardTable() {
        document.getElementById('table-loading').classList.add('hidden');
        document.getElementById('table-container').classList.remove('hidden');
        document.getElementById('table-error').classList.add('hidden');
    }

    /**
     * Show error state
     */
    static showErrorState() {
        document.getElementById('table-loading').classList.add('hidden');
        document.getElementById('table-container').classList.add('hidden');
        document.getElementById('table-error').classList.remove('hidden');
    }

    /**
     * Update last updated timestamp
     * @param {Date} timestamp - Timestamp to display
     */
    static updateLastUpdated(timestamp) {
        const timeAgo = DataProcessor.formatTimeAgo(timestamp);
        document.getElementById('last-updated').textContent = `Last updated ${timeAgo}`;
    }

    /**
     * Show refresh indicator
     */
    static showRefreshIndicator() {
        const indicator = document.getElementById('update-indicator');
        indicator.classList.add('animate-pulse');
    }

    /**
     * Hide refresh indicator
     */
    static hideRefreshIndicator() {
        const indicator = document.getElementById('update-indicator');
        indicator.classList.remove('animate-pulse');
    }

    /**
     * Update statistics in charts tab
     * @param {Object} stats - Statistics object
     */
    static updateChartStatistics(stats) {
        if (!stats) return;

        document.getElementById('stat-avg-per-contributor').textContent =
            `${DataProcessor.formatNumber(stats.avgPerContributor)} BACON`;
        document.getElementById('stat-highest-tier').textContent =
            stats.highestTier;

        if (stats.topContributor) {
            document.getElementById('stat-active-day').textContent =
                stats.topContributor.username;
        }

        const rate = stats.totalBacon / 30; // Average per day
        document.getElementById('stat-rate').textContent =
            `${rate.toFixed(1)} BACON/day`;
    }

    /**
     * Enable/disable controls
     * @param {boolean} enabled - Should controls be enabled
     */
    static setControlsEnabled(enabled) {
        const controls = [
            'ranking-select',
            'limit-select',
            'search-btn',
            'refresh-btn',
            'prev-page',
            'next-page',
            'tx-prev-page',
            'tx-next-page'
        ];

        controls.forEach(id => {
            const element = document.getElementById(id);
            if (element) {
                element.disabled = !enabled;
            }
        });
    }
}

/**
 * Global helper function to copy to clipboard
 */
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        alert('Wallet address copied to clipboard!');
    }).catch(err => {
        console.error('Failed to copy:', err);
    });
}
