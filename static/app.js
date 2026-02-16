(function () {
  const API = '';
  const fromSelect = document.getElementById('from');
  const toSelect = document.getElementById('to');
  const periodSelect = document.getElementById('period');
  const searchBtn = document.getElementById('search-btn');
  const dealsOrigin = document.getElementById('deals-origin');
  const tabs = document.querySelectorAll('.tab');
  const dealsLoading = document.getElementById('deals-loading');
  const dealsError = document.getElementById('deals-error');
  const dealsList = document.getElementById('deals-list');
  const searchResult = document.getElementById('search-result');
  const searchResultContent = document.getElementById('search-result-content');

  let airports = [];

  function fillAirports(select, exclude) {
    select.innerHTML = '<option value="">Select…</option>';
    airports.forEach(code => {
      if (code === exclude) return;
      const opt = document.createElement('option');
      opt.value = code;
      opt.textContent = code;
      select.appendChild(opt);
    });
  }

  async function loadAirports() {
    try {
      const res = await fetch(`${API}/api/airports`);
      const data = await res.json();
      airports = data.airports || [];
      fillAirports(fromSelect);
      fillAirports(toSelect);
      fillAirports(dealsOrigin);
    } catch (e) {
      console.error('Failed to load airports', e);
      dealsError.hidden = false;
      dealsError.textContent = 'Could not load airports. Is the server running?';
    }
  }

  function showDealsLoading(show) {
    dealsLoading.hidden = !show;
    if (show) dealsError.hidden = true;
  }

  function showDealsError(msg) {
    dealsError.hidden = false;
    dealsError.textContent = msg;
    dealsList.innerHTML = '';
  }

  function renderDeals(origin, period, deals) {
    dealsError.hidden = true;
    if (!deals || deals.length === 0) {
      dealsList.innerHTML = '<p class="loading">No deals found for this period. Run the scraper to populate data.</p>';
      return;
    }
    dealsList.innerHTML = deals.map(d => `
      <article class="deal-card">
        <div class="route">${origin} → ${d.destination}</div>
        <div class="price">$${Number(d.price).toFixed(2)}</div>
        <div class="meta">${d.departure_date ? d.departure_date + ' · ' : ''}${d.airline || '—'}${d.departure_time ? ' · ' + d.departure_time : ''}</div>
        <a class="book-link" href="${d.booking_url || '#'}" target="_blank" rel="noopener">View on Google Flights →</a>
      </article>
    `).join('');
  }

  async function fetchDeals(origin, period) {
    showDealsLoading(true);
    try {
      const res = await fetch(`${API}/api/deals?origin=${encodeURIComponent(origin)}&period=${encodeURIComponent(period)}`);
      if (!res.ok) throw new Error(res.statusText);
      const data = await res.json();
      renderDeals(data.origin, data.period, data.deals);
    } catch (e) {
      showDealsError(e.message || 'Failed to load deals');
    } finally {
      showDealsLoading(false);
    }
  }

  function getActivePeriod() {
    const t = document.querySelector('.tab.active');
    return t ? t.dataset.period : 'today';
  }

  dealsOrigin.addEventListener('change', function () {
    const origin = this.value;
    if (!origin) {
      dealsList.innerHTML = '';
      return;
    }
    fetchDeals(origin, getActivePeriod());
  });

  tabs.forEach(tab => {
    tab.addEventListener('click', function () {
      tabs.forEach(t => t.classList.remove('active'));
      this.classList.add('active');
      const origin = dealsOrigin.value;
      if (origin) fetchDeals(origin, this.dataset.period);
    });
  });

  searchBtn.addEventListener('click', async function () {
    const origin = fromSelect.value;
    const destination = toSelect.value;
    const period = periodSelect.value;
    if (!origin || !destination) {
      alert('Please select both From and To airports.');
      return;
    }
    searchResult.hidden = true;
    searchResultContent.innerHTML = '';
    try {
      const res = await fetch(
        `${API}/api/search?origin=${encodeURIComponent(origin)}&destination=${encodeURIComponent(destination)}&period=${encodeURIComponent(period)}`
      );
      if (res.status === 404) {
        searchResultContent.innerHTML = '<p class="error">No data for this route. Try another period or run the scraper.</p>';
        searchResult.hidden = false;
        return;
      }
      if (!res.ok) throw new Error(res.statusText);
      const r = await res.json();
      searchResultContent.innerHTML = `
        <div class="result-card">
          <div class="result-route">${r.origin} → ${r.destination}</div>
          <div class="result-price">$${Number(r.price).toFixed(2)}</div>
          <div class="result-meta">${r.departure_date ? r.departure_date + ' · ' : ''}${r.airline || '—'}${r.departure_time ? ' · ' + r.departure_time : ''}${r.duration ? ' · ' + r.duration : ''}</div>
          <a class="book-link" href="${r.booking_url || '#'}" target="_blank" rel="noopener">View on Google Flights →</a>
        </div>
      `;
      searchResult.hidden = false;
    } catch (e) {
      searchResultContent.innerHTML = '<p class="error">Search failed. ' + (e.message || '') + '</p>';
      searchResult.hidden = false;
    }
  });

  loadAirports();
})();
