/* WSB Tuning Workbench — Frontend Application */

const API = '/api/tuning';

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let configs = [];
let selectedIds = new Set();           // multi-select for workbench
let selectedComments = new Map();      // reddit_id -> full comment data
let matrixResults = {};                // { "reddit_id|config_id": { result, usage, cost, run_id } }
let matrixColumns = [];                // ordered config ids that have been run

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

/** Parse SSE stream from a fetch Response, yielding JSON objects. */
async function* parseSSE(response) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
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
            yield json;
        }
    }
}

function renderPagination(containerId, total, offset, limit, callback) {
    const el = document.getElementById(containerId);
    const page = Math.floor(offset / limit) + 1;
    const totalPages = Math.ceil(total / limit);

    el.innerHTML = `
        <button ${offset <= 0 ? 'disabled' : ''} id="${containerId}-prev">Prev</button>
        <span class="page-info">Page ${page} of ${totalPages} (${total} total)</span>
        <button ${offset + limit >= total ? 'disabled' : ''} id="${containerId}-next">Next</button>
    `;

    document.getElementById(`${containerId}-prev`)?.addEventListener('click', () => {
        callback(Math.max(0, offset - limit));
    });
    document.getElementById(`${containerId}-next`)?.addEventListener('click', () => {
        callback(offset + limit);
    });
}

function renderResultFields(r, usage, cost) {
    const tickers = (r.tickers || []).map((t, i) =>
        `${t}(${(r.ticker_sentiments || [])[i] || '?'})`
    ).join(', ') || 'none';

    return `
        <div class="matrix-detail-grid">
            <div class="detail-field">
                <span class="label">Sentiment</span>
                <span class="value">${sentimentBadge(r.sentiment)}</span>
            </div>
            <div class="detail-field">
                <span class="label">Confidence</span>
                <span class="value">${r.confidence?.toFixed(2) || '--'}</span>
            </div>
            <div class="detail-field">
                <span class="label">Tickers</span>
                <span class="value">${escapeHtml(tickers)}</span>
            </div>
            <div class="detail-field">
                <span class="label">Sarcasm</span>
                <span class="value">${r.sarcasm_detected ? 'yes' : 'no'}</span>
            </div>
            <div class="detail-field">
                <span class="label">Reasoning</span>
                <span class="value">${r.has_reasoning ? 'yes' : 'no'}</span>
            </div>
            <div class="detail-field">
                <span class="label">Cost</span>
                <span class="value cost">${formatCost(cost)}</span>
            </div>
            <div class="detail-field">
                <span class="label">Tokens</span>
                <span class="value token-count">${usage.prompt_tokens} / ${usage.completion_tokens}</span>
            </div>
        </div>
        ${r.reasoning_summary ? `<div class="matrix-detail-reasoning">
            <strong>Reasoning:</strong> ${escapeHtml(r.reasoning_summary)}
        </div>` : ''}
    `;
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
        // Load data for tabs that need it
        if (tab.dataset.tab === 'configs') loadConfigList();
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
    // History config dropdown (has "All" option)
    const historyConfig = document.getElementById('history-config');
    if (historyConfig) {
        historyConfig.innerHTML = '<option value="">All configs</option>';
        configs.forEach(c => {
            const opt = document.createElement('option');
            opt.value = c.id;
            opt.textContent = `${c.name} (${c.model}, t=${c.temperature})`;
            if (c.is_default) opt.textContent += ' *';
            historyConfig.appendChild(opt);
        });
    }

    // Workbench config dropdown (select default)
    const wbConfig = document.getElementById('wb-config');
    if (wbConfig) {
        wbConfig.innerHTML = '';
        configs.forEach(c => {
            const opt = document.createElement('option');
            opt.value = c.id;
            opt.textContent = `${c.name} (${c.model}, t=${c.temperature})`;
            if (c.is_default) { opt.textContent += ' *'; opt.selected = true; }
            wbConfig.appendChild(opt);
        });
    }
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
            `<p class="error-text">Error: ${escapeHtml(e.message)}</p>`;
    }
}

function renderBrowseResults(items, total) {
    const container = document.getElementById('browse-results');
    if (!items.length) {
        container.innerHTML = '<p class="muted-text">No comments found.</p>';
        document.getElementById('browse-pagination').innerHTML = '';
        return;
    }

    let html = `<table><thead><tr>
        <th class="col-check"><input type="checkbox" id="browse-check-all" /></th>
        <th>ID</th><th>Author</th><th>Body</th>
        <th>Sentiment</th><th>Conf</th><th>Score</th>
    </tr></thead><tbody>`;

    items.forEach(c => {
        const checked = selectedIds.has(c.reddit_id) ? ' checked' : '';
        html += `<tr class="browse-row${checked ? ' selected' : ''}" data-id="${escapeHtml(c.reddit_id)}">
            <td class="col-check"><input type="checkbox" class="browse-check" data-id="${escapeHtml(c.reddit_id)}"${checked} /></td>
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

    // Checkbox handlers
    container.querySelectorAll('.browse-check').forEach(cb => {
        cb.addEventListener('change', (e) => {
            e.stopPropagation();
            const id = cb.dataset.id;
            if (cb.checked) {
                selectedIds.add(id);
                cb.closest('tr').classList.add('selected');
                // Load full comment data
                loadCommentForWorkbench(id);
            } else {
                selectedIds.delete(id);
                selectedComments.delete(id);
                cb.closest('tr').classList.remove('selected');
            }
            updateSelectionUI();
        });
    });

    // Check-all header
    const checkAll = document.getElementById('browse-check-all');
    if (checkAll) {
        checkAll.checked = items.length > 0 && items.every(c => selectedIds.has(c.reddit_id));
        checkAll.addEventListener('change', () => {
            const checks = container.querySelectorAll('.browse-check');
            checks.forEach(cb => {
                cb.checked = checkAll.checked;
                const id = cb.dataset.id;
                if (checkAll.checked) {
                    selectedIds.add(id);
                    cb.closest('tr').classList.add('selected');
                    loadCommentForWorkbench(id);
                } else {
                    selectedIds.delete(id);
                    selectedComments.delete(id);
                    cb.closest('tr').classList.remove('selected');
                }
            });
            updateSelectionUI();
        });
    }

    renderPagination('browse-pagination', total, browseOffset, BROWSE_LIMIT, browseComments);
}

async function loadCommentForWorkbench(redditId) {
    if (selectedComments.has(redditId)) return;
    try {
        const data = await apiFetch(`/comments/${redditId}`);
        selectedComments.set(redditId, data.data);
        renderWorkbenchComments();
    } catch (e) {
        console.error(`Failed to load comment ${redditId}:`, e);
    }
}

function updateSelectionUI() {
    const countEl = document.getElementById('browse-selection-count');
    const clearBtn = document.getElementById('browse-clear-sel');
    const n = selectedIds.size;

    if (n > 0) {
        countEl.textContent = `${n} selected`;
        countEl.style.display = '';
        clearBtn.style.display = '';
    } else {
        countEl.style.display = 'none';
        clearBtn.style.display = 'none';
    }

    renderWorkbenchComments();
}

document.getElementById('browse-clear-sel').addEventListener('click', () => {
    selectedIds.clear();
    selectedComments.clear();
    // Uncheck visible checkboxes
    document.querySelectorAll('.browse-check').forEach(cb => {
        cb.checked = false;
        cb.closest('tr').classList.remove('selected');
    });
    const checkAll = document.getElementById('browse-check-all');
    if (checkAll) checkAll.checked = false;
    updateSelectionUI();
});

document.getElementById('browse-btn').addEventListener('click', () => browseComments(0));
document.getElementById('browse-search').addEventListener('keydown', e => {
    if (e.key === 'Enter') browseComments(0);
});

// ---------------------------------------------------------------------------
// Workbench Tab — Selected Comments
// ---------------------------------------------------------------------------

function renderWorkbenchComments() {
    const list = document.getElementById('wb-comment-list');
    const countSpan = document.getElementById('wb-comment-count');
    const n = selectedIds.size;

    countSpan.textContent = `(${n})`;

    if (n === 0) {
        list.innerHTML = '<p class="placeholder">Select comments from the Browse tab</p>';
        return;
    }

    let html = '';
    for (const rid of selectedIds) {
        const c = selectedComments.get(rid);
        const preview = c ? truncate(c.body, 50) : 'Loading...';
        const author = c ? c.author : '';

        html += `<div class="wb-comment-item" data-id="${escapeHtml(rid)}">
            <div class="wb-comment-item-header">
                <span class="expand-icon">&#9654;</span>
                <span class="comment-id">${escapeHtml(rid)}</span>
                <span class="comment-author">by ${escapeHtml(author)}</span>
                <span class="comment-preview">${escapeHtml(preview)}</span>
                <button class="remove-btn" data-id="${escapeHtml(rid)}" title="Remove">&times;</button>
            </div>
            <div class="wb-comment-context">
                ${c ? renderCommentContext(c) : '<span class="spinner"></span> Loading...'}
            </div>
        </div>`;
    }

    list.innerHTML = html;

    // Expand/collapse handlers
    list.querySelectorAll('.wb-comment-item-header').forEach(header => {
        header.addEventListener('click', (e) => {
            if (e.target.classList.contains('remove-btn')) return;
            header.closest('.wb-comment-item').classList.toggle('expanded');
        });
    });

    // Remove handlers
    list.querySelectorAll('.remove-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const id = btn.dataset.id;
            selectedIds.delete(id);
            selectedComments.delete(id);
            // Uncheck in browse if visible
            const cb = document.querySelector(`.browse-check[data-id="${id}"]`);
            if (cb) { cb.checked = false; cb.closest('tr').classList.remove('selected'); }
            updateSelectionUI();
        });
    });
}

function renderCommentContext(c) {
    let html = '';

    // Meta line
    html += `<div class="context-meta">
        <span>trust: ${(c.author_trust_score || 0.5).toFixed(2)}</span>
        <span>score: ${c.score ?? '--'}</span>
        ${c.sentiment ? `<span>${sentimentBadge(c.sentiment)} conf: ${c.ai_confidence?.toFixed(2) || '--'}</span>` : ''}
    </div>`;

    // Post title
    if (c.post_title) {
        html += `<div class="context-section">
            <div class="context-label">Post Title</div>
            <div>${escapeHtml(c.post_title)}</div>
        </div>`;
    }

    // Post body
    if (c.post_selftext) {
        html += `<div class="context-section">
            <div class="context-label">Post Body</div>
            <div class="context-body">${escapeHtml(c.post_selftext)}</div>
        </div>`;
    }

    // Image description
    if (c.image_analysis) {
        html += `<div class="context-section">
            <div class="context-label">Image Description</div>
            <div class="context-body">${escapeHtml(c.image_analysis)}</div>
        </div>`;
    }

    // Parent chain
    if (c.parent_chain && Array.isArray(c.parent_chain) && c.parent_chain.length > 0) {
        html += `<div class="context-section">
            <div class="context-label">Parent Chain</div>`;
        c.parent_chain.forEach(p => {
            html += `<div class="parent-chain-item">
                <span class="chain-author">${escapeHtml(p.author || 'unknown')}</span>:
                ${escapeHtml(p.body || '')}
            </div>`;
        });
        html += '</div>';
    }

    // Comment body
    html += `<div class="context-section">
        <div class="context-label">Comment Body</div>
        <div class="context-body">${escapeHtml(c.body)}</div>
    </div>`;

    return html;
}

document.getElementById('wb-clear-all').addEventListener('click', () => {
    selectedIds.clear();
    selectedComments.clear();
    // Uncheck all visible browse checkboxes
    document.querySelectorAll('.browse-check').forEach(cb => {
        cb.checked = false;
        cb.closest('tr').classList.remove('selected');
    });
    const checkAll = document.getElementById('browse-check-all');
    if (checkAll) checkAll.checked = false;
    updateSelectionUI();
    // Clear matrix
    matrixResults = {};
    matrixColumns = [];
    document.getElementById('wb-output').innerHTML = '';
});

// ---------------------------------------------------------------------------
// Workbench Tab — Batch Run
// ---------------------------------------------------------------------------

document.getElementById('btn-batch-run').addEventListener('click', async () => {
    if (selectedIds.size === 0) return showInlineError('wb-output', 'Select comments from the Browse tab first.');

    const configId = document.getElementById('wb-config').value;
    if (!configId) return showInlineError('wb-output', 'Select a config.');

    const marketCtx = document.getElementById('wb-market-ctx').value;
    const tag = document.getElementById('wb-tag').value || null;

    const body = {
        reddit_ids: [...selectedIds],
        prompt_config_id: parseInt(configId),
        market_context: marketCtx === 'off' ? false : null,
        tag,
    };

    const output = document.getElementById('wb-output');
    output.innerHTML = '<span class="spinner"></span> Running batch analysis...';

    try {
        const res = await fetch(`${API}/batch-analyze`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });

        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err?.error?.message || `HTTP ${res.status}`);
        }

        const cid = parseInt(configId);

        // Add column if new
        if (!matrixColumns.includes(cid)) {
            matrixColumns.push(cid);
        }

        // Render matrix immediately with pending cells
        renderMatrix();

        for await (const event of parseSSE(res)) {
            if (event.type === 'summary') {
                renderBatchSummary(event);
            } else if (event.error) {
                // Store error in matrix
                const key = `${event.reddit_id}|${cid}`;
                matrixResults[key] = { error: event.error };
                renderMatrix();
            } else {
                // Store result
                const key = `${event.reddit_id}|${cid}`;
                matrixResults[key] = {
                    result: event.result,
                    usage: event.usage,
                    cost: event.cost,
                    run_id: event.tuning_run_id,
                };
                renderMatrix();
            }
        }
    } catch (e) {
        output.innerHTML = `<p class="error-text">Error: ${escapeHtml(e.message)}</p>`;
    }
});

document.getElementById('btn-wb-dry-run').addEventListener('click', async () => {
    if (selectedIds.size === 0) return showInlineError('wb-output', 'Select comments from the Browse tab first.');

    const configId = document.getElementById('wb-config').value;
    const marketCtx = document.getElementById('wb-market-ctx').value;

    // Use first selected comment
    const firstId = [...selectedIds][0];

    const body = {
        reddit_id: firstId,
        prompt_config_id: configId ? parseInt(configId) : null,
        market_context: marketCtx === 'off' ? false : null,
    };

    const output = document.getElementById('wb-output');
    output.innerHTML = '<span class="spinner"></span> Building prompts...';

    try {
        const data = await apiFetch('/dry-run', {
            method: 'POST',
            body: JSON.stringify(body),
        });
        const d = data.data;
        output.innerHTML = `
            <div class="result-panel">
                <h3>Dry Run — Prompts Preview (${escapeHtml(firstId)})</h3>
                <div class="prompt-display">
                    <span class="prompt-label">SYSTEM PROMPT</span>${escapeHtml(d.system_prompt)}
                </div>
                <div class="prompt-display mt-8">
                    <span class="prompt-label">USER PROMPT</span>${escapeHtml(d.user_prompt)}
                </div>
                ${d.market_context ? `<div class="prompt-display mt-8">
                    <span class="prompt-label">MARKET CONTEXT</span>${escapeHtml(d.market_context)}
                </div>` : ''}
            </div>
        `;
    } catch (e) {
        output.innerHTML = `<p class="error-text">Error: ${escapeHtml(e.message)}</p>`;
    }
});

function showInlineError(elementId, msg) {
    document.getElementById(elementId).innerHTML = `<p class="error-text">${escapeHtml(msg)}</p>`;
}

// ---------------------------------------------------------------------------
// Workbench Tab — Results Matrix
// ---------------------------------------------------------------------------

function renderMatrix() {
    const output = document.getElementById('wb-output');
    if (matrixColumns.length === 0) return;

    // Build column headers from configs
    const colHeaders = matrixColumns.map(cid => {
        const cfg = configs.find(c => c.id === cid);
        return cfg ? `${cfg.name} (t=${cfg.temperature})` : `Config #${cid}`;
    });

    let html = '<div class="results-matrix"><table><thead><tr>';
    html += '<th>Comment</th>';
    colHeaders.forEach(h => { html += `<th>${escapeHtml(h)}</th>`; });
    html += '</tr></thead><tbody>';

    const commentIds = [...selectedIds];

    commentIds.forEach(rid => {
        // Main row
        html += `<tr>`;
        html += `<td title="${escapeHtml(rid)}">${escapeHtml(rid)}</td>`;

        matrixColumns.forEach(cid => {
            const key = `${rid}|${cid}`;
            const data = matrixResults[key];

            if (!data) {
                html += `<td class="matrix-cell pending">--</td>`;
            } else if (data.error) {
                html += `<td class="matrix-cell error-text" title="${escapeHtml(data.error)}">err</td>`;
            } else {
                const r = data.result;
                html += `<td class="matrix-cell" data-key="${escapeHtml(key)}">
                    ${sentimentBadge(r.sentiment)}
                    <strong>${r.confidence?.toFixed(2) || '--'}</strong>
                    <span class="cell-rerun" data-rid="${escapeHtml(rid)}" data-cid="${cid}" title="Re-run">&#8635;</span>
                </td>`;
            }
        });

        html += '</tr>';

        // Detail row (hidden by default)
        const totalCols = matrixColumns.length + 1;
        html += `<tr class="matrix-detail-row" data-for="${escapeHtml(rid)}">
            <td colspan="${totalCols}" id="detail-content-${escapeHtml(rid)}"></td>
        </tr>`;
    });

    html += '</tbody></table></div>';

    // Preserve summary if it exists
    const existingSummary = output.querySelector('.batch-summary');
    const summaryHtml = existingSummary ? existingSummary.outerHTML : '';

    output.innerHTML = html + summaryHtml;

    // Cell click handlers (expand detail)
    output.querySelectorAll('.matrix-cell[data-key]').forEach(cell => {
        cell.addEventListener('click', (e) => {
            if (e.target.classList.contains('cell-rerun')) return;
            const key = cell.dataset.key;
            const rid = key.split('|')[0];
            const detailRow = output.querySelector(`.matrix-detail-row[data-for="${rid}"]`);
            if (!detailRow) return;

            const wasOpen = detailRow.classList.contains('open');
            // Close all detail rows
            output.querySelectorAll('.matrix-detail-row').forEach(r => r.classList.remove('open'));

            if (!wasOpen) {
                const data = matrixResults[key];
                if (data && !data.error) {
                    detailRow.querySelector('td').innerHTML = renderResultFields(data.result, data.usage, data.cost);
                }
                detailRow.classList.add('open');
            }
        });
    });

    // Re-run handlers
    output.querySelectorAll('.cell-rerun').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.stopPropagation();
            const rid = btn.dataset.rid;
            const cid = parseInt(btn.dataset.cid);
            btn.textContent = '...';
            try {
                const data = await apiFetch('/analyze', {
                    method: 'POST',
                    body: JSON.stringify({
                        reddit_id: rid,
                        prompt_config_id: cid,
                        market_context: document.getElementById('wb-market-ctx').value === 'off' ? false : null,
                        tag: document.getElementById('wb-tag').value || null,
                    }),
                });
                const r = data.data;
                matrixResults[`${rid}|${cid}`] = {
                    result: r.result,
                    usage: r.usage,
                    cost: r.cost,
                    run_id: r.tuning_run_id,
                };
                renderMatrix();
            } catch (err) {
                btn.textContent = '!';
                btn.title = err.message;
            }
        });
    });
}

function renderBatchSummary(event) {
    const output = document.getElementById('wb-output');
    // Remove existing summary
    const existing = output.querySelector('.batch-summary');
    if (existing) existing.remove();

    const counts = Object.entries(event.sentiment_counts || {})
        .map(([s, n]) => `${sentimentBadge(s)} ${n}/${event.total}`)
        .join(' &nbsp; ');

    const div = document.createElement('div');
    div.className = 'batch-summary';
    div.innerHTML = `
        <strong>Batch Summary:</strong> ${counts}<br>
        Success: ${event.success_count} | Errors: ${event.error_count} |
        Total cost: ${formatCost(event.total_cost)}
    `;
    output.appendChild(div);
}

// ---------------------------------------------------------------------------
// Configs Tab
// ---------------------------------------------------------------------------

async function loadConfigList() {
    const container = document.getElementById('config-list');
    container.innerHTML = '<span class="spinner"></span> Loading...';

    try {
        await loadConfigs();  // refresh global configs
        renderConfigList();
    } catch (e) {
        container.innerHTML = `<p class="error-text">Error: ${escapeHtml(e.message)}</p>`;
    }
}

function renderConfigList() {
    const container = document.getElementById('config-list');
    if (!configs.length) {
        container.innerHTML = '<p class="muted-text">No configs found.</p>';
        return;
    }

    let html = `<table class="config-table"><thead><tr>
        <th>Name</th><th>Model</th><th>Temp</th><th>Max Tokens</th>
        <th>Top P</th><th>Default</th><th>Actions</th>
    </tr></thead><tbody>`;

    configs.forEach(c => {
        const starClass = c.is_default ? 'default-star' : 'default-star inactive';
        html += `<tr data-config-id="${c.id}">
            <td>${escapeHtml(c.name)}</td>
            <td>${escapeHtml(c.model)}</td>
            <td>${c.temperature}</td>
            <td>${c.max_tokens}</td>
            <td>${c.top_p}</td>
            <td><span class="${starClass}" data-id="${c.id}" title="Set as default">&#9733;</span></td>
            <td class="config-actions">
                <button class="cfg-edit" data-id="${c.id}">Edit</button>
                <button class="cfg-dup" data-id="${c.id}">Dup</button>
                <button class="cfg-del danger" data-id="${c.id}">Del</button>
            </td>
        </tr>`;
    });

    html += '</tbody></table>';
    container.innerHTML = html;

    // Set-default handlers
    container.querySelectorAll('.default-star').forEach(star => {
        star.addEventListener('click', async () => {
            try {
                await apiFetch(`/configs/${star.dataset.id}/default`, { method: 'PUT' });
                await loadConfigList();
            } catch (e) {
                alert(e.message);
            }
        });
    });

    // Edit handlers
    container.querySelectorAll('.cfg-edit').forEach(btn => {
        btn.addEventListener('click', () => {
            const cfg = configs.find(c => c.id === parseInt(btn.dataset.id));
            if (cfg) showConfigForm(cfg);
        });
    });

    // Duplicate handlers
    container.querySelectorAll('.cfg-dup').forEach(btn => {
        btn.addEventListener('click', () => {
            const cfg = configs.find(c => c.id === parseInt(btn.dataset.id));
            if (cfg) {
                const dup = { ...cfg, id: null, name: `${cfg.name} (copy)`, is_default: false };
                showConfigForm(dup, true);
            }
        });
    });

    // Delete handlers
    container.querySelectorAll('.cfg-del').forEach(btn => {
        btn.addEventListener('click', async () => {
            if (!confirm('Delete this config? This cannot be undone.')) return;
            try {
                await apiFetch(`/configs/${btn.dataset.id}`, { method: 'DELETE' });
                await loadConfigList();
            } catch (e) {
                alert(e.message);
            }
        });
    });
}

function showConfigForm(config = null, isNew = false) {
    const container = document.getElementById('config-form-container');
    const isCreate = !config || !config.id || isNew;
    const title = isCreate ? 'New Config' : `Edit: ${config.name}`;

    container.innerHTML = `
        <div class="config-form">
            <h3>${escapeHtml(title)}</h3>
            <div class="config-form-grid">
                <div class="form-field">
                    <label>Name</label>
                    <input type="text" id="cf-name" value="${escapeHtml(config?.name || '')}" />
                </div>
                <div class="form-field">
                    <label>Model</label>
                    <input type="text" id="cf-model" value="${escapeHtml(config?.model || 'gpt-4o-mini')}" />
                </div>
                <div class="form-field">
                    <label>Temperature</label>
                    <input type="number" id="cf-temperature" value="${config?.temperature ?? 0.3}" min="0" max="2" step="0.1" />
                </div>
                <div class="form-field">
                    <label>Max Tokens</label>
                    <input type="number" id="cf-max-tokens" value="${config?.max_tokens ?? 500}" min="100" max="2000" />
                </div>
                <div class="form-field">
                    <label>Top P</label>
                    <input type="number" id="cf-top-p" value="${config?.top_p ?? 1.0}" min="0" max="1" step="0.05" />
                </div>
                <div class="form-field">
                    <label>Frequency Penalty</label>
                    <input type="number" id="cf-freq-penalty" value="${config?.frequency_penalty ?? ''}" min="-2" max="2" step="0.1" />
                </div>
                <div class="form-field">
                    <label>Presence Penalty</label>
                    <input type="number" id="cf-pres-penalty" value="${config?.presence_penalty ?? ''}" min="-2" max="2" step="0.1" />
                </div>
                <div class="form-field">
                    <label>Provider</label>
                    <input type="text" id="cf-provider" value="${escapeHtml(config?.provider || 'openai')}" />
                </div>
            </div>
            <div class="config-form-grid full-width">
                <div class="form-field">
                    <label>System Prompt</label>
                    <textarea id="cf-system-prompt">${escapeHtml(config?.system_prompt || '')}</textarea>
                </div>
            </div>
            <div class="form-actions">
                <button class="btn primary" id="cf-save">${isCreate ? 'Create' : 'Save'}</button>
                <button class="btn" id="cf-cancel">Cancel</button>
            </div>
        </div>
    `;

    document.getElementById('cf-cancel').addEventListener('click', () => {
        container.innerHTML = '';
    });

    document.getElementById('cf-save').addEventListener('click', async () => {
        const payload = {
            name: document.getElementById('cf-name').value.trim(),
            system_prompt: document.getElementById('cf-system-prompt').value,
            model: document.getElementById('cf-model').value.trim(),
            temperature: parseFloat(document.getElementById('cf-temperature').value),
            max_tokens: parseInt(document.getElementById('cf-max-tokens').value),
            top_p: parseFloat(document.getElementById('cf-top-p').value),
            provider: document.getElementById('cf-provider').value.trim(),
        };

        const freqPenalty = document.getElementById('cf-freq-penalty').value;
        if (freqPenalty !== '') payload.frequency_penalty = parseFloat(freqPenalty);
        const presPenalty = document.getElementById('cf-pres-penalty').value;
        if (presPenalty !== '') payload.presence_penalty = parseFloat(presPenalty);

        if (!payload.name) return alert('Name is required.');
        if (!payload.system_prompt) return alert('System prompt is required.');

        try {
            if (isCreate) {
                await apiFetch('/configs', {
                    method: 'POST',
                    body: JSON.stringify(payload),
                });
            } else {
                await apiFetch(`/configs/${config.id}`, {
                    method: 'PUT',
                    body: JSON.stringify(payload),
                });
            }
            container.innerHTML = '';
            await loadConfigList();
        } catch (e) {
            alert(`Error: ${e.message}`);
        }
    });
}

document.getElementById('btn-new-config').addEventListener('click', () => {
    showConfigForm(null, true);
});

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
            `<p class="error-text">Error: ${escapeHtml(e.message)}</p>`;
    }
}

function renderHistory(items, total) {
    const container = document.getElementById('history-results');
    if (!items.length) {
        container.innerHTML = '<p class="muted-text">No tuning runs found.</p>';
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
            <div class="history-detail-grid">
                <div>
                    <strong>Reasoning:</strong> ${escapeHtml(r.reasoning_summary || 'none')}<br>
                    <strong>Tickers:</strong> ${escapeHtml(r.tickers || '[]')}<br>
                    <strong>Sarcasm:</strong> ${r.sarcasm_detected ? 'yes' : 'no'} |
                    <strong>Reasoning:</strong> ${r.has_reasoning ? 'yes' : 'no'}<br>
                    <strong>Tokens:</strong> ${r.prompt_tokens || 0} prompt / ${r.completion_tokens || 0} completion
                </div>
                <div>
                    ${r.user_prompt ? `<div class="prompt-display prompt-display-compact">${escapeHtml(truncate(r.user_prompt, 500))}</div>` : ''}
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
document.getElementById('history-reddit-id').addEventListener('keydown', e => {
    if (e.key === 'Enter') loadHistory(0);
});
document.getElementById('history-tag').addEventListener('keydown', e => {
    if (e.key === 'Enter') loadHistory(0);
});

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

(async function init() {
    await loadConfigs();
    browseComments(0);
})();
