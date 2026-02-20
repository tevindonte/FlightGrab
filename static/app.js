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
    if (CITY_IMAGES[airportCode]) return CITY_IMAGES[airportCode];
    return `/static/images/airports/${airportCode}.jpg`;
  }

  function getStateFallbackImage(airportCode) {
    const state = AIRPORT_TO_STATE[airportCode] || 'georgia';
    return `/static/images/states/${state}.jpg`;
  }

  function getFallbackImage(airportCode) {
    if (AIRPORT_TO_STATE[airportCode]) return getStateFallbackImage(airportCode);
    if (AIRPORT_TO_COUNTRY[airportCode]) return `https://flagcdn.com/w320/${AIRPORT_TO_COUNTRY[airportCode]}.png`;
    return '/static/images/states/georgia.jpg';
  }

  const AIRPORT_CITIES = {
    'ATL': 'Atlanta', 'DFW': 'Dallas', 'DEN': 'Denver', 'ORD': 'Chicago', 'LAX': 'Los Angeles',
    'CLT': 'Charlotte', 'MCO': 'Orlando', 'LAS': 'Las Vegas', 'PHX': 'Phoenix', 'MIA': 'Miami',
    'SEA': 'Seattle', 'IAH': 'Houston', 'EWR': 'Newark', 'SFO': 'San Francisco', 'BOS': 'Boston',
    'MSP': 'Minneapolis', 'DTW': 'Detroit', 'FLL': 'Fort Lauderdale', 'JFK': 'New York', 'LGA': 'New York',
    'PHL': 'Philadelphia', 'BWI': 'Baltimore', 'DCA': 'Washington', 'IAD': 'Washington', 'SAN': 'San Diego',
    'SLC': 'Salt Lake City', 'TPA': 'Tampa', 'PDX': 'Portland', 'HNL': 'Honolulu', 'AUS': 'Austin',
    'MDW': 'Chicago', 'BNA': 'Nashville', 'DAL': 'Dallas', 'RDU': 'Raleigh', 'STL': 'St. Louis',
    'HOU': 'Houston', 'SJC': 'San Jose', 'MCI': 'Kansas City', 'OAK': 'Oakland', 'SAT': 'San Antonio',
    'RSW': 'Fort Myers', 'IND': 'Indianapolis', 'CMH': 'Columbus', 'CVG': 'Cincinnati', 'PIT': 'Pittsburgh',
    'SMF': 'Sacramento', 'CLE': 'Cleveland', 'MKE': 'Milwaukee', 'SNA': 'Santa Ana', 'ANC': 'Anchorage',
    'DXB': 'Dubai', 'AUH': 'Abu Dhabi', 'DOH': 'Doha', 'SIN': 'Singapore', 'HKG': 'Hong Kong',
    'NRT': 'Tokyo', 'HND': 'Tokyo', 'ICN': 'Seoul', 'BKK': 'Bangkok', 'KUL': 'Kuala Lumpur',
    'LHR': 'London', 'CDG': 'Paris', 'FRA': 'Frankfurt', 'AMS': 'Amsterdam', 'BCN': 'Barcelona',
    'MAD': 'Madrid', 'FCO': 'Rome', 'DUB': 'Dublin', 'EDI': 'Edinburgh', 'MEX': 'Mexico City',
    'YYZ': 'Toronto', 'YVR': 'Vancouver', 'YUL': 'Montreal', 'SYD': 'Sydney', 'MEL': 'Melbourne',
    'AKL': 'Auckland', 'JNB': 'Johannesburg', 'CPT': 'Cape Town', 'CAI': 'Cairo', 'TLV': 'Tel Aviv',
    'DEL': 'Delhi', 'BOM': 'Mumbai', 'SJO': 'San Jose', 'PTY': 'Panama City',
  };

  const AIRPORT_TO_COUNTRY = {
    'DXB': 'ae', 'AUH': 'ae', 'SHJ': 'ae', 'DOH': 'qa', 'BAH': 'bh', 'KBL': 'af',
    'SIN': 'sg', 'HKG': 'hk', 'NRT': 'jp', 'HND': 'jp', 'ICN': 'kr', 'BKK': 'th',
    'KUL': 'my', 'DEL': 'in', 'BOM': 'in', 'DAC': 'bd',
    'LHR': 'gb', 'CDG': 'fr', 'FRA': 'de', 'AMS': 'nl', 'BCN': 'es', 'MAD': 'es',
    'FCO': 'it', 'DUB': 'ie', 'EDI': 'gb', 'VIE': 'at', 'BRU': 'be', 'ZRH': 'ch',
    'YYZ': 'ca', 'YVR': 'ca', 'YUL': 'ca', 'MEX': 'mx', 'GRU': 'br', 'EZE': 'ar',
    'SYD': 'au', 'MEL': 'au', 'BNE': 'au', 'AKL': 'nz',
    'JNB': 'za', 'CPT': 'za', 'CAI': 'eg', 'PTY': 'pa', 'SJO': 'cr', 'TLV': 'il',
    'ATL': 'us', 'LAX': 'us', 'MIA': 'us', 'SFO': 'us', 'DEN': 'us', 'ORD': 'us'
  };

  const CITY_IMAGES = {
    'DXB': 'https://images.unsplash.com/photo-1512453979798-5ea266f8880c?w=400&fit=crop',
    'AUH': 'https://images.unsplash.com/photo-1518684079-3c830dcef090?w=400&fit=crop',
    'DOH': 'https://images.unsplash.com/photo-1570701513264-e09c5d7ea2e5?w=400&fit=crop',
    'SIN': 'https://images.unsplash.com/photo-1525625293386-3f8f99389edd?w=400&fit=crop',
    'HKG': 'https://images.unsplash.com/photo-1536599018102-9f803c140fc1?w=400&fit=crop',
    'NRT': 'https://images.unsplash.com/photo-1540959733332-eab4deabeeaf?w=400&fit=crop',
    'HND': 'https://images.unsplash.com/photo-1540959733332-eab4deabeeaf?w=400&fit=crop',
    'ICN': 'https://images.unsplash.com/photo-1517154421773-0529f29ea451?w=400&fit=crop',
    'LHR': 'https://images.unsplash.com/photo-1513635269975-59663e0ac1ad?w=400&fit=crop',
    'CDG': 'https://images.unsplash.com/photo-1502602898657-3e91760cbb34?w=400&fit=crop',
    'FRA': 'https://images.unsplash.com/photo-1564981797816-1043664bf78d?w=400&fit=crop',
    'AMS': 'https://images.unsplash.com/photo-1534351590666-13e3e96b5017?w=400&fit=crop',
    'BCN': 'https://images.unsplash.com/photo-1583422409516-2895a77efded?w=400&fit=crop',
    'MAD': 'https://images.unsplash.com/photo-1539037116277-4db20889f2d4?w=400&fit=crop',
    'FCO': 'https://images.unsplash.com/photo-1552832230-c0197dd311b5?w=400&fit=crop',
    'DUB': 'https://images.unsplash.com/photo-1549918864-48ac978761a4?w=400&fit=crop',
    'EDI': 'https://images.unsplash.com/photo-1603231639062-0eb8b1d210c4?w=400&fit=crop',
    'YYZ': 'https://images.unsplash.com/photo-1517935706615-2717063c2225?w=400&fit=crop',
    'YVR': 'https://images.unsplash.com/photo-1503919545889-aef636e10ad4?w=400&fit=crop',
    'YUL': 'https://images.unsplash.com/photo-1497602172604-bfa09185fd5e?w=400&fit=crop',
    'SYD': 'https://images.unsplash.com/photo-1549180030-48bf079a38b1?w=400&fit=crop',
    'MEL': 'https://images.unsplash.com/photo-1545044846-351ba303b5b6?w=400&fit=crop',
    'MEX': 'https://images.unsplash.com/photo-1518639192441-8fce0a366e8e?w=400&fit=crop',
    'AKL': 'https://images.unsplash.com/photo-1507699629798-6870c2a0a90a?w=400&fit=crop',
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
      filtered = filtered.filter(function (d) { return (d.price || 0) <= f.maxPrice; });
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
        const oneWayPrice = Number(deal.price) || 0;
        const duration = deal.duration || '—';
        const stops = formatStops(deal.num_stops != null ? deal.num_stops : 0);
        const dateStr = formatDate(deal.departure_date);
        const imgSrc = getCityImage(code);
        const imgFallback = getFallbackImage(code);
        const origin = (deal.origin || currentOrigin || '').toUpperCase();
        const dest = (deal.destination || '').toUpperCase();
        const depDate = deal.departure_date || '';
        const bookRedirectUrl = origin && dest && depDate
          ? `${API}/api/book-redirect?origin=${encodeURIComponent(origin)}&destination=${encodeURIComponent(dest)}&date=${encodeURIComponent(depDate)}`
          : '#';
        const googleFlightsUrl = origin && dest && depDate
          ? `https://www.google.com/travel/flights?q=${encodeURIComponent('Flights from ' + origin + ' to ' + dest + ' on ' + depDate)}`
          : '#';
        const fallbackSvg = "data:image/svg+xml,%3Csvg%20xmlns%3D%27http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%27%20width%3D%27400%27%20height%3D%27300%27%3E%3Crect%20fill%3D%27%231a73e8%27%20width%3D%27400%27%20height%3D%27300%27%2F%3E%3C%2Fsvg%3E";
        const originBadge = mode === 'all' && deal.origin
          ? `<span class="origin-badge">from ${escapeHtml(getCityName(deal.origin))} (${deal.origin})</span>`
          : '';
        const dealJson = escapeAttr(JSON.stringify({
          origin, destination: dest, departure_date: depDate, price: oneWayPrice,
          airline: deal.airline, duration, num_stops: deal.num_stops,
          google_booking_url: deal.google_booking_url || ''
        }));
        return `
        <div class="deal-card" data-destination="${code}">
          <img class="card-image" src="${imgSrc}" alt="${cityName}" loading="lazy" data-fallback="${escapeAttr(imgFallback)}" data-final-fallback="${fallbackSvg}" onerror="if(this.dataset.tried){this.src=this.dataset.finalFallback}else{this.dataset.tried=1;this.src=this.dataset.fallback}">
          <div class="card-content">
            ${originBadge}
            <h3 class="city-name">${cityName}</h3>
            <p class="airport-code">${deal.destination}</p>
            <p class="flight-info">${duration}, ${stops}</p>
            <p class="flight-dates">Departs ${dateStr}</p>
            <p class="price">from $${Math.round(oneWayPrice)}</p>
            <p class="price-note">one-way</p>
            <div class="card-actions">
              <a class="btn-primary" href="${escapeAttr(bookRedirectUrl)}" target="_blank" rel="noopener" title="Book direct (~10 sec)">Book Now →</a>
              <a class="btn-secondary" href="${escapeAttr(googleFlightsUrl)}" target="_blank" rel="noopener">Compare on Google</a>
              <button type="button" class="btn-return" data-deal="${dealJson}">+ Add return flight</button>
            </div>
          </div>
        </div>
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
        const cheapest = Math.min.apply(null, deals.map(function (d) { return (d.price || 0); }));
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

  let selectedOutbound = null;
  let selectedReturn = null;
  let returnFlightsData = null;

  window.showReturnOptions = async function (deal) {
    if (typeof deal === 'string') {
      try { deal = JSON.parse(deal); } catch (e) { return; }
    }
    if (!deal || !deal.origin || !deal.destination || !deal.departure_date) return;

    selectedOutbound = deal;
    selectedReturn = null;
    const modal = document.getElementById('return-modal');
    const optionsEl = document.getElementById('return-options');
    const totalEl = document.getElementById('modal-total-price');
    const bookBothBtn = document.getElementById('book-both-btn');
    const returnSelectedEl = document.getElementById('return-selected');
    const returnPriceEl = document.getElementById('return-price');

    document.getElementById('outbound-route').textContent = deal.origin + ' → ' + deal.destination;
    document.getElementById('outbound-date').textContent = formatDate(deal.departure_date);
    document.getElementById('outbound-price').textContent = '$' + Math.round(deal.price);
    document.getElementById('return-route').textContent = deal.destination + ' → ' + deal.origin;
    returnSelectedEl.textContent = 'Select a return flight below';
    returnPriceEl.textContent = '—';
    totalEl.textContent = '—';
    bookBothBtn.disabled = true;
    optionsEl.innerHTML = '<p class="loading-return">Loading return options...</p>';

    modal.classList.remove('hidden');
    modal.setAttribute('aria-hidden', 'false');

    try {
      const url = `${API}/api/return-flights?origin=${encodeURIComponent(deal.origin)}&destination=${encodeURIComponent(deal.destination)}&outbound_date=${encodeURIComponent(deal.departure_date)}&min_days=2&max_days=30`;
      const res = await fetch(url);
      const data = await res.json();
      returnFlightsData = data;
      if (!data.flights || data.flights.length === 0) {
        optionsEl.innerHTML = '<p class="no-return-options">No return flights found for this route. Try different dates on Google Flights.</p>';
        return;
      }
      optionsEl.innerHTML = data.flights.map(function (f) {
        const fJson = escapeAttr(JSON.stringify(f));
        return `<div class="return-option" data-flight="${fJson}">
          <div class="option-date">${formatDate(f.departure_date)}</div>
          <div class="option-details">${escapeHtml(f.airline || 'Multiple')} · ${f.duration || '—'} · ${formatStops(f.num_stops || 0)}</div>
          <div class="option-price">$${Math.round(f.price)}</div>
        </div>`;
      }).join('');
      optionsEl.querySelectorAll('.return-option').forEach(function (el) {
        el.addEventListener('click', function () {
          optionsEl.querySelectorAll('.return-option').forEach(function (o) { o.classList.remove('selected'); });
          el.classList.add('selected');
          try {
            selectedReturn = JSON.parse(el.dataset.flight);
            returnSelectedEl.textContent = formatDate(selectedReturn.departure_date);
            returnPriceEl.textContent = '$' + Math.round(selectedReturn.price);
            totalEl.textContent = '$' + Math.round(selectedOutbound.price + selectedReturn.price);
            bookBothBtn.disabled = false;
          } catch (e) {}
        });
      });
    } catch (e) {
      optionsEl.innerHTML = '<p class="no-return-options">Failed to load return flights. Please try again.</p>';
    }
  };

  window.closeReturnModal = function () {
    const modal = document.getElementById('return-modal');
    modal.classList.add('hidden');
    modal.setAttribute('aria-hidden', 'true');
  };

  const modal = document.getElementById('return-modal');
  if (modal) {
    const backdrop = modal.querySelector('.modal-backdrop');
    const closeBtn = modal.querySelector('.modal-close');
    if (backdrop) backdrop.addEventListener('click', closeReturnModal);
    if (closeBtn) closeBtn.addEventListener('click', closeReturnModal);
    modal.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') closeReturnModal();
    });
  }

  document.getElementById('book-both-btn')?.addEventListener('click', function () {
    if (!selectedOutbound || !selectedReturn) return;
    const outboundUrl = `${API}/api/book-redirect?origin=${encodeURIComponent(selectedOutbound.origin)}&destination=${encodeURIComponent(selectedOutbound.destination)}&date=${encodeURIComponent(selectedOutbound.departure_date)}`;
    const returnUrl = `${API}/api/book-redirect?origin=${encodeURIComponent(selectedReturn.origin)}&destination=${encodeURIComponent(selectedReturn.destination)}&date=${encodeURIComponent(selectedReturn.departure_date)}`;
    window.open(outboundUrl, '_blank');
    setTimeout(function () { window.open(returnUrl, '_blank'); }, 500);
    closeReturnModal();
  });

  document.getElementById('book-separate-btn')?.addEventListener('click', function () {
    if (!selectedOutbound || !selectedReturn) return;
    const outboundUrl = `${API}/api/book-redirect?origin=${encodeURIComponent(selectedOutbound.origin)}&destination=${encodeURIComponent(selectedOutbound.destination)}&date=${encodeURIComponent(selectedOutbound.departure_date)}`;
    const returnUrl = `${API}/api/book-redirect?origin=${encodeURIComponent(selectedReturn.origin)}&destination=${encodeURIComponent(selectedReturn.destination)}&date=${encodeURIComponent(selectedReturn.departure_date)}`;
    window.open(outboundUrl, '_blank');
    setTimeout(function () { window.open(returnUrl, '_blank'); }, 500);
    closeReturnModal();
  });

  if (dealsGrid) {
    dealsGrid.addEventListener('click', function (e) {
      const btn = e.target.closest('.btn-return');
      if (btn) {
        e.preventDefault();
        showReturnOptions(btn.dataset.deal ? JSON.parse(btn.dataset.deal) : null);
      }
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
