// ═══════════════════════════════════════════════════════════════════════════
// DMARC Pipeline — analysis report logic
// ═══════════════════════════════════════════════════════════════════════════

const $ = (sel) => document.querySelector(sel);

function fmtCount(n) {
  if (n == null) return '0';
  return n.toLocaleString();
}

function fmtPct(n) {
  if (n == null) return '0%';
  return n.toFixed(1) + '%';
}

async function loadAnalysis() {
  const res = await fetch('/api/analysis');
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  const data = await res.json();
  render(data);
}

function render(data) {
  const o = data.overall;
  const a = data.alignment;

  // ── Health ring ─────────────────────────────────────────────────────────
  const ring = $('#health-ring');
  ring.style.setProperty('--score', o.health_score);
  animateCount($('#health-score'), o.health_score, 1000);

  // Color the ring based on health
  const ringColor =
    o.health_score >= 90 ? 'var(--success)' :
    o.health_score >= 70 ? 'var(--accent)' :
    o.health_score >= 50 ? 'var(--warning)' :
    'var(--danger)';
  ring.style.background = `conic-gradient(${ringColor} ${o.health_score}%, var(--border) ${o.health_score}%)`;

  $('#summary-text').textContent = data.summary_text;
  $('#health-meta').textContent =
    `${fmtCount(o.total_reports)} reports · ${fmtCount(o.total_records)} records · ${fmtCount(o.total_messages)} messages · ${o.unique_domains} domains · ${o.unique_ips} IPs`;

  // ── Alignment strip ─────────────────────────────────────────────────────
  animateCount($('#dkim-pass'), a.dkim_pass || 0);
  $('#dkim-rate').textContent = fmtPct(a.dkim_pass_rate) + ' pass rate';
  animateCount($('#spf-pass'), a.spf_pass || 0);
  $('#spf-rate').textContent = fmtPct(a.spf_pass_rate) + ' pass rate';
  animateCount($('#both-pass'), a.both_pass || 0);
  animateCount($('#either-pass'), a.either_pass || 0);
  $('#either-rate').textContent = fmtPct(a.overall_pass_rate) + ' DMARC compliant';
  animateCount($('#both-fail'), a.both_fail || 0);

  // ── Recommendations ─────────────────────────────────────────────────────
  const recsEl = $('#recommendations');
  recsEl.innerHTML = '';
  for (const rec of data.recommendations) {
    const div = document.createElement('div');
    div.className = `rec-item ${rec.severity}`;
    div.innerHTML = `
      <div class="rec-title">${rec.title}</div>
      <div class="rec-detail">${rec.detail}</div>
      <span class="rec-action">→ ${rec.action}</span>
    `;
    recsEl.appendChild(div);
  }

  // ── Domains table ───────────────────────────────────────────────────────
  const domainsBody = $('#domains-table tbody');
  domainsBody.innerHTML = '';
  for (const d of data.domains) {
    const tr = document.createElement('tr');
    const rateColor = d.overall_pass_rate >= 90 ? 'var(--success)' :
                      d.overall_pass_rate >= 50 ? 'var(--warning)' : 'var(--danger)';
    tr.innerHTML = `
      <td>${d.domain}</td>
      <td>${fmtCount(d.messages)}</td>
      <td>${fmtCount(d.records)}</td>
      <td><span class="badge pass">${d.dkim_pass}</span> / <span class="badge fail">${d.dkim_fail}</span></td>
      <td><span class="badge pass">${d.spf_pass}</span> / <span class="badge fail">${d.spf_fail}</span></td>
      <td>${d.both_fail > 0 ? `<span class="badge fail">${d.both_fail}</span>` : '<span class="badge pass">0</span>'}</td>
      <td style="color: ${rateColor}; font-weight: 600;">${fmtPct(d.overall_pass_rate)}</td>
    `;
    domainsBody.appendChild(tr);
  }

  // ── IPs table ───────────────────────────────────────────────────────────
  const ipsBody = $('#ips-table tbody');
  ipsBody.innerHTML = '';
  for (const ip of data.top_ips) {
    const tr = document.createElement('tr');
    const disp = Object.keys(ip.dispositions)[0] || '–';
    const dispClass = disp === 'reject' ? 'fail' : disp === 'quarantine' ? 'warn' : 'pass';
    tr.innerHTML = `
      <td>${ip.ip}</td>
      <td>${fmtCount(ip.messages)}</td>
      <td>${fmtPct(ip.dkim_pass_rate)}</td>
      <td>${fmtPct(ip.spf_pass_rate)}</td>
      <td><span class="badge ${dispClass}">${disp}</span></td>
      <td>${ip.header_froms.join(', ')}</td>
    `;
    ipsBody.appendChild(tr);
  }

  // ── Sending services ────────────────────────────────────────────────────
  const servicesEl = $('#services');
  servicesEl.innerHTML = '<div class="service-grid"></div>';
  const grid = servicesEl.querySelector('.service-grid');
  for (const svc of data.sending_services) {
    const div = document.createElement('div');
    div.className = 'service-card';
    div.innerHTML = `
      <div class="service-name">${svc.service}</div>
      <div class="service-stat"><strong>${fmtCount(svc.messages)}</strong> messages</div>
      <div class="service-stat"><strong>${svc.ip_count}</strong> IP address${svc.ip_count !== 1 ? 'es' : ''}</div>
    `;
    grid.appendChild(div);
  }

  // ── Dispositions ────────────────────────────────────────────────────────
  const dispEl = $('#dispositions');
  dispEl.innerHTML = '';
  const totalDisp = Object.values(data.dispositions).reduce((a, b) => a + b, 0) || 1;
  const dispColors = { none: 'success', reject: 'danger', quarantine: 'warn' };
  for (const [name, count] of Object.entries(data.dispositions).sort((a, b) => b[1] - a[1])) {
    const pct = (count / totalDisp * 100).toFixed(1);
    const div = document.createElement('div');
    div.className = 'disp-row';
    div.innerHTML = `
      <span class="disp-label">${name}</span>
      <div class="disp-bar-track">
        <div class="disp-bar-fill ${dispColors[name] || ''}" style="width: ${pct}%"></div>
      </div>
      <span class="disp-value">${fmtCount(count)} (${pct}%)</span>
    `;
    dispEl.appendChild(div);
  }
}

function animateCount(el, target, duration = 800) {
  const start = performance.now();
  function tick(now) {
    const t = Math.min((now - start) / duration, 1);
    const eased = t === 1 ? 1 : 1 - Math.pow(2, -10 * t);
    el.textContent = Math.round(target * eased);
    if (t < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}

// ── Init ──────────────────────────────────────────────────────────────────────

loadAnalysis().catch(err => {
  $('#summary-text').textContent = `Error loading analysis: ${err.message}`;
  $('#summary-text').style.color = 'var(--danger)';
});
