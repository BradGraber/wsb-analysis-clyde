/* WSB Tuning Workbench — Frontend Application */

const API = '/api/tuning';
let selectedComment = null;
let configs = [];

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

async function apiFetch(path, opts = {}) {
    const res = await fetch(`${API}${path}`, {
        headers: { 'Content-Type': 'application/json', ...opts.headers },
        ...opts,
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err?.error?.message || `HTTP ${res.status}`);
    }
    return res.json();
}

function truncate(str, len = 80) {
    if (!str) return '';
    return str.length > len ? str.slice(0, len) + '...' : str;
}

function sentimentBadge(s) {
    if (!s) return '<span class="sentiment neutral">--</span>';
    return `<span class="sentiment ${s}">${s}</span>`;
}

function formatCost(c) {
    return `$${(c || 0).toFixed(4)}`;
}

function escapeHtml(str) {
    if (!str) return '';
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
}

// ---------------------------------------------------------------------------
// Tab Navigation
// ---------------------------------------------------------------------------

document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(tc => tc.classList.remove('active'));
        tab.classList.add('active');
        document.getElementById(`tab-${tab.dataset.tab}`).classList.add('active');
    });
});

// ---------------------------------------------------------------------------
// Config Loading
// ---------------------------------------------------------------------------

async function loadConfigs() {
    try {
        const data = await apiFetch('/configs');
        configs = data.data || [];
        populateConfigDropdowns();
    } catch (e) {
        console.error('Failed to load configs:', e);
    }
}

function populateConfigDropdowns() {
    const selects = [
        document.getElementById('analyze-config'),
        document.getElementById('history-config'),
    ];

    selects.forEach(sel => {
        if (!sel) return;
        sel.innerHTML = '<option value="">All configs</option>';
        configs.forEach(c => {
            const opt = document.createElement('option');
            opt.value = c.id;
            opt.textContent = `${c.name} (${c.model}, t=${c.temperature})`;
            if (c.is_default) opt.textContent += ' *';
            sel.appendChild(opt);
        });
    });

    // Analyze config: select default
    const analyzeConfig = document.getElementById('analyze-config');
    if (analyzeConfig) {
        analyzeConfig.innerHTML = '';
        configs.forEach(c => {
            const opt = document.createElement('option');
            opt.value = c.id;
            opt.textContent = `${c.name} (${c.model}, t=${c.temperature})`;
            if (c.is_default) { opt.textContent += ' *'; opt.selected = true; }
            analyzeConfig.appendChild(opt);
        });
    }

    updateCompareConfigList();
}

// ---------------------------------------------------------------------------
// Browse Tab
// ---------------------------------------------------------------------------

let browseOffset = 0;
const BROWSE_LIMIT = 25;

async function browseComments(offset = 0) {
    browseOffset = offset;
    const q = document.getElementById('browse-search').value;
    const sentiment = document.getElementById('browse-sentiment').value;

    const params = new URLSearchParams({ limit: BROWSE_LIMIT, offset });
    if (q) params.set('q', q);
    if (sentiment) params.set('sentiment', sentiment);

    try {
        const data = await apiFetch(`/comments?${params}`);
        renderBrowseResults(data.data, data.meta.total);
    } catch (e) {
        document.getElementById('browse-results').innerHTML =
            `<p style="color:var(--bearish)">Error: ${escapeHtml(e.message)}</p>`;
    }
}

function renderBrowseResults(items, total) {
    const container = document.getElementById('browse-results');
    if (!items.length) {
        container.innerHTML = '<p style="color:var(--text-muted)">No comments found.</p>';
        document.getElementById('browse-pagination').innerHTML = '';
        return;
    }

    let html = `<table><thead><tr>
        <th>ID</th><th>Author</th><th>Body</th>
        <th>Sentiment</th><th>Conf</th><th>Score</th>
    </tr></thead><tbody>`;

    items.forEach(c => {
        const sel = selectedComment?.reddit_id === c.reddit_id ? ' selected' : '';
        html += `<tr class="browse-row${sel}" data-id="${escapeHtml(c.reddit_id)}">
            <td>${escapeHtml(c.reddit_id)}</td>
            <td>${escapeHtml(c.author)}</td>
            <td>${escapeHtml(truncate(c.body, 60))}</td>
            <td>${sentimentBadge(c.sentiment)}</td>
            <td>${c.ai_confidence != null ? c.ai_confidence.toFixed(2) : '--'}</td>
            <td>${c.score ?? '--'}</td>
        </tr>`;
    });

    html += '</tbody></table>';
    container.innerHTML = html;

    // Click handlers
    container.querySelectorAll('.browse-row').forEach(row => {
        row.addEventListener('click', () => selectComment(row.dataset.id));
    });

    // Pagination
    renderPagination('browse-pagination', total, browseOffset, BROWSE_LIMIT, browseComments);
}

function renderPagination(containerId, total, offset, limit, callback) {
    const el = document.getElementById(containerId);
    const page = Math.floor(offset / limit) + 1;
    const totalPages = Math.ceil(total / limit);

    el.innerHTML = `
        <button ${offset <= 0 ? 'disabled' : ''} onclick="void(0)" id="${containerId}-prev">Prev</button>
        <span class="page-info">Page ${page} of ${totalPages} (${total} total)</span>
        <button ${offset + limit >= total ? 'disabled' : ''} onclick="void(0)" id="${containerId}-next">Next</button>
    `;

    document.getElementById(`${containerId}-prev`)?.addEventListener('click', () => {
        callback(Math.max(0, offset - limit));
    });
    document.getElementById(`${containerId}-next`)?.addEventListener('click', () => {
        callback(offset + limit);
    });
}

async function selectComment(redditId) {
    try {
        const data = await apiFetch(`/comments/${redditId}`);
        selectedComment = data.data;
        renderSelectedComment();
        // Highlight in browse table
        document.querySelectorAll('.browse-row').forEach(r => {
            r.classList.toggle('selected', r.dataset.id === redditId);
        });
    } catch (e) {
        console.error('Failed to load comment:', e);
    }
}

function renderSelectedComment() {
    const cards = [
        document.getElementById('selected-comment'),
        document.getElementById('compare-comment'),
    ];

    cards.forEach(card => {
        if (!card || !selectedComment) return;
        const c = selectedComment;
        card.classList.remove('empty');
        card.innerHTML = `
            <div class="meta">
                <span><strong>${escapeHtml(c.reddit_id)}</strong></span>
                <span>by ${escapeHtml(c.author)}</span>
                <span>trust: ${(c.author_trust_score || 0.5).toFixed(2)}</span>
                <span>post: "${escapeHtml(truncate(c.post_title, 50))}"</span>
            </div>
            <div class="body">${escapeHtml(c.body)}</div>
            ${c.sentiment ? `<div class="analysis">
                ${sentimentBadge(c.sentiment)}
                <span>conf: ${c.ai_confidence?.toFixed(2) || '--'}</span>
                <span>sarcasm: ${c.sarcasm_detected ? 'yes' : 'no'}</span>
                <span>reasoning: ${c.has_reasoning ? 'yes' : 'no'}</span>
            </div>` : ''}
        `;
    });
}

document.getElementById('browse-btn').addEventListener('click', () => browseComments(0));
document.getElementById('browse-search').addEventListener('keydown', e => {
    if (e.key === 'Enter') browseComments(0);
});

// ---------------------------------------------------------------------------
// Analyze Tab
// ---------------------------------------------------------------------------

document.getElementById('btn-dry-run').addEventListener('click', async () => {
    if (!selectedComment) return alert('Select a comment first');

    const configId = document.getElementById('analyze-config').value;
    const marketCtx = document.getElementById('analyze-market-ctx').value;

    const body = {
        reddit_id: selectedComment.reddit_id,
        prompt_config_id: configId ? parseInt(configId) : null,
        market_context: marketCtx === 'off' ? false : null,
    };

    const output = document.getElementById('analyze-output');
    output.innerHTML = '<span class="spinner"></span> Building prompts...';

    try {
        const data = await apiFetch('/dry-run', {
            method: 'POST',
            body: JSON.stringify(body),
        });
        const d = data.data;
        output.innerHTML = `
            <div class="result-panel">
                <h3>Dry Run — Prompts Preview</h3>
                <div class="prompt-display">
                    <span class="prompt-label">SYSTEM PROMPT</span>${escapeHtml(d.system_prompt)}
                </div>
                <div class="prompt-display" style="margin-top:8px">
                    <span class="prompt-label">USER PROMPT</span>${escapeHtml(d.user_prompt)}
                </div>
                ${d.market_context ? `<div class="prompt-display" style="margin-top:8px">
                    <span class="prompt-label">MARKET CONTEXT</span>${escapeHtml(d.market_context)}
                </div>` : ''}
            </div>
        `;
    } catch (e) {
        output.innerHTML = `<p style="color:var(--bearish)">Error: ${escapeHtml(e.message)}</p>`;
    }
});

document.getElementById('btn-analyze').addEventListener('click', async () => {
    if (!selectedComment) return alert('Select a comment first');

    const configId = document.getElementById('analyze-config').value;
    const marketCtx = document.getElementById('analyze-market-ctx').value;
    const tag = document.getElementById('analyze-tag').value || null;

    const body = {
        reddit_id: selectedComment.reddit_id,
        prompt_config_id: configId ? parseInt(configId) : null,
        market_context: marketCtx === 'off' ? false : null,
        tag,
    };

    const output = document.getElementById('analyze-output');
    output.innerHTML = '<span class="spinner"></span> Analyzing...';

    try {
        const data = await apiFetch('/analyze', {
            method: 'POST',
            body: JSON.stringify(body),
        });
        const r = data.data;
        output.innerHTML = renderResult(r.result, r.usage, r.cost, r.tuning_run_id);
    } catch (e) {
        output.innerHTML = `<p style="color:var(--bearish)">Error: ${escapeHtml(e.message)}</p>`;
    }
});

document.getElementById('btn-multi-run').addEventListener('click', async () => {
    if (!selectedComment) return alert('Select a comment first');

    const configId = document.getElementById('analyze-config').value;
    const marketCtx = document.getElementById('analyze-market-ctx').value;
    const tag = document.getElementById('analyze-tag').value || null;
    const runs = parseInt(document.getElementById('multi-run-count').value) || 5;

    const body = {
        reddit_id: selectedComment.reddit_id,
        prompt_config_id: configId ? parseInt(configId) : null,
        market_context: marketCtx === 'off' ? false : null,
        tag,
        runs,
    };

    const output = document.getElementById('analyze-output');
    output.innerHTML = '<span class="spinner"></span> Running multi-run analysis...';

    try {
        const res = await fetch(`${API}/multi-run`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });

        const reader = res.body.getReader();
        const decoder = new TextDecoder();

        let tableHtml = `<div class="multi-run-table"><table><thead><tr>
            <th>#</th><th>Sentiment</th><th>Conf</th><th>Tickers</th><th>Sarcasm</th><th>Cost</th>
        </tr></thead><tbody id="multi-run-body"></tbody></table></div>
        <div id="multi-run-summary" class="multi-run-summary" style="display:none"></div>`;
        output.innerHTML = tableHtml;

        let buffer = '';
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });

            const lines = buffer.split('\n');
            buffer = lines.pop(); // keep incomplete line

            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                let json;
                try { json = JSON.parse(line.slice(6)); }
                catch { continue; }

                if (json.type === 'summary') {
                    const sumEl = document.getElementById('multi-run-summary');
                    if (sumEl) {
                        const counts = Object.entries(json.sentiment_counts)
                            .map(([s, n]) => `${sentimentBadge(s)} ${n}/${json.total_runs}`)
                            .join(' &nbsp; ');
                        sumEl.style.display = 'block';
                        sumEl.innerHTML = `
                            <strong>Summary:</strong> ${counts}<br>
                            Avg confidence: ${json.avg_confidence.toFixed(2)} &nbsp;|&nbsp;
                            Total cost: ${formatCost(json.total_cost)}
                        `;
                    }
                } else if (json.error) {
                    const tbody = document.getElementById('multi-run-body');
                    if (tbody) {
                        tbody.innerHTML += `<tr>
                            <td>${json.run}</td>
                            <td colspan="5" style="color:var(--bearish)">Error: ${escapeHtml(json.error)}</td>
                        </tr>`;
                    }
                } else {
                    const r = json.result;
                    const tickers = (r.tickers || []).map((t, i) =>
                        `${t}(${(r.ticker_sentiments || [])[i] || '?'})`
                    ).join(', ') || 'none';

                    const tbody = document.getElementById('multi-run-body');
                    if (tbody) {
                        tbody.innerHTML += `<tr>
                            <td>${json.run}</td>
                            <td>${sentimentBadge(r.sentiment)}</td>
                            <td>${r.confidence?.toFixed(2) || '--'}</td>
                            <td>${escapeHtml(tickers)}</td>
                            <td>${r.sarcasm_detected ? 'yes' : 'no'}</td>
                            <td class="cost">${formatCost(json.cost)}</td>
                        </tr>`;
                    }
                }
            }
        }
    } catch (e) {
        output.innerHTML = `<p style="color:var(--bearish)">Error: ${escapeHtml(e.message)}</p>`;
    }
});

function renderResult(r, usage, cost, runId) {
    const tickers = (r.tickers || []).map((t, i) =>
        `${t}(${(r.ticker_sentiments || [])[i] || '?'})`
    ).join(', ') || 'none';

    return `<div class="result-panel">
        <h3>Result ${runId ? `(run #${runId})` : ''}</h3>
        <div class="result-grid">
            <div class="result-field">
                <span class="label">Sentiment</span>
                <span class="value">${sentimentBadge(r.sentiment)}</span>
            </div>
            <div class="result-field">
                <span class="label">Confidence</span>
                <span class="value">${r.confidence?.toFixed(2) || '--'}</span>
            </div>
            <div class="result-field">
                <span class="label">Tickers</span>
                <span class="value">${escapeHtml(tickers)}</span>
            </div>
            <div class="result-field">
                <span class="label">Sarcasm</span>
                <span class="value">${r.sarcasm_detected ? 'yes' : 'no'}</span>
            </div>
            <div class="result-field">
                <span class="label">Reasoning</span>
                <span class="value">${r.has_reasoning ? 'yes' : 'no'}</span>
            </div>
            <div class="result-field">
                <span class="label">Cost</span>
                <span class="value cost">${formatCost(cost)}</span>
            </div>
        </div>
        ${r.reasoning_summary ? `<div style="margin-top:8px;font-size:11px;color:var(--text-muted)">
            <strong>Reasoning:</strong> ${escapeHtml(r.reasoning_summary)}
        </div>` : ''}
        <div style="margin-top:6px;font-size:10px;color:var(--text-muted)">
            Tokens: ${usage.prompt_tokens} prompt / ${usage.completion_tokens} completion
        </div>
    </div>`;
}

// ---------------------------------------------------------------------------
// Compare Tab
// ---------------------------------------------------------------------------

function updateCompareConfigList() {
    const container = document.getElementById('compare-config-list');
    if (!container) return;

    // Keep at least 2 selects
    const existing = container.querySelectorAll('select');
    if (existing.length < 2) {
        container.innerHTML = '';
        for (let i = 0; i < 2; i++) addCompareConfigSelect(container);
    }
}

function addCompareConfigSelect(container) {
    if (!container) container = document.getElementById('compare-config-list');
    const count = container.querySelectorAll('select').length;
    if (count >= 5) return;

    const sel = document.createElement('select');
    sel.className = 'compare-config-select';
    configs.forEach(c => {
        const opt = document.createElement('option');
        opt.value = c.id;
        opt.textContent = `${c.name} (${c.model}, t=${c.temperature})`;
        sel.appendChild(opt);
    });
    // Default to different config if available
    if (configs.length > count) {
        sel.value = configs[count].id;
    }
    container.appendChild(sel);
}

document.getElementById('btn-add-config')?.addEventListener('click', () => {
    addCompareConfigSelect();
});

document.getElementById('btn-compare')?.addEventListener('click', async () => {
    if (!selectedComment) return alert('Select a comment first');

    const selects = document.querySelectorAll('.compare-config-select');
    const configIds = [...selects].map(s => parseInt(s.value)).filter(Boolean);

    if (configIds.length < 2) return alert('Select at least 2 configs');

    const marketCtx = document.getElementById('compare-market-ctx').value;

    const body = {
        reddit_id: selectedComment.reddit_id,
        config_ids: configIds,
        market_context: marketCtx === 'off' ? false : null,
    };

    const output = document.getElementById('compare-output');
    output.innerHTML = '<span class="spinner"></span> Comparing configs...';

    try {
        const res = await fetch(`${API}/compare`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });

        const reader = res.body.getReader();
        const decoder = new TextDecoder();

        const results = [];
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });

            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                let json;
                try { json = JSON.parse(line.slice(6)); }
                catch { continue; }
                if (json.type === 'done') continue;
                results.push(json);
            }
        }

        // Render side-by-side
        const colClass = `cols-${Math.min(results.length, 5)}`;
        let html = `<div class="compare-grid ${colClass}">`;
        results.forEach(r => {
            if (r.error) {
                html += `<div class="result-panel">
                    <h3>Config ${escapeHtml(r.label)}: ${escapeHtml(r.config_name)}</h3>
                    <p style="color:var(--bearish)">Error: ${escapeHtml(r.error)}</p>
                </div>`;
            } else {
                html += `<div class="result-panel">
                    <h3>Config ${escapeHtml(r.label)}: ${escapeHtml(r.config_name)}</h3>
                    ${renderCompareResult(r.result, r.usage, r.cost)}
                </div>`;
            }
        });
        html += '</div>';

        // Highlight differences
        output.innerHTML = html;

    } catch (e) {
        output.innerHTML = `<p style="color:var(--bearish)">Error: ${escapeHtml(e.message)}</p>`;
    }
});

function renderCompareResult(r, usage, cost) {
    const tickers = (r.tickers || []).map((t, i) =>
        `${t}(${(r.ticker_sentiments || [])[i] || '?'})`
    ).join(', ') || 'none';

    return `
        <div style="margin-bottom:6px">${sentimentBadge(r.sentiment)} <strong>${r.confidence?.toFixed(2) || '--'}</strong></div>
        <div style="font-size:11px;margin-bottom:4px">Tickers: ${escapeHtml(tickers)}</div>
        <div style="font-size:11px;margin-bottom:4px">Sarcasm: ${r.sarcasm_detected ? 'yes' : 'no'} | Reasoning: ${r.has_reasoning ? 'yes' : 'no'}</div>
        ${r.reasoning_summary ? `<div style="font-size:10px;color:var(--text-muted);margin-bottom:4px">${escapeHtml(truncate(r.reasoning_summary, 150))}</div>` : ''}
        <div class="cost">${formatCost(cost)} | ${usage.prompt_tokens}+${usage.completion_tokens} tokens</div>
    `;
}

// ---------------------------------------------------------------------------
// History Tab
// ---------------------------------------------------------------------------

let historyOffset = 0;
const HISTORY_LIMIT = 25;

async function loadHistory(offset = 0) {
    historyOffset = offset;
    const redditId = document.getElementById('history-reddit-id').value;
    const tag = document.getElementById('history-tag').value;
    const configId = document.getElementById('history-config').value;

    const params = new URLSearchParams({ limit: HISTORY_LIMIT, offset });
    if (redditId) params.set('reddit_id', redditId);
    if (tag) params.set('tag', tag);
    if (configId) params.set('config_id', configId);

    try {
        const data = await apiFetch(`/history?${params}`);
        renderHistory(data.data, data.meta.total);
    } catch (e) {
        document.getElementById('history-results').innerHTML =
            `<p style="color:var(--bearish)">Error: ${escapeHtml(e.message)}</p>`;
    }
}

function renderHistory(items, total) {
    const container = document.getElementById('history-results');
    if (!items.length) {
        container.innerHTML = '<p style="color:var(--text-muted)">No tuning runs found.</p>';
        document.getElementById('history-pagination').innerHTML = '';
        return;
    }

    let html = `<table><thead><tr>
        <th>ID</th><th>Comment</th><th>Config</th>
        <th>Sentiment</th><th>Conf</th><th>Mode</th>
        <th>Tag</th><th>Cost</th><th>Time</th>
    </tr></thead><tbody>`;

    items.forEach(r => {
        html += `<tr class="history-row" data-id="${r.id}">
            <td>${r.id}</td>
            <td>${escapeHtml(r.reddit_id)}</td>
            <td>${escapeHtml(r.config_name)} (${escapeHtml(r.config_model)})</td>
            <td>${sentimentBadge(r.sentiment)}</td>
            <td>${r.ai_confidence != null ? r.ai_confidence.toFixed(2) : '--'}</td>
            <td>${escapeHtml(r.mode || '--')}${r.label ? '/' + escapeHtml(r.label) : ''}</td>
            <td>${escapeHtml(r.tag || '--')}</td>
            <td class="cost">${formatCost(r.cost)}</td>
            <td>${r.created_at ? r.created_at.slice(0, 16) : '--'}</td>
        </tr>
        <tr class="history-detail" id="detail-${r.id}"><td colspan="9">
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div>
                    <strong>Reasoning:</strong> ${escapeHtml(r.reasoning_summary || 'none')}<br>
                    <strong>Tickers:</strong> ${escapeHtml(r.tickers || '[]')}<br>
                    <strong>Sarcasm:</strong> ${r.sarcasm_detected ? 'yes' : 'no'} |
                    <strong>Reasoning:</strong> ${r.has_reasoning ? 'yes' : 'no'}<br>
                    <strong>Tokens:</strong> ${r.prompt_tokens || 0} prompt / ${r.completion_tokens || 0} completion
                </div>
                <div>
                    ${r.user_prompt ? `<div class="prompt-display" style="max-height:200px;font-size:10px">${escapeHtml(truncate(r.user_prompt, 500))}</div>` : ''}
                </div>
            </div>
        </td></tr>`;
    });

    html += '</tbody></table>';
    container.innerHTML = html;

    // Expandable rows
    container.querySelectorAll('.history-row').forEach(row => {
        row.addEventListener('click', () => {
            const detail = document.getElementById(`detail-${row.dataset.id}`);
            if (detail) detail.classList.toggle('open');
        });
    });

    renderPagination('history-pagination', total, historyOffset, HISTORY_LIMIT, loadHistory);
}

document.getElementById('history-btn').addEventListener('click', () => loadHistory(0));

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

(async function init() {
    await loadConfigs();
    browseComments(0);
})();
