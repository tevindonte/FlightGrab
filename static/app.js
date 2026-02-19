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
  let currentOrigin = '';

  function setLoading(show) {
    if (loadingEl) loadingEl.classList.toggle('hidden', !show);
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

  function cardMatchesSearch(deal, query) {
    if (!query || !query.trim()) return true;
    const q = query.trim().toLowerCase();
    const city = getCityName(deal.destination).toLowerCase();
    const code = deal.destination.toLowerCase();
    return city.includes(q) || code.includes(q);
  }

  function renderCards(deals, searchQuery, origin) {
    let filtered = searchQuery
      ? deals.filter(d => cardMatchesSearch(d, searchQuery))
      : deals;

    const deduplicated = [];
    const bestByCity = {};
    for (const d of filtered) {
      const cityKey = getCityName(d.destination);
      const price = Number(d.price) || 999999;
      if (!bestByCity[cityKey] || price < (Number(bestByCity[cityKey].price) || 999999)) {
        bestByCity[cityKey] = d;
      }
    }
    filtered = Object.values(bestByCity).sort((a, b) => (Number(a.price) || 0) - (Number(b.price) || 0));

    if (noResultsEl) noResultsEl.classList.toggle('hidden', filtered.length > 0 || deals.length === 0);
    if (filtered.length === 0 && deals.length > 0) {
      if (dealsGrid) dealsGrid.innerHTML = '';
      return;
    }
    if (filtered.length === 0) {
      if (dealsGrid) dealsGrid.innerHTML = '';
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
        return `
        <a class="deal-card" href="${escapeAttr(bookingUrl)}" target="_blank" rel="noopener" data-destination="${code}">
          <img class="card-image" src="${imgSrc}" alt="${cityName}" loading="lazy" data-fallback="${stateFallback}" data-final-fallback="${fallbackSvg}" onerror="if(this.dataset.tried){this.src=this.dataset.finalFallback}else{this.dataset.tried=1;this.src=this.dataset.fallback}">
          <div class="card-content">
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
    } catch (err) {
      console.error('FlightGrab renderCards error:', err);
      dealsGrid.innerHTML = '<p class="error">Error displaying deals. Check console.</p>';
    }
  }

  async function fetchDeals(origin) {
    if (!origin) {
      dealsGrid.innerHTML = '';
      return;
    }
    currentOrigin = origin;
    setLoading(true);
    setError(null);
    try {
      // Use 'week' so we show data when DB has future dates only; use 'today' after running incremental for current day
      const res = await fetch(`${API}/api/deals?origin=${encodeURIComponent(origin)}&period=week`);
      if (!res.ok) throw new Error(res.statusText);
      const data = await res.json();
      allDeals = data.deals || [];
      renderCards(allDeals, searchInput ? searchInput.value.trim() : '', origin);
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
      originSelect.innerHTML = '<option value="">Select airport…</option>' +
        airports.map(code => `<option value="${code}">${code}</option>`).join('');
      const first = airports[0];
      if (first) {
        originSelect.value = first;
        fetchDeals(first);
      } else {
        setError('No airport data. Run the scraper first.');
      }
    } catch (e) {
      airports = FALLBACK_ORIGINS;
      originSelect.innerHTML = '<option value="">Select airport…</option>' +
        airports.map(code => `<option value="${code}">${code}</option>`).join('');
      originSelect.value = FALLBACK_ORIGINS[0];
      fetchDeals(FALLBACK_ORIGINS[0]);
    }
  }

  originSelect.addEventListener('change', function () {
    fetchDeals(this.value);
  });

  if (searchInput) {
    searchInput.addEventListener('input', function () {
      const q = this.value.trim();
      renderCards(allDeals, q, currentOrigin);
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
