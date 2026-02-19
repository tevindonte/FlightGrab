(function () {
  const API = '';

  function runApp() {
    const originSelect = document.getElementById('origin');
    const searchInput = document.getElementById('search-input');
    const loadingEl = document.getElementById('loading');
    const errorEl = document.getElementById('error');
    const noResultsEl = document.getElementById('no-results');
    const dealsGrid = document.getElementById('deals-grid');

    if (!originSelect || !dealsGrid) {
      console.error('FlightGrab: missing required DOM elements (origin or deals-grid)');
      return;
    }

  // Airport code -> state (images in /static/images/states/, run scripts/download_state_images.py)
  const AIRPORT_TO_STATE = {
    'ATL': 'georgia', 'DFW': 'texas', 'DEN': 'colorado', 'ORD': 'illinois',
    'LAX': 'california', 'CLT': 'north_carolina', 'MCO': 'florida',
    'LAS': 'nevada', 'PHX': 'arizona', 'MIA': 'florida', 'SEA': 'washington',
    'IAH': 'texas', 'EWR': 'new_jersey', 'SFO': 'california', 'BOS': 'massachusetts',
    'MSP': 'minnesota', 'DTW': 'michigan', 'FLL': 'florida', 'JFK': 'new_york',
    'LGA': 'new_york', 'PHL': 'pennsylvania', 'BWI': 'maryland', 'DCA': 'virginia',
    'IAD': 'virginia', 'SAN': 'california', 'SLC': 'utah', 'TPA': 'florida',
    'PDX': 'oregon', 'HNL': 'hawaii', 'AUS': 'texas', 'MDW': 'illinois',
    'BNA': 'tennessee', 'DAL': 'texas', 'RDU': 'north_carolina', 'STL': 'missouri',
    'HOU': 'texas', 'SJC': 'california', 'MCI': 'kansas', 'OAK': 'california',
    'SAT': 'texas', 'RSW': 'florida', 'IND': 'indiana', 'CMH': 'ohio',
    'CVG': 'kentucky', 'PIT': 'pennsylvania', 'SMF': 'california', 'CLE': 'ohio',
    'MKE': 'wisconsin', 'SNA': 'california', 'ANC': 'alaska',
  };

  function getCityImage(airportCode) {
    if (!airportCode) return '/static/images/states/georgia.jpg';
    return `/static/images/airports/${airportCode}.jpg`;
  }

  function getStateFallbackImage(airportCode) {
    const state = AIRPORT_TO_STATE[airportCode] || 'georgia';
    return `/static/images/states/${state}.jpg`;
  }

  const AIRPORT_CITIES = {
    'ATL': 'Atlanta',
    'DFW': 'Dallas',
    'DEN': 'Denver',
    'ORD': 'Chicago',
    'LAX': 'Los Angeles',
    'CLT': 'Charlotte',
    'MCO': 'Orlando',
    'LAS': 'Las Vegas',
    'PHX': 'Phoenix',
    'MIA': 'Miami',
    'SEA': 'Seattle',
    'IAH': 'Houston',
    'EWR': 'Newark',
    'SFO': 'San Francisco',
    'BOS': 'Boston',
    'MSP': 'Minneapolis',
    'DTW': 'Detroit',
    'FLL': 'Fort Lauderdale',
    'JFK': 'New York',
    'LGA': 'New York',
    'PHL': 'Philadelphia',
    'BWI': 'Baltimore',
    'DCA': 'Washington',
    'IAD': 'Washington',
    'SAN': 'San Diego',
    'SLC': 'Salt Lake City',
    'TPA': 'Tampa',
    'PDX': 'Portland',
    'HNL': 'Honolulu',
    'AUS': 'Austin',
    'MDW': 'Chicago',
    'BNA': 'Nashville',
    'DAL': 'Dallas',
    'RDU': 'Raleigh',
    'STL': 'St. Louis',
    'HOU': 'Houston',
    'SJC': 'San Jose',
    'MCI': 'Kansas City',
    'OAK': 'Oakland',
    'SAT': 'San Antonio',
    'RSW': 'Fort Myers',
    'IND': 'Indianapolis',
    'CMH': 'Columbus',
    'CVG': 'Cincinnati',
    'PIT': 'Pittsburgh',
    'SMF': 'Sacramento',
    'CLE': 'Cleveland',
    'MKE': 'Milwaukee',
    'SNA': 'Santa Ana',
    'ANC': 'Anchorage',
  };

  let airports = [];
  let allDeals = [];
  let currentOrigin = null;
  let currentMode = 'all';

  function setLoading(show) {
    if (loadingEl) loadingEl.classList.toggle('hidden', !show);
    if (dealsGrid) dealsGrid.classList.toggle('hidden', show);
    if (show) {
      if (errorEl) errorEl.classList.add('hidden');
      if (noResultsEl) noResultsEl.classList.add('hidden');
    }
  }

  function setError(msg) {
    if (errorEl) {
      errorEl.classList.toggle('hidden', !msg);
      errorEl.textContent = msg || '';
    }
    if (msg && dealsGrid) dealsGrid.innerHTML = '';
  }

  function formatDate(isoDate) {
    if (!isoDate) return '—';
    const d = new Date(isoDate + 'T12:00:00');
    const today = new Date();
    const tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);
    today.setHours(0, 0, 0, 0);
    tomorrow.setHours(0, 0, 0, 0);
    d.setHours(0, 0, 0, 0);
    if (d.getTime() === today.getTime()) return 'Today';
    if (d.getTime() === tomorrow.getTime()) return 'Tomorrow';
    return d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
  }

  function formatStops(numStops) {
    if (numStops === 0) return 'non-stop';
    return numStops === 1 ? '1 stop' : numStops + ' stops';
  }

  function getCityName(code) {
    return AIRPORT_CITIES[code] || code;
  }

  function escapeAttr(str) {
    if (str == null) return '';
    return String(str).replace(/\r?\n/g, ' ').replace(/"/g, '&quot;').trim();
  }

  function escapeHtml(str) {
    if (str == null) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function cardMatchesSearch(deal, query) {
    if (!query || !query.trim()) return true;
    const q = query.trim().toLowerCase();
    const city = getCityName(deal.destination).toLowerCase();
    const code = deal.destination.toLowerCase();
    const originCode = (deal.origin || '').toLowerCase();
    return city.includes(q) || code.includes(q) || (deal.origin && originCode.includes(q));
  }

  function parseDuration(str) {
    if (!str) return 999999;
    const parts = str.match(/(\d+)\s*hr|(\d+)\s*min/g);
    if (!parts) return 999999;
    let total = 0;
    parts.forEach(function (m) {
      if (m.includes('hr')) total += parseInt(m, 10) * 60;
      if (m.includes('min')) total += parseInt(m, 10);
    });
    return total;
  }

  function getFilterValues() {
    const nonstopEl = document.getElementById('filter-nonstop') || document.getElementById('filter-nonstop-mobile');
    const maxEl = document.getElementById('filter-max-price') || document.getElementById('filter-max-price-mobile');
    const sortEl = document.getElementById('sort-select') || document.getElementById('sort-select-mobile');
    return {
      nonstop: nonstopEl ? nonstopEl.checked : false,
      maxPrice: maxEl ? parseInt(maxEl.value, 10) : NaN,
      sortBy: sortEl ? sortEl.value : 'price-asc'
    };
  }

  function syncFiltersToMobile() {
    const n = document.getElementById('filter-nonstop');
    const m = document.getElementById('filter-nonstop-mobile');
    const p = document.getElementById('filter-max-price');
    const pm = document.getElementById('filter-max-price-mobile');
    const s = document.getElementById('sort-select');
    const sm = document.getElementById('sort-select-mobile');
    if (n && m) m.checked = n.checked;
    if (p && pm) pm.value = p.value;
    if (s && sm) sm.value = s.value;
  }

  function syncFiltersToDesktop() {
    const n = document.getElementById('filter-nonstop');
    const m = document.getElementById('filter-nonstop-mobile');
    const p = document.getElementById('filter-max-price');
    const pm = document.getElementById('filter-max-price-mobile');
    const s = document.getElementById('sort-select');
    const sm = document.getElementById('sort-select-mobile');
    if (n && m) n.checked = m.checked;
    if (p && pm) p.value = pm.value;
    if (s && sm) s.value = sm.value;
  }

  function applySortAndFilter(deals) {
    const f = getFilterValues();
    let filtered = deals.filter(function (d) { return d.price && Number(d.price) > 0; });
    if (f.nonstop) filtered = filtered.filter(function (d) { return (d.num_stops || 0) === 0; });
    if (!isNaN(f.maxPrice) && f.maxPrice > 0) {
      filtered = filtered.filter(function (d) { return (d.price || 0) * 2 <= f.maxPrice; });
    }

    switch (f.sortBy) {
      case 'price-asc':
        filtered.sort(function (a, b) { return (a.price || 0) - (b.price || 0); });
        break;
      case 'price-desc':
        filtered.sort(function (a, b) { return (b.price || 0) - (a.price || 0); });
        break;
      case 'date-asc':
        filtered.sort(function (a, b) {
          return new Date(a.departure_date || 0) - new Date(b.departure_date || 0);
        });
        break;
      case 'duration-asc':
        filtered.sort(function (a, b) {
          return parseDuration(a.duration) - parseDuration(b.duration);
        });
        break;
    }
    return filtered;
  }

  function filtersAreActive() {
    const f = getFilterValues();
    return f.nonstop || (!isNaN(f.maxPrice) && f.maxPrice > 0);
  }

  function updateFilterIndicators(filteredCount) {
    const f = getFilterValues();
    const countEl = document.getElementById('nonstop-count');
    const countElM = document.getElementById('nonstop-count-mobile');
    const text = f.nonstop && filteredCount > 0 ? ' (' + filteredCount + ' flights)' : '';
    if (countEl) countEl.textContent = text;
    if (countElM) countElM.textContent = text;

    const clearBtn = document.getElementById('clear-filters');
    const clearBtnM = document.getElementById('clear-filters-mobile');
    const showClear = filtersAreActive();
    if (clearBtn) clearBtn.classList.toggle('hidden', !showClear);
    if (clearBtnM) clearBtnM.classList.toggle('hidden', !showClear);
  }

  function clearFilters() {
    const n = document.getElementById('filter-nonstop');
    const m = document.getElementById('filter-nonstop-mobile');
    const p = document.getElementById('filter-max-price');
    const pm = document.getElementById('filter-max-price-mobile');
    if (n) n.checked = false;
    if (m) m.checked = false;
    if (p) p.value = '';
    if (pm) pm.value = '';
    refreshFromControls();
  }

  function renderCards(deals, searchQuery, mode) {
    let filtered = deals.filter(function (d) { return d.price && Number(d.price) > 0; });
    filtered = searchQuery
      ? filtered.filter(function (d) { return cardMatchesSearch(d, searchQuery); })
      : filtered;

    const bestByCity = {};
    for (let i = 0; i < filtered.length; i++) {
      const d = filtered[i];
      const cityKey = getCityName(d.destination);
      const price = Number(d.price) || 999999;
      if (!bestByCity[cityKey] || price < (Number(bestByCity[cityKey].price) || 999999)) {
        bestByCity[cityKey] = d;
      }
    }
    filtered = Object.keys(bestByCity).map(function (k) { return bestByCity[k]; });
    filtered = applySortAndFilter(filtered);

    if (noResultsEl) noResultsEl.classList.toggle('hidden', filtered.length > 0 || deals.length === 0);
    if (filtered.length === 0 && deals.length > 0) {
      if (dealsGrid) dealsGrid.innerHTML = '';
      updateStats([]);
      updateFilterIndicators(0);
      return;
    }
    if (filtered.length === 0) {
      if (dealsGrid) dealsGrid.innerHTML = '';
      updateStats([]);
      updateFilterIndicators(0);
      return;
    }

    if (!dealsGrid) return;
    try {
      const html = filtered.map(deal => {
        const cityName = getCityName(deal.destination);
        const code = deal.destination || '';
        const roundTripPrice = (Number(deal.price) || 0) * 2;
        const duration = deal.duration || '—';
        const stops = formatStops(deal.num_stops != null ? deal.num_stops : 0);
        const dateStr = formatDate(deal.departure_date);
        const imgSrc = getCityImage(code);
        const stateFallback = getStateFallbackImage(code);
        const bookingUrl = deal.booking_url ? escapeAttr(deal.booking_url) : '#';
        const fallbackSvg = "data:image/svg+xml,%3Csvg%20xmlns%3D%27http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%27%20width%3D%27400%27%20height%3D%27300%27%3E%3Crect%20fill%3D%27%231a73e8%27%20width%3D%27400%27%20height%3D%27300%27%2F%3E%3C%2Fsvg%3E";
        const originBadge = mode === 'all' && deal.origin
          ? `<span class="origin-badge">from ${deal.origin}</span>`
          : '';
        const airline = deal.airline || 'Multiple airlines';
        return `
        <a class="deal-card" href="${escapeAttr(bookingUrl)}" target="_blank" rel="noopener" data-destination="${code}">
          <img class="card-image" src="${imgSrc}" alt="${cityName}" loading="lazy" data-fallback="${stateFallback}" data-final-fallback="${fallbackSvg}" onerror="if(this.dataset.tried){this.src=this.dataset.finalFallback}else{this.dataset.tried=1;this.src=this.dataset.fallback}">
          <div class="preview-details">
            <p>✈️ ${escapeHtml(airline)}</p>
            <p>⏱️ ${duration}</p>
            <p>📅 Departs ${dateStr}</p>
            <span class="quick-book book-btn">Book Now →</span>
          </div>
          <div class="card-content">
            ${originBadge}
            <h3 class="city-name">${cityName}</h3>
            <p class="airport-code">${deal.destination}</p>
            <p class="flight-info">${duration}, ${stops}</p>
            <p class="flight-dates">Departs ${dateStr}</p>
            <p class="price">from $${Math.round(roundTripPrice)}</p>
            <p class="price-note">round-trip</p>
          </div>
        </a>
      `;
      }).join('');
      dealsGrid.innerHTML = html;
      updateStats(filtered);
      updateFilterIndicators(filtered.length);
    } catch (err) {
      console.error('FlightGrab renderCards error:', err);
      dealsGrid.innerHTML = '<p class="error">Error displaying deals. Check console.</p>';
    }
  }

  const dealsHeading = document.getElementById('deals-heading');

  function getPeriod() {
    const range = document.getElementById('date-range');
    return range ? range.value : 'week';
  }

  function updateStats(deals) {
    const countEl = document.getElementById('deal-count');
    const priceEl = document.getElementById('cheapest-price');
    const updateEl = document.getElementById('last-update');
    if (countEl) countEl.textContent = deals.length;
    if (priceEl) {
      if (deals.length === 0) {
        priceEl.textContent = '—';
      } else {
        const cheapest = Math.min.apply(null, deals.map(function (d) { return (d.price || 0) * 2; }));
        priceEl.textContent = '$' + Math.round(cheapest);
      }
    }
    if (updateEl) {
      updateEl.textContent = new Date().toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit'
      });
    }
  }

  const PERIOD_LABELS = {
    today: 'Today',
    tomorrow: 'Tomorrow',
    weekend: 'This Weekend',
    week: 'This Week',
    month: 'This Month',
    flexible: 'Flexible (30 days)'
  };

  function updateDealsHeading(mode, origin) {
    if (!dealsHeading) return;
    const periodLabel = PERIOD_LABELS[getPeriod()] || 'This Week';
    if (mode === 'all') {
      dealsHeading.textContent = 'Cheapest Flights ' + periodLabel + ' (From Any Airport)';
    } else {
      const cityName = getCityName(origin);
      dealsHeading.textContent = 'Cheapest Flights from ' + cityName + ' ' + periodLabel;
    }
  }

  async function fetchDeals(origin) {
    if (!origin) {
      dealsGrid.innerHTML = '';
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const period = getPeriod();
      let data;
      if (origin === 'ALL') {
        currentMode = 'all';
        currentOrigin = null;
        const res = await fetch(`${API}/api/deals/all?period=${encodeURIComponent(period)}`);
        if (!res.ok) throw new Error(res.statusText);
        data = await res.json();
        updateDealsHeading('all');
      } else {
        currentMode = 'specific';
        currentOrigin = origin;
        const res = await fetch(`${API}/api/deals?origin=${encodeURIComponent(origin)}&period=${encodeURIComponent(period)}`);
        if (!res.ok) throw new Error(res.statusText);
        data = await res.json();
        updateDealsHeading('specific', origin);
      }
      allDeals = data.deals || [];
      renderCards(allDeals, searchInput ? searchInput.value.trim() : '', currentMode);
    } catch (e) {
      setError(e.message || 'Failed to load deals');
      allDeals = [];
    } finally {
      setLoading(false);
    }
  }

  const FALLBACK_ORIGINS = ['ATL', 'DFW', 'DEN', 'LAX', 'ORD'];

  async function loadAirports() {
    try {
      const res = await fetch(`${API}/api/airports?with_data=true`);
      const data = await res.json();
      airports = Array.isArray(data.airports) && data.airports.length > 0
        ? data.airports
        : FALLBACK_ORIGINS;
      const allOption = '<option value="ALL">All Airports (Cheapest Deals)</option>';
      originSelect.innerHTML = allOption +
        airports.map(code => `<option value="${code}">${getCityName(code)} (${code})</option>`).join('');
      originSelect.value = 'ALL';
      fetchDeals('ALL');
    } catch (e) {
      airports = FALLBACK_ORIGINS;
      originSelect.innerHTML = '<option value="ALL">All Airports (Cheapest Deals)</option>' +
        airports.map(code => `<option value="${code}">${getCityName(code)} (${code})</option>`).join('');
      originSelect.value = 'ALL';
      fetchDeals('ALL');
    }
  }

  function refreshFromControls() {
    const searchQ = searchInput ? searchInput.value.trim() : '';
    renderCards(allDeals, searchQ, currentMode);
  }

  originSelect.addEventListener('change', function () {
    fetchDeals(this.value);
  });

  const dateRangeEl = document.getElementById('date-range');
  if (dateRangeEl) {
    dateRangeEl.addEventListener('change', function () {
      fetchDeals(originSelect.value);
    });
  }

  function onFilterChange(fromMobile) {
    if (fromMobile) syncFiltersToDesktop(); else syncFiltersToMobile();
    refreshFromControls();
  }

  const sortSelect = document.getElementById('sort-select');
  if (sortSelect) sortSelect.addEventListener('change', function () { onFilterChange(false); });

  const sortSelectM = document.getElementById('sort-select-mobile');
  if (sortSelectM) sortSelectM.addEventListener('change', function () { onFilterChange(true); });

  const filterNonstop = document.getElementById('filter-nonstop');
  if (filterNonstop) filterNonstop.addEventListener('change', function () { onFilterChange(false); });

  const filterNonstopM = document.getElementById('filter-nonstop-mobile');
  if (filterNonstopM) filterNonstopM.addEventListener('change', function () { onFilterChange(true); });

  const filterMaxPrice = document.getElementById('filter-max-price');
  if (filterMaxPrice) {
    filterMaxPrice.addEventListener('input', function () { onFilterChange(false); });
    filterMaxPrice.addEventListener('change', function () { onFilterChange(false); });
  }

  const filterMaxPriceM = document.getElementById('filter-max-price-mobile');
  if (filterMaxPriceM) {
    filterMaxPriceM.addEventListener('input', function () { onFilterChange(true); });
    filterMaxPriceM.addEventListener('change', function () { onFilterChange(true); });
  }

  const clearFiltersBtn = document.getElementById('clear-filters');
  const clearFiltersBtnM = document.getElementById('clear-filters-mobile');
  if (clearFiltersBtn) clearFiltersBtn.addEventListener('click', clearFilters);
  if (clearFiltersBtnM) clearFiltersBtnM.addEventListener('click', function () { clearFilters(); closeFilterDrawer(); });

  const mobileFilterBtn = document.getElementById('mobile-filter-btn');
  const filterDrawer = document.getElementById('filter-drawer');
  const drawerClose = document.getElementById('drawer-close');

  function openFilterDrawer() {
    if (filterDrawer) { filterDrawer.classList.add('open'); }
    if (mobileFilterBtn) { mobileFilterBtn.setAttribute('aria-expanded', 'true'); }
  }

  function closeFilterDrawer() {
    if (filterDrawer) { filterDrawer.classList.remove('open'); }
    if (mobileFilterBtn) { mobileFilterBtn.setAttribute('aria-expanded', 'false'); }
  }

  if (mobileFilterBtn && filterDrawer) {
    mobileFilterBtn.addEventListener('click', function () {
      if (filterDrawer.classList.contains('open')) {
        closeFilterDrawer();
      } else {
        syncFiltersToMobile();
        openFilterDrawer();
      }
    });
  }
  if (drawerClose) drawerClose.addEventListener('click', closeFilterDrawer);

  if (searchInput) {
    searchInput.addEventListener('input', function () {
      const q = this.value.trim();
      renderCards(allDeals, q, currentMode);
    });
    searchInput.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') e.preventDefault();
    });
  }

  loadAirports();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', runApp);
  } else {
    runApp();
  }
})();
