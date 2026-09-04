// ═══════════════════════════════════════════════════════════════════════════
// DMARC Pipeline — per-file detail view (every parameter)
// ═══════════════════════════════════════════════════════════════════════════

const $ = (sel) => document.querySelector(sel);

function fmtDate(ts) {
  if (!ts) return '–';
  const d = new Date(typeof ts === 'number' ? ts * 1000 : ts);
  return d.toISOString().replace('T', ' ').slice(0, 19) + ' UTC';
}

function fmtCount(n) {
  if (n == null) return '0';
  return n.toLocaleString();
}

function fmtPct(n) {
  if (n == null) return '0%';
  return n.toFixed(1) + '%';
}

// Build a grid of key-value pairs
function detailGrid(items) {
  return `<div class="detail-grid">` + items.map(([key, value, cls = '']) => `
    <div class="detail-item">
      <div class="detail-key">${key}</div>
      <div class="detail-value ${cls}">${value}</div>
    </div>`).join('') + `</div>`;
}

async function loadDetail() {
  // Extract report ID from URL path: /file/123
  const pathParts = window.location.pathname.split('/');
  const reportId = pathParts[pathParts.length - 1];
  if (!reportId || reportId === 'file') {
    $('#metadata-grid').innerHTML = '<p style="color: var(--danger);">No report ID specified.</p>';
    return;
  }

  const res = await fetch(`/api/reports/${reportId}/detail`);
  if (!res.ok) {
    $('#metadata-grid').innerHTML = `<p style="color: var(--danger);">Report not found.</p>`;
    return;
  }

  const data = await res.json();
  renderDetail(data);
}

function renderDetail(data) {
  const r = data.report;
  const records = data.records;
  const analysis = data.analysis;

  // ── Breadcrumb + header ─────────────────────────────────────────────────
  $('#detail-filename').textContent = r.xml_filename;
  $('#detail-org').textContent = r.org_name || 'Unknown';
  $('#detail-record-count').textContent = `${records.length} record${records.length !== 1 ? 's' : ''}`;

  // ── Metadata grid ───────────────────────────────────────────────────────
  $('#metadata-grid').innerHTML = detailGrid([
    ['Organization', r.org_name || '–'],
    ['Organization email', r.org_email || '–'],
    ['Report ID', r.report_id || '–', 'mono'],
    ['Date range (begin)', fmtDate(r.date_begin)],
    ['Date range (end)', fmtDate(r.date_end)],
    ['Domain', r.domain || '–'],
    ['XML filename', r.xml_filename, 'mono'],
    ['Archive filename', r.archive_filename || '–', 'mono'],
    ['Ingested at', fmtDate(r.created_at)],
  ]);

  // ── Policy grid ─────────────────────────────────────────────────────────
  $('#policy-grid').innerHTML = detailGrid([
    ['Domain', r.domain || '–'],
    ['DKIM alignment mode (adkim)', r.adkim || '–'],
    ['SPF alignment mode (aspf)', r.aspf || '–'],
    ['Policy (p)', r.p || '–'],
    ['Subdomain policy (sp)', r.sp || '–'],
    ['Percentage applied (pct)', r.pct != null ? r.pct + '%' : '–'],
  ]);

  // ── Alignment summary ───────────────────────────────────────────────────
  const a = analysis.alignment;
  const o = analysis.overall;
  $('#detail-health-badge').textContent = `${o.health_score}/100 ${o.health_label}`;
  $('#detail-health-badge').className = `badge ${o.health_score >= 70 ? 'pass' : o.health_score >= 40 ? 'warn' : 'fail'}`;

  $('#alignment-summary').innerHTML = `
    <div class="detail-grid">
      <div class="detail-item">
        <div class="detail-key">DKIM pass</div>
        <div class="detail-value large" style="color: var(--success);">${fmtCount(a.dkim_pass)}</div>
      </div>
      <div class="detail-item">
        <div class="detail-key">DKIM fail</div>
        <div class="detail-value large" style="color: var(--danger);">${fmtCount(a.dkim_fail)}</div>
      </div>
      <div class="detail-item">
        <div class="detail-key">DKIM pass rate</div>
        <div class="detail-value large">${fmtPct(a.dkim_pass_rate)}</div>
      </div>
      <div class="detail-item">
        <div class="detail-key">SPF pass</div>
        <div class="detail-value large" style="color: var(--success);">${fmtCount(a.spf_pass)}</div>
      </div>
      <div class="detail-item">
        <div class="detail-key">SPF fail</div>
        <div class="detail-value large" style="color: var(--danger);">${fmtCount(a.spf_fail)}</div>
      </div>
      <div class="detail-item">
        <div class="detail-key">SPF pass rate</div>
        <div class="detail-value large">${fmtPct(a.spf_pass_rate)}</div>
      </div>
      <div class="detail-item">
        <div class="detail-key">Both pass</div>
        <div class="detail-value large">${fmtCount(a.both_pass)}</div>
      </div>
      <div class="detail-item">
        <div class="detail-key">Both fail</div>
        <div class="detail-value large" style="color: var(--danger);">${fmtCount(a.both_fail)}</div>
      </div>
      <div class="detail-item">
        <div class="detail-key">Either pass (DMARC compliant)</div>
        <div class="detail-value large" style="color: var(--accent);">${fmtCount(a.either_pass)}</div>
      </div>
      <div class="detail-item">
        <div class="detail-key">Overall pass rate</div>
        <div class="detail-value large" style="color: var(--accent);">${fmtPct(a.overall_pass_rate)}</div>
      </div>
    </div>`;

  // ── All records ─────────────────────────────────────────────────────────
  const container = $('#records-container');
  container.innerHTML = '';

  for (let i = 0; i < records.length; i++) {
    const rec = records[i];
    const card = document.createElement('div');
    card.className = 'record-card';

    // DKIM auth entries
    let dkimAuthHtml = '';
    if (rec.dkim_auth && rec.dkim_auth.length > 0) {
      dkimAuthHtml = `<div class="record-subsection">
        <div class="record-subsection-title">DKIM authentication results (${rec.dkim_auth.length})</div>`;
      for (const dk of rec.dkim_auth) {
        dkimAuthHtml += `<div class="auth-entry">
          <div class="auth-entry-row"><span class="auth-entry-key">Domain</span><span>${dk.domain || '–'}</span></div>
          <div class="auth-entry-row"><span class="auth-entry-key">Result</span><span class="badge ${dk.result === 'pass' ? 'pass' : 'fail'}">${dk.result || '–'}</span></div>
          <div class="auth-entry-row"><span class="auth-entry-key">Selector</span><span>${dk.selector || '–'}</span></div>
        </div>`;
      }
      dkimAuthHtml += `</div>`;
    }

    // SPF auth entries
    let spfAuthHtml = '';
    if (rec.spf_auth && rec.spf_auth.length > 0) {
      spfAuthHtml = `<div class="record-subsection">
        <div class="record-subsection-title">SPF authentication results (${rec.spf_auth.length})</div>`;
      for (const sp of rec.spf_auth) {
        spfAuthHtml += `<div class="auth-entry">
          <div class="auth-entry-row"><span class="auth-entry-key">Domain</span><span>${sp.domain || '–'}</span></div>
          <div class="auth-entry-row"><span class="auth-entry-key">Result</span><span class="badge ${sp.result === 'pass' ? 'pass' : 'fail'}">${sp.result || '–'}</span></div>
          <div class="auth-entry-row"><span class="auth-entry-key">Scope</span><span>${sp.scope || '–'}</span></div>
        </div>`;
      }
      spfAuthHtml += `</div>`;
    }

    card.innerHTML = `
      <div class="record-card-header">
        <div class="record-card-title">Record ${i + 1}</div>
        <span class="badge ${rec.dkim_aligned || rec.spf_aligned ? 'pass' : 'fail'}">
          ${rec.dkim_aligned || rec.spf_aligned ? 'ALIGNED' : 'NOT ALIGNED'}
        </span>
      </div>
      <div class="record-grid">
        <div class="detail-item">
          <div class="detail-key">Source IP</div>
          <div class="detail-value mono">${rec.source_ip || '–'}</div>
        </div>
        <div class="detail-item">
          <div class="detail-key">Count</div>
          <div class="detail-value large">${fmtCount(rec.count)}</div>
        </div>
        <div class="detail-item">
          <div class="detail-key">Header from</div>
          <div class="detail-value">${rec.header_from || '–'}</div>
        </div>
        <div class="detail-item">
          <div class="detail-key">Envelope from</div>
          <div class="detail-value">${rec.envelope_from || '–'}</div>
        </div>
        <div class="detail-item">
          <div class="detail-key">Envelope to</div>
          <div class="detail-value">${rec.envelope_to || '–'}</div>
        </div>
        <div class="detail-item">
          <div class="detail-key">Disposition</div>
          <div class="detail-value"><span class="badge ${rec.disposition === 'reject' ? 'fail' : rec.disposition === 'quarantine' ? 'warn' : 'pass'}">${rec.disposition || '–'}</span></div>
        </div>
        <div class="detail-item">
          <div class="detail-key">DKIM aligned</div>
          <div class="detail-value"><span class="badge ${rec.dkim_aligned ? 'pass' : 'fail'}">${rec.dkim_aligned ? 'YES' : 'NO'}</span></div>
        </div>
        <div class="detail-item">
          <div class="detail-key">SPF aligned</div>
          <div class="detail-value"><span class="badge ${rec.spf_aligned ? 'pass' : 'fail'}">${rec.spf_aligned ? 'YES' : 'NO'}</span></div>
        </div>
        <div class="detail-item">
          <div class="detail-key">DKIM result</div>
          <div class="detail-value"><span class="badge ${rec.dkim_result === 'pass' ? 'pass' : 'fail'}">${rec.dkim_result || '–'}</span></div>
        </div>
        <div class="detail-item">
          <div class="detail-key">SPF result</div>
          <div class="detail-value"><span class="badge ${rec.spf_result === 'pass' ? 'pass' : 'fail'}">${rec.spf_result || '–'}</span></div>
        </div>
        <div class="detail-item">
          <div class="detail-key">DKIM domain</div>
          <div class="detail-value">${rec.dkim_domain || '–'}</div>
        </div>
        <div class="detail-item">
          <div class="detail-key">SPF domain</div>
          <div class="detail-value">${rec.spf_domain || '–'}</div>
        </div>
      </div>
      ${dkimAuthHtml}
      ${spfAuthHtml}
    `;
    container.appendChild(card);
  }
}

// ── Init ──────────────────────────────────────────────────────────────────────

loadDetail();
