(function () {
  const API = '';

  let currentUser = null;
  let Clerk = null;

  async function loadClerkAndRun(publishableKey) {
    if (!publishableKey) {
      runApp();
      return;
    }
    return new Promise(function (resolve) {
      const script = document.createElement('script');
      script.src = 'https://accounts.clerk.dev/npm/@clerk/clerk-js@latest/dist/clerk.browser.js';
      script.async = true;
      script.setAttribute('data-clerk-publishable-key', publishableKey);
      script.onload = function () {
        Clerk = window.Clerk;
        runApp();
        resolve();
      };
      script.onerror = function () { runApp(); resolve(); };
      document.head.appendChild(script);
    });
  }

  async function initializeAuth() {
    if (!Clerk) return;
    try {
      await Clerk.load();
      if (Clerk.user) {
        currentUser = {
          id: Clerk.user.id,
          email: Clerk.user.primaryEmailAddress?.emailAddress || '',
          firstName: Clerk.user.firstName || 'Account',
          avatar: Clerk.user.imageUrl || ''
        };
        document.getElementById('user-name').textContent = currentUser.firstName;
        document.getElementById('user-avatar').src = currentUser.avatar || 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="%23666"/><rect width="24" height="24" fill="%23ddd"/></svg>';
        document.getElementById('user-avatar').alt = currentUser.firstName;
        document.getElementById('user-menu').style.display = 'flex';
        document.getElementById('user-menu').classList.add('header-auth-visible');
        document.getElementById('sign-in-section').style.display = 'none';
        Clerk.session.getToken().then(function (token) {
          fetch((typeof API !== 'undefined' ? API : '') + '/api/date-preferences', { headers: { 'Authorization': 'Bearer ' + token } })
            .then(function (r) { return r.json(); })
            .then(function (data) {
              if (data && data.date_from && data.date_to) window.preferredDates = data;
            })
            .catch(function () {});
        }).catch(function () {});
      } else {
        document.getElementById('sign-in-section').style.display = 'flex';
        document.getElementById('sign-in-section').classList.add('header-auth-visible');
        document.getElementById('user-menu').style.display = 'none';
      }
    } catch (e) {
      document.getElementById('sign-in-section').style.display = 'flex';
      document.getElementById('sign-in-section').classList.add('header-auth-visible');
    }
  }

  function tryPendingAlert() {
    try {
      const raw = sessionStorage.getItem('flightgrab_pending_alert');
      if (!raw || !currentUser) return;
      const data = JSON.parse(raw);
      sessionStorage.removeItem('flightgrab_pending_alert');
      if (!data.origin || !data.destination) return;
      openAlertModal(data);
    } catch (e) {}
  }

  async function tryPendingSave() {
    try {
      const raw = sessionStorage.getItem('flightgrab_pending_save');
      if (!raw || !currentUser) return;
      const pending = JSON.parse(raw);
      sessionStorage.removeItem('flightgrab_pending_save');
      if (!pending.origin || !pending.destination) return;
      let token = '';
      if (Clerk && Clerk.session) token = await Clerk.session.getToken({ skipCache: true });
      if (!token) return;
      const res = await fetch(`${API}/api/saved-flights`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
        body: JSON.stringify({ origin: pending.origin, destination: pending.destination })
      });
      if (res.ok) {
        const btn = document.querySelector('.btn-save-flight[data-save-origin="' + pending.origin + '"][data-save-dest="' + pending.destination + '"]');
        if (btn) { btn.textContent = 'Saved ✓'; btn.classList.add('saved'); btn.disabled = true; }
        openSavedFlightsModal();
      }
    } catch (e) {}
  }

  function runApp() {
    const originSelect = document.getElementById('origin');
    const originInput = document.getElementById('origin-input');
    const originListbox = document.getElementById('origin-listbox');
    const originCombobox = document.querySelector('.origin-combobox');
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

  function getFallbackImage(airportCode) {
    if (AIRPORT_TO_STATE[airportCode]) return getStateFallbackImage(airportCode);
    if (AIRPORT_TO_COUNTRY[airportCode]) return `https://flagcdn.com/w320/${AIRPORT_TO_COUNTRY[airportCode]}.png`;
    return '/static/images/states/georgia.jpg';
  }

  // Lat/lon for nearest-airport fallback (US origins from OpenFlights/OurAirports)
  const AIRPORT_COORDS = {
    'ATL': [33.6367, -84.428101], 'DFW': [32.896801, -97.038002], 'DEN': [39.860027, -104.673792],
    'ORD': [41.9786, -87.9048], 'LAX': [33.942501, -118.407997], 'CLT': [35.214, -80.9431],
    'MCO': [28.4294, -81.309], 'LAS': [36.083361, -115.151817], 'PHX': [33.435302, -112.005905],
    'MIA': [25.796011, -80.289751], 'SEA': [47.447943, -122.310276], 'IAH': [29.9844, -95.3414],
    'EWR': [40.6894, -74.170545], 'SFO': [37.619806, -122.374821], 'BOS': [42.36197, -71.0079],
    'MSP': [44.880081, -93.221741], 'DTW': [42.21377, -83.353786], 'FLL': [26.072599, -80.152702],
    'JFK': [40.639447, -73.779317], 'LGA': [40.777199, -73.872597], 'PHL': [39.871899, -75.241096],
    'BWI': [39.1754, -76.668297], 'DCA': [38.8521, -77.037697], 'IAD': [38.9445, -77.455803],
    'SAN': [32.733601, -117.19], 'SLC': [40.78886, -111.979866], 'TPA': [27.9755, -82.533203],
    'PDX': [45.588699, -122.598], 'HNL': [21.318387, -157.92567], 'AUS': [30.197535, -97.662015],
    'MDW': [41.786, -87.752403], 'BNA': [36.1245, -86.6782], 'DAL': [32.844776, -96.847653],
    'RDU': [35.878659, -78.7873], 'STL': [38.748697, -90.37], 'HOU': [29.645336, -95.276812],
    'SJC': [37.362452, -121.929188], 'MCI': [39.301699, -94.713893], 'OAK': [37.720085, -122.221184],
    'SAT': [29.533701, -98.469803], 'RSW': [26.534685, -81.752816], 'IND': [39.7173, -86.294403],
    'CMH': [39.998001, -82.891899], 'CVG': [39.048801, -84.667801], 'PIT': [40.491501, -80.232903],
    'SMF': [38.6954, -121.591003], 'CLE': [41.411701, -81.8498], 'MKE': [42.947201, -87.896599],
    'SNA': [33.675063, -117.869281], 'ANC': [61.179004, -149.992561],
    'CDG': [49.0097, 2.5478], 'LHR': [51.4700, -0.4543], 'FRA': [50.0379, 8.5622]
  };

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
    'LHR': 'London', 'CDG': 'Paris', 'ORY': 'Paris', 'FRA': 'Frankfurt', 'AMS': 'Amsterdam', 'BCN': 'Barcelona',
    'MAD': 'Madrid', 'FCO': 'Rome', 'DUB': 'Dublin', 'EDI': 'Edinburgh', 'MEX': 'Mexico City',
    'MUC': 'Munich', 'ZRH': 'Zurich', 'VIE': 'Vienna', 'ATH': 'Athens', 'IST': 'Istanbul',
    'CPH': 'Copenhagen', 'OSL': 'Oslo', 'ARN': 'Stockholm', 'PRG': 'Prague', 'BUD': 'Budapest',
    'WAW': 'Warsaw', 'LIS': 'Lisbon', 'BRU': 'Brussels',
    'YYZ': 'Toronto', 'YVR': 'Vancouver', 'YUL': 'Montreal', 'YTZ': 'Toronto',
    'SYD': 'Sydney', 'MEL': 'Melbourne',
    'AKL': 'Auckland', 'BNE': 'Brisbane', 'GRU': 'São Paulo', 'EZE': 'Buenos Aires',
    'JNB': 'Johannesburg', 'CPT': 'Cape Town', 'CAI': 'Cairo', 'TLV': 'Tel Aviv',
    'DEL': 'Delhi', 'BOM': 'Mumbai', 'SJO': 'San Jose', 'PTY': 'Panama City',
    'FAO': 'Faro', 'OPO': 'Porto', 'NAP': 'Naples', 'MXP': 'Milan',
    'AGP': 'Málaga', 'PMI': 'Palma de Mallorca', 'SVQ': 'Seville',
    'VLC': 'Valencia', 'BIO': 'Bilbao', 'SCL': 'Santiago', 'BOG': 'Bogotá',
    'CUN': 'Cancún', 'GIG': 'Rio de Janeiro', 'COR': 'Córdoba',
    'CNS': 'Cairns', 'PER': 'Perth', 'ADL': 'Adelaide', 'DUR': 'Durban',
    'NBO': 'Nairobi', 'ADD': 'Addis Ababa',
    'MNL': 'Manila', 'SGN': 'Ho Chi Minh City',
    'GVA': 'Geneva', 'CRL': 'Charleroi', 'NCE': 'Nice', 'LYS': 'Lyon',
    'HAM': 'Hamburg', 'STR': 'Stuttgart', 'DUS': 'Düsseldorf', 'CGN': 'Cologne',
    'BHX': 'Birmingham', 'MAN': 'Manchester', 'LPL': 'Liverpool', 'NCL': 'Newcastle',
    'NAS': 'Nassau', 'PUJ': 'Punta Cana', 'MBJ': 'Montego Bay', 'SXM': 'St. Maarten',
  };

  const AIRPORT_TO_COUNTRY = {
    'DXB': 'ae', 'AUH': 'ae', 'SHJ': 'ae', 'DOH': 'qa', 'BAH': 'bh', 'KBL': 'af',
    'YTZ': 'ca', 'ORY': 'fr',
    'SIN': 'sg', 'HKG': 'hk', 'NRT': 'jp', 'HND': 'jp', 'ICN': 'kr', 'BKK': 'th',
    'KUL': 'my', 'DEL': 'in', 'BOM': 'in', 'DAC': 'bd',
    'LHR': 'gb', 'CDG': 'fr', 'FRA': 'de', 'AMS': 'nl', 'BCN': 'es', 'MAD': 'es',
    'FCO': 'it', 'DUB': 'ie', 'EDI': 'gb', 'VIE': 'at', 'BRU': 'be', 'ZRH': 'ch',
    'YYZ': 'ca', 'YVR': 'ca', 'YUL': 'ca', 'MEX': 'mx', 'GRU': 'br', 'EZE': 'ar',
    'SYD': 'au', 'MEL': 'au', 'BNE': 'au', 'AKL': 'nz',
    'JNB': 'za', 'CPT': 'za', 'CAI': 'eg', 'PTY': 'pa', 'SJO': 'cr', 'TLV': 'il',
    'ARN': 'se', 'MUC': 'de', 'ATH': 'gr', 'IST': 'tr', 'CPH': 'dk', 'OSL': 'no',
    'PRG': 'cz', 'BUD': 'hu', 'WAW': 'pl', 'LIS': 'pt',
    'ATL': 'us', 'LAX': 'us', 'MIA': 'us', 'SFO': 'us', 'DEN': 'us', 'ORD': 'us'
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

    const airportCount = filtered.length;
    const allAirportDeals = filtered.slice();
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
      updateStats([], 0);
      updateFilterIndicators(0);
      return;
    }
    if (filtered.length === 0) {
      if (dealsGrid) dealsGrid.innerHTML = '';
      updateStats([], 0);
      updateFilterIndicators(0);
      return;
    }

    if (!dealsGrid) return;
    try {
      const html = filtered.map(deal => {
        const cityName = getCityName(deal.destination);
        const code = deal.destination || '';
        const oneWayPrice = Number(deal.price) || 0;
        const duration = deal.duration && String(deal.duration).trim() ? deal.duration : '';
        const stops = formatStops(deal.num_stops != null ? deal.num_stops : 0);
        const durationStops = duration ? duration + ', ' + stops : stops;
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
          ? `https://www.google.com/travel/flights?q=${encodeURIComponent('One way flights from ' + origin + ' to ' + dest + ' on ' + depDate)}`
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
        const imgWebp = `/static/images/airports/${code}.webp`;
        const otherRaw = allAirportDeals.filter(function (d) {
          return getCityName(d.destination) === cityName && (d.destination || '') !== (deal.destination || '');
        });
        const otherByDest = {};
        otherRaw.forEach(function (d) {
          const code = d.destination;
          const p = Number(d.price) || 999999;
          if (!otherByDest[code] || p < (Number(otherByDest[code].price) || 999999)) otherByDest[code] = d;
        });
        const otherAirports = Object.values(otherByDest).sort(function (a, b) { return (Number(a.price) || 0) - (Number(b.price) || 0); });
        const otherAirportsHTML = otherAirports.length > 0
          ? '<details class="other-airports"><summary>' + otherAirports.length + ' other airport' + (otherAirports.length > 1 ? 's' : '') + '</summary><div class="airport-alternatives">' +
            otherAirports.map(function (alt) {
              const altOrigin = (alt.origin || currentOrigin || '').toUpperCase();
              const altDest = (alt.destination || '').toUpperCase();
              const altDate = alt.departure_date || '';
              const altBookUrl = altOrigin && altDest && altDate ? API + '/api/book-redirect?origin=' + encodeURIComponent(altOrigin) + '&destination=' + encodeURIComponent(altDest) + '&date=' + encodeURIComponent(altDate) : '#';
              return '<a class="alt-airport" href="' + escapeAttr(altBookUrl) + '" target="_blank" rel="noopener" title="Book ' + escapeHtml(altDest) + ' $' + Math.round(Number(alt.price) || 0) + '"><span class="alt-name">' + escapeHtml(alt.destination || '') + '</span><span class="alt-price">$' + Math.round(Number(alt.price) || 0) + '</span></a>';
            }).join('') +
            '</div></details>'
          : '';
        return `
        <div class="deal-card" data-destination="${code}" data-origin="${escapeAttr(origin)}">
          <picture>
            <source srcset="${escapeAttr(imgWebp)}" type="image/webp">
            <img class="card-image" src="${imgSrc}" alt="${cityName}" loading="lazy" data-fallback="${escapeAttr(imgFallback)}" data-final-fallback="${fallbackSvg}" onerror="if(this.dataset.tried){this.src=this.dataset.finalFallback}else{this.dataset.tried=1;this.src=this.dataset.fallback}">
          </picture>
          <div class="card-content">
            ${originBadge}
            <h3 class="city-name">${cityName}</h3>
            <p class="airport-code">${deal.destination}</p>
            <p class="flight-info">${durationStops}</p>
            <p class="flight-dates">Departs ${dateStr}</p>
            <p class="price">from $${Math.round(oneWayPrice)}</p>
            <p class="price-note">one-way</p>
            ${otherAirportsHTML}
            <div class="card-actions">
              <a class="btn-primary" href="${escapeAttr(bookRedirectUrl)}" target="_blank" rel="noopener" title="Books via our link when available; otherwise opens Google Flights">Book Now →</a>
              <a class="btn-secondary" href="${escapeAttr(googleFlightsUrl)}" target="_blank" rel="noopener">Compare on Google</a>
              <button type="button" class="btn-alert" data-alert="${escapeAttr(JSON.stringify({ origin, destination: dest, departure_date: depDate, price: oneWayPrice }))}" title="Get notified when price drops">🔔 Set Price Alert</button>
              <button type="button" class="btn-share" data-share="${escapeAttr(JSON.stringify({ origin, destination: dest, departure_date: depDate, price: oneWayPrice }))}" title="Share this flight">📤 Share</button>
              <button type="button" class="btn-save-flight" data-save-origin="${escapeAttr(origin)}" data-save-dest="${escapeAttr(dest)}" title="Save this route">Save</button>
              <button type="button" class="btn-calendar" data-cal-origin="${escapeAttr(origin)}" data-cal-dest="${escapeAttr(dest)}" title="See prices by date">📅 Prices by date</button>
              <button type="button" class="btn-return" data-deal="${dealJson}">+ Add return flight</button>
            </div>
          </div>
        </div>
      `;
      }).join('');
      dealsGrid.innerHTML = html;
      updateStats(filtered, airportCount);
      updateFilterIndicators(filtered.length);
      updateCalendarOriginDisplay();
    } catch (err) {
      console.error('FlightGrab renderCards error:', err);
      dealsGrid.innerHTML = '<p class="error">Error displaying deals. Check console.</p>';
    }
  }

  const dealsHeading = document.getElementById('deals-heading');

  function updateCalendarOriginDisplay() {
    const valEl = document.getElementById('calendar-origin-value');
    const hintEl = document.getElementById('calendar-origin-hint');
    if (!valEl) return;
    const origin = (originSelect && originSelect.value) || currentOrigin || 'ALL';
    if (origin === 'ALL' || !origin) {
      valEl.textContent = '—';
      if (hintEl) hintEl.classList.remove('hidden');
    } else {
      valEl.textContent = getCityName(origin) + ' (' + origin + ')';
      if (hintEl) hintEl.classList.add('hidden');
    }
  }

  function getPeriod() {
    const range = document.getElementById('date-range');
    return range ? range.value : 'week';
  }

  function updateStats(deals, airportCount) {
    const countEl = document.getElementById('deal-count');
    const countLabel = document.getElementById('deal-count-label');
    const priceEl = document.getElementById('cheapest-price');
    const updateEl = document.getElementById('last-update');
    if (countEl) {
      countEl.textContent = deals.length;
      if (countLabel) {
        if (airportCount != null && airportCount > 0 && airportCount !== deals.length) {
          countLabel.textContent = ' cities · ' + airportCount + ' airports';
        } else {
          countLabel.textContent = ' destinations';
        }
      }
    }
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
    flexible: 'Flexible (30 days)',
    date: 'specific date',
    range: 'date range'
  };

  function updateDealsHeading(mode, origin) {
    if (!dealsHeading) return;
    const period = getPeriod();
    let periodLabel = PERIOD_LABELS[period] || 'This Week';
    if (period === 'date') {
      const specEl = document.getElementById('specific-date');
      const d = specEl && specEl.value ? new Date(specEl.value + 'T12:00:00') : null;
      periodLabel = d ? d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' }) : 'specific date';
    } else if (period === 'range') {
      const fromEl = document.getElementById('date-from');
      const toEl = document.getElementById('date-to');
      if (fromEl && toEl && fromEl.value && toEl.value) {
        const d1 = new Date(fromEl.value + 'T12:00:00');
        const d2 = new Date(toEl.value + 'T12:00:00');
        periodLabel = d1.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ' – ' + d2.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
      }
    }
    if (mode === 'all') {
      dealsHeading.textContent = 'Cheapest Flights ' + periodLabel + ' (From Any Airport)';
    } else {
      const cityName = getCityName(origin);
      dealsHeading.textContent = 'Cheapest Flights from ' + cityName + ' ' + periodLabel;
    }
  }

  function getClientDate() {
    const d = new Date();
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
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
      const clientDate = getClientDate();
      let dateParam = (period === 'today' || period === 'tomorrow') ? '&client_date=' + encodeURIComponent(clientDate) : '';
      if (period === 'date') {
        const specEl = document.getElementById('specific-date');
        const specDate = specEl && specEl.value ? specEl.value : clientDate;
        dateParam = '&specific_date=' + encodeURIComponent(specDate);
      } else if (period === 'range') {
        const fromEl = document.getElementById('date-from');
        const toEl = document.getElementById('date-to');
        const df = fromEl && fromEl.value ? fromEl.value : clientDate;
        const dt = toEl && toEl.value ? toEl.value : clientDate;
        dateParam = '&date_from=' + encodeURIComponent(df) + '&date_to=' + encodeURIComponent(dt);
      }
      const apiPeriod = (period === 'date' || period === 'range') ? period : period;
      let data;
      if (origin === 'ALL') {
        currentMode = 'all';
        currentOrigin = null;
        const res = await fetch(`${API}/api/deals/all?period=${encodeURIComponent(apiPeriod)}${dateParam}`);
        if (!res.ok) throw new Error(res.statusText);
        data = await res.json();
        updateDealsHeading('all');
      } else {
        currentMode = 'specific';
        currentOrigin = origin;
        const res = await fetch(`${API}/api/deals?origin=${encodeURIComponent(origin)}&period=${encodeURIComponent(apiPeriod)}${dateParam}`);
        if (!res.ok) throw new Error(res.statusText);
        data = await res.json();
        updateDealsHeading('specific', origin);
      }
      allDeals = data.deals || [];
      renderCards(allDeals, searchInput ? searchInput.value.trim() : '', currentMode);
      handleSharedLink();
    } catch (e) {
      setError(e.message || 'Failed to load deals');
      allDeals = [];
    } finally {
      setLoading(false);
    }
  }

  const FALLBACK_ORIGINS = ['ATL', 'DFW', 'DEN', 'LAX', 'ORD'];

  const ALL_AIRPORTS_OPTION = { value: 'ALL', label: 'All Airports (Cheapest Deals)' };

  function buildOriginOptions() {
    return [ALL_AIRPORTS_OPTION].concat(airports.map(function (code) {
      return { value: code, label: getCityName(code) + ' (' + code + ')' };
    }));
  }

  function renderOriginListbox(filter, show) {
    const options = buildOriginOptions();
    const q = (filter || '').toLowerCase().trim();
    const filtered = q
      ? options.filter(function (o) {
          return o.label.toLowerCase().includes(q) || o.value.toLowerCase().includes(q);
        })
      : options;
    if (!originListbox) return;
    originListbox.innerHTML = filtered.map(function (o) {
      return '<li role="option" data-value="' + escapeAttr(o.value) + '">' + escapeHtml(o.label) + '</li>';
    }).join('');
    const shouldShow = show !== false && filtered.length > 0;
    originListbox.classList.toggle('hidden', !shouldShow);
    if (originCombobox) originCombobox.setAttribute('aria-expanded', shouldShow);
  }

  function setOrigin(value, label) {
    if (originSelect) originSelect.value = value;
    if (originInput) originInput.value = label || (value === 'ALL' ? ALL_AIRPORTS_OPTION.label : getCityName(value) + ' (' + value + ')');
    if (originListbox) { originListbox.classList.add('hidden'); originListbox.innerHTML = ''; }
    if (originCombobox) originCombobox.setAttribute('aria-expanded', 'false');
    calendarDestinationsOrigin = null;
    updateCalendarOriginDisplay();
    fetchDeals(value);
  }

  const GEO_CACHE_KEY = 'fg_geocode';
  const GEO_CACHE_TTL_MS = 24 * 60 * 60 * 1000;
  let lastNominatimCall = 0;
  const NOMINATIM_MIN_INTERVAL_MS = 1100;

  function getGeocodeCacheKey(lat, lon) {
    const r = (n) => Math.round(n * 100) / 100;
    return r(lat) + ',' + r(lon);
  }

  function getCachedPlace(lat, lon) {
    try {
      const raw = localStorage.getItem(GEO_CACHE_KEY);
      if (!raw) return null;
      const cache = JSON.parse(raw);
      const key = getGeocodeCacheKey(lat, lon);
      const entry = cache[key];
      if (!entry || (Date.now() - entry.ts > GEO_CACHE_TTL_MS)) return null;
      return entry.place;
    } catch (_) { return null; }
  }

  function setCachedPlace(lat, lon, place) {
    try {
      const raw = localStorage.getItem(GEO_CACHE_KEY) || '{}';
      const cache = JSON.parse(raw);
      const key = getGeocodeCacheKey(lat, lon);
      cache[key] = { place, ts: Date.now() };
      const keys = Object.keys(cache);
      if (keys.length > 200) {
        const sorted = keys.sort((a, b) => cache[a].ts - cache[b].ts);
        for (let i = 0; i < sorted.length - 100; i++) delete cache[sorted[i]];
      }
      localStorage.setItem(GEO_CACHE_KEY, JSON.stringify(cache));
    } catch (_) {}
  }

  async function reverseGeocode(lat, lon) {
    const cached = getCachedPlace(lat, lon);
    if (cached) return cached;

    const delay = NOMINATIM_MIN_INTERVAL_MS - (Date.now() - lastNominatimCall);
    if (delay > 0) await new Promise(function (r) { setTimeout(r, delay); });

    const headers = { 'Accept': 'application/json' };
    const ua = 'FlightGrab/1.0 (flight deal finder; fair use)';

    try {
      lastNominatimCall = Date.now();
      const url = 'https://nominatim.openstreetmap.org/reverse?format=json&lat=' + lat + '&lon=' + lon + '&zoom=8';
      const res = await fetch(url, { headers: { ...headers, 'User-Agent': ua } });
      if (!res.ok) throw new Error('Nominatim ' + res.status);
      const data = await res.json();
      const addr = data.address || {};
      const place = (addr.city || addr.town || addr.village || addr.municipality || addr.county || addr.state || addr.region || '').toLowerCase();
      if (place) setCachedPlace(lat, lon, place);
      return place;
    } catch (e) {
      try {
        const fallback = 'https://api.bigdatacloud.net/data/reverse-geocode?latitude=' + lat + '&longitude=' + lon;
        const res2 = await fetch(fallback);
        if (!res2.ok) throw new Error('Fallback ' + res2.status);
        const data2 = await res2.json();
        const city = (data2.city || data2.locality || data2.principalSubdivision || data2.localityInfo?.administrative?.[0]?.name || '').toLowerCase();
        if (city) setCachedPlace(lat, lon, city);
        return city;
      } catch (_) {
        return '';
      }
    }
  }

  function matchPlaceToAirport(place, allOpts) {
    if (!place) return null;
    for (let i = 0; i < allOpts.length; i++) {
      const o = allOpts[i];
      if (o.value === 'ALL') continue;
      const cityName = getCityName(o.value).toLowerCase();
      if (cityName.includes(place) || place.includes(cityName)) return o;
    }
    return null;
  }

  function findNearestAirport(lat, lon, allOpts) {
    let best = null;
    let bestDist = Infinity;
    const toRad = function (d) { return d * Math.PI / 180; };
    const haversine = function (lat1, lon1, lat2, lon2) {
      const R = 6371;
      const dLat = toRad(lat2 - lat1);
      const dLon = toRad(lon2 - lon1);
      const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
        Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
      return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    };
    for (let i = 0; i < allOpts.length; i++) {
      const o = allOpts[i];
      if (o.value === 'ALL') continue;
      const c = AIRPORT_COORDS[o.value];
      if (!c) continue;
      const d = haversine(lat, lon, c[0], c[1]);
      if (d < bestDist) { bestDist = d; best = o; }
    }
    return best;
  }

  async function useLocation() {
    const btn = document.getElementById('btn-use-location');
    if (btn) { btn.disabled = true; btn.classList.add('loading'); btn.title = 'Detecting...'; }
    if (!navigator.geolocation) {
      alert('Location not supported by your browser.');
      if (btn) { btn.disabled = false; btn.classList.remove('loading'); btn.title = 'Use my location'; }
      return;
    }
    navigator.geolocation.getCurrentPosition(
      async function (pos) {
        try {
          const place = await reverseGeocode(pos.coords.latitude, pos.coords.longitude);
          const allOpts = buildOriginOptions();
          let found = matchPlaceToAirport(place, allOpts);
          if (found) {
            setOrigin(found.value, found.label);
          } else {
            found = findNearestAirport(pos.coords.latitude, pos.coords.longitude, allOpts);
            if (found) {
              const ok = confirm('Nearest airport: ' + found.label + '. Use this?');
              if (ok) setOrigin(found.value, found.label);
            } else {
              alert('Could not find a matching airport for your location. Please select manually.');
            }
          }
        } catch (e) {
          alert('Could not detect location. Please select manually.');
        }
        if (btn) { btn.disabled = false; btn.classList.remove('loading'); btn.title = 'Use my location'; }
      },
      function () {
        alert('Location denied. Please select an airport manually.');
        if (btn) { btn.disabled = false; btn.classList.remove('loading'); btn.title = 'Use my location'; }
      }
    );
  }

  function handleSharedLink() {
    try {
      const params = new URLSearchParams(window.location.search);
      const from = (params.get('from') || '').toUpperCase();
      const to = (params.get('to') || '').toUpperCase();
      if (!from || !to) return;
      const cards = document.querySelectorAll('.deal-card');
      let card = null;
      for (let i = 0; i < cards.length; i++) {
        if (cards[i].dataset.origin === from && cards[i].dataset.destination === to) {
          card = cards[i];
          break;
        }
      }
      if (card) {
        card.scrollIntoView({ behavior: 'smooth', block: 'center' });
        card.classList.add('shared-highlight');
        setTimeout(function () { card.classList.remove('shared-highlight'); }, 3000);
      }
      if (history.replaceState) history.replaceState({}, '', window.location.pathname || '/');
    } catch (e) {}
  }

  function getDestinationEmoji(code) {
    const emojis = { 'MIA': '🏖️', 'LAX': '🌴', 'LAS': '🎰', 'JFK': '🗽', 'ORD': '🏙️', 'DEN': '⛰️', 'SEA': '☕', 'BOS': '🦞', 'SFO': '🌉', 'ATL': '✈️', 'PHX': '🌵', 'MCO': '🎢', 'HNL': '🌺', 'ANC': '🐻', 'PDX': '🌲', 'DFW': '🤠', 'FLL': '🏝️', 'TPA': '🌊', 'CUN': '🍹', 'LHR': '🇬🇧', 'CDG': '🗼' };
    return emojis[code] || '✈️';
  }

  function loadHomepageWidgets() {
    var grid = document.getElementById('cheap-destinations-grid');
    if (grid) {
      fetch((typeof API !== 'undefined' ? API : '') + '/api/cheap-destinations?max_price=100&limit=8')
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.destinations && data.destinations.length > 0) {
            grid.innerHTML = data.destinations.map(function (d) {
              var name = d.destination_name || d.destination || '';
              var price = Math.round(d.min_price || 0);
              var count = d.origin_count || 0;
              var link = '/deals?destination=' + encodeURIComponent(d.destination);
              var badge = price < 75 ? '<div class="destination-badge">Hot Deal</div>' : '';
              return '<a href="' + link + '" class="destination-card" title="Flights to ' + name + '">' +
                '<div class="destination-image">' + getDestinationEmoji(d.destination) + '</div>' +
                '<div class="destination-info">' +
                '<div class="destination-name">' + escapeHtml(name) + '</div>' +
                '<div class="destination-price"><span class="from">from</span> $' + price + '</div>' +
                '<div class="destination-meta">From ' + count + ' ' + (count === 1 ? 'city' : 'cities') + '</div>' +
                '</div>' + badge + '</a>';
            }).join('');
          } else {
            grid.innerHTML = '<div class="loading-dest">No destinations found under $100</div>';
          }
        })
        .catch(function () {
          if (grid) grid.innerHTML = '<div class="loading-dest">Unable to load destinations</div>';
        });
    }
    var dropsGrid = document.getElementById('price-drops-grid');
    if (dropsGrid) {
      fetch((typeof API !== 'undefined' ? API : '') + '/api/price-drops?limit=6')
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.drops && data.drops.length > 0) {
            dropsGrid.innerHTML = data.drops.map(function (d) {
              var orig = d.origin_name || d.origin;
              var dest = d.destination_name || d.destination;
              var link = '/flights/' + d.origin + '-to-' + d.destination;
              return '<a href="' + link + '" class="price-drop-card">' +
                '<div class="price-drop-route">' + escapeHtml(orig) + '<span class="arrow">→</span>' + escapeHtml(dest) + '</div>' +
                '<div class="price-drop-stats">' +
                '<div class="price-drop-current">$' + Math.round(d.current_price) + '</div>' +
                '<div class="price-drop-change">↓ ' + Math.round(d.drop_percent) + '% off</div>' +
                '</div>' +
                '<div class="price-drop-was">was $' + Math.round(d.previous_price || d.avg_price) + '</div>' +
                '</a>';
            }).join('');
          } else {
            dropsGrid.innerHTML = '<div class="loading-dest">No recent price drops</div>';
          }
        })
        .catch(function () {
          if (dropsGrid) dropsGrid.innerHTML = '<div class="loading-dest">Unable to load</div>';
        });
    }
    var routesList = document.getElementById('popular-routes-list');
    if (routesList) {
      fetch((typeof API !== 'undefined' ? API : '') + '/api/popular-routes?limit=10')
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.routes && data.routes.length > 0) {
            routesList.innerHTML = data.routes.map(function (r, i) {
              var orig = r.origin_name || r.origin;
              var dest = r.destination_name || r.destination;
              var link = '/flights/' + r.origin + '-to-' + r.destination;
              return '<a href="' + link + '" class="route-item">' +
                '<div class="route-info">' +
                '<div class="route-rank">' + (i + 1) + '</div>' +
                '<div class="route-cities">' + escapeHtml(orig) + ' → ' + escapeHtml(dest) + '</div>' +
                '</div>' +
                '<div class="route-price">$' + Math.round(r.min_price) + '</div>' +
                '</a>';
            }).join('');
          } else {
            routesList.innerHTML = '<div class="loading-dest">No routes available</div>';
          }
        })
        .catch(function () {
          if (routesList) routesList.innerHTML = '<div class="loading-dest">Unable to load</div>';
        });
    }
  }

  async function loadAirports() {
    try {
      const res = await fetch(`${API}/api/airports?with_data=true`);
      const data = await res.json();
      airports = Array.isArray(data.airports) && data.airports.length > 0 ? data.airports : FALLBACK_ORIGINS;
      const params = new URLSearchParams(window.location.search);
      const from = params.get('from');
      const to = params.get('to');
      if (from && to && airports.indexOf(from.toUpperCase()) !== -1) {
        setOrigin(from.toUpperCase(), getCityName(from.toUpperCase()) + ' (' + from.toUpperCase() + ')');
      } else {
        setOrigin('ALL', ALL_AIRPORTS_OPTION.label);
      }
      renderOriginListbox(originInput ? originInput.value : '', false);
    } catch (e) {
      airports = FALLBACK_ORIGINS;
      setOrigin('ALL', ALL_AIRPORTS_OPTION.label);
      renderOriginListbox(originInput ? originInput.value : '', false);
    }
  }

  function refreshFromControls() {
    const searchQ = searchInput ? searchInput.value.trim() : '';
    renderCards(allDeals, searchQ, currentMode);
  }

  if (originInput && originListbox) {
    originInput.addEventListener('focus', function () {
      originInput.select();
      renderOriginListbox(originInput.value, true);
    });
    originInput.addEventListener('input', function () { renderOriginListbox(originInput.value, true); });
    originInput.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        originListbox.classList.add('hidden');
        originInput.blur();
      }
    });
    originListbox.addEventListener('click', function (e) {
      const li = e.target.closest('li[data-value]');
      if (li) setOrigin(li.dataset.value, li.textContent);
    });
  }
  document.addEventListener('click', function (e) {
    if (originCombobox && !originCombobox.contains(e.target)) {
      if (originListbox) originListbox.classList.add('hidden');
    }
  });

  document.getElementById('btn-use-location')?.addEventListener('click', function (e) {
    e.preventDefault();
    useLocation();
  });

  const dateRangeEl = document.getElementById('date-range');
  const specificDateEl = document.getElementById('specific-date');
  const specificDateLabel = document.getElementById('specific-date-label');
  const dateRangeInputs = document.getElementById('date-range-inputs');
  const dateFromEl = document.getElementById('date-from');
  const dateToEl = document.getElementById('date-to');
  function syncDateRangeVisibility() {
    const today = getClientDate();
    const period = dateRangeEl ? dateRangeEl.value : 'week';
    const isDate = period === 'date';
    const isRange = period === 'range';
    if (specificDateLabel) specificDateLabel.classList.toggle('hidden', !isDate);
    if (specificDateEl) specificDateEl.classList.toggle('hidden', !isDate);
    if (dateRangeInputs) dateRangeInputs.classList.toggle('hidden', !isRange);
    if (isDate && specificDateEl && !specificDateEl.value) {
      specificDateEl.value = today;
      specificDateEl.min = today;
    }
    if (isRange && dateFromEl && dateToEl) {
      if (!dateFromEl.value) {
        const prefs = window.preferredDates;
        dateFromEl.value = (prefs && prefs.date_from) ? prefs.date_from : today;
        dateFromEl.min = today;
      }
      if (!dateToEl.value) {
        const prefs = window.preferredDates;
        dateToEl.value = (prefs && prefs.date_to) ? prefs.date_to : today;
        dateToEl.min = today;
      }
      if (dateFromEl.value) dateToEl.min = dateFromEl.value;
      if (dateFromEl.value && dateToEl.value && dateToEl.value < dateFromEl.value) {
        const t = dateFromEl.value;
        dateFromEl.value = dateToEl.value;
        dateToEl.value = t;
      }
    }
    fetchDeals(originSelect ? originSelect.value : 'ALL');
  }
  if (dateRangeEl) {
    dateRangeEl.addEventListener('change', syncDateRangeVisibility);
  }
  if (specificDateEl) {
    specificDateEl.addEventListener('change', function () {
      if (getPeriod() === 'date') fetchDeals(originSelect ? originSelect.value : 'ALL');
    });
  }
  function validateDateRange() {
    if (!dateFromEl || !dateToEl || !dateFromEl.value || !dateToEl.value) return true;
    if (dateToEl.value < dateFromEl.value) {
      const tmp = dateFromEl.value;
      dateFromEl.value = dateToEl.value;
      dateToEl.value = tmp;
      dateToEl.min = dateFromEl.value;
      return true;
    }
    return true;
  }
  if (dateFromEl) {
    dateFromEl.addEventListener('change', function () {
      if (dateToEl && dateFromEl.value) { dateToEl.min = dateFromEl.value; if (dateToEl.value && dateToEl.value < dateFromEl.value) dateToEl.value = dateFromEl.value; }
      if (getPeriod() === 'range') { validateDateRange(); fetchDeals(originSelect ? originSelect.value : 'ALL'); }
    });
  }
  if (dateToEl) {
    dateToEl.addEventListener('change', function () {
      if (getPeriod() === 'range') { validateDateRange(); fetchDeals(originSelect ? originSelect.value : 'ALL'); }
    });
  }
  const listViewContainer = document.getElementById('list-view-container');
  const calendarViewContainer = document.getElementById('calendar-view-container');
  document.getElementById('view-list')?.addEventListener('click', function () {
    if (listViewContainer) listViewContainer.classList.remove('hidden');
    if (calendarViewContainer) calendarViewContainer.classList.add('hidden');
    document.querySelectorAll('.view-btn').forEach(function (b) { b.classList.remove('active'); b.setAttribute('aria-pressed', 'false'); });
    const btn = document.getElementById('view-list');
    if (btn) { btn.classList.add('active'); btn.setAttribute('aria-pressed', 'true'); }
  });
  document.getElementById('view-calendar')?.addEventListener('click', function () {
    if (listViewContainer) listViewContainer.classList.add('hidden');
    if (calendarViewContainer) calendarViewContainer.classList.remove('hidden');
    document.querySelectorAll('.view-btn').forEach(function (b) { b.classList.remove('active'); b.setAttribute('aria-pressed', 'false'); });
    const btn = document.getElementById('view-calendar');
    if (btn) { btn.classList.add('active'); btn.setAttribute('aria-pressed', 'true'); }
    updateCalendarOriginDisplay();
  });
  let mainCalendarState = null;

  function loadMainCalendar(origin, destination, year, month) {
    const content = document.getElementById('main-calendar-content');
    if (!content) return;
    const firstDay = year + '-' + String(month).padStart(2, '0') + '-01';
    const lastDay = new Date(year, month, 0);
    const dateTo = lastDay.getFullYear() + '-' + String(lastDay.getMonth() + 1).padStart(2, '0') + '-' + String(lastDay.getDate()).padStart(2, '0');
    content.innerHTML = '<p class="calendar-loading">Loading…</p>';
    fetch(`${API}/api/price-calendar?origin=${encodeURIComponent(origin)}&destination=${encodeURIComponent(destination)}&date_from=${encodeURIComponent(firstDay)}&date_to=${encodeURIComponent(dateTo)}`)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        const dates = data.dates || [];
        mainCalendarState = { origin, destination, year, month };
        if (dates.length === 0) {
          content.innerHTML = '<p class="calendar-empty">No price data for this route in ' + new Date(year, month - 1).toLocaleString('en-US', { month: 'long', year: 'numeric' }) + '.</p>';
          return;
        }
        calendarModalData = { origin, destination, dates, dateFrom: '', dateTo: '' };
        renderMainCalendarView(dates, origin, destination, year, month, content);
      })
      .catch(function () { content.innerHTML = '<p class="calendar-error">Failed to load.</p>'; });
  }

  function renderMainCalendarView(dates, origin, destination, year, month, content) {
    const prices = dates.map(function (d) { return d.price; });
    const minPrice = Math.min.apply(null, prices);
    const maxPrice = Math.max.apply(null, prices);
    const avgPrice = prices.length ? Math.round(prices.reduce(function (a, b) { return a + b; }, 0) / prices.length) : 0;
    const monthName = new Date(year, month - 1).toLocaleString('en-US', { month: 'long', year: 'numeric' });
    const prevMonth = month === 1 ? { y: year - 1, m: 12 } : { y: year, m: month - 1 };
    const nextMonth = month === 12 ? { y: year + 1, m: 1 } : { y: year, m: month + 1 };
    const prevLabel = new Date(prevMonth.y, prevMonth.m - 1).toLocaleString('en-US', { month: 'short' });
    const nextLabel = new Date(nextMonth.y, nextMonth.m - 1).toLocaleString('en-US', { month: 'short' });
    content.innerHTML = '';
    const wrapper = document.createElement('div');
    wrapper.className = 'calendar-view-wrapper';
    wrapper.innerHTML = '<div class="calendar-month-nav"><button type="button" class="btn-cal-prev" aria-label="Previous month">← ' + prevLabel + '</button><h3>' + monthName + '</h3><button type="button" class="btn-cal-next" aria-label="Next month">' + nextLabel + ' →</button></div>' +
      '<div class="calendar-price-summary"><span>Cheapest: <strong>$' + Math.round(minPrice) + '</strong></span><span>Average: <strong>$' + avgPrice + '</strong></span><span>Highest: <strong>$' + Math.round(maxPrice) + '</strong></span></div>' +
      '<div class="calendar-legend"><span class="legend-item"><span class="color-box cheapest"></span> Best Deal</span><span class="legend-item"><span class="color-box good-deal"></span> Good</span><span class="legend-item"><span class="color-box fair"></span> Fair</span><span class="legend-item"><span class="color-box expensive"></span> High</span></div>';
    const grid = document.createElement('div');
    grid.className = 'calendar-grid';
    wrapper.appendChild(grid);
    content.appendChild(wrapper);
    renderCalendarGrid(dates, origin, destination, grid, null);
    wrapper.querySelector('.btn-cal-prev').addEventListener('click', function () {
      loadMainCalendar(origin, destination, prevMonth.y, prevMonth.m);
    });
    wrapper.querySelector('.btn-cal-next').addEventListener('click', function () {
      loadMainCalendar(origin, destination, nextMonth.y, nextMonth.m);
    });
  }

  let calendarDestinationsCache = null;
  let calendarDestinationsOrigin = null;

  function fetchCalendarDestinations(origin) {
    if (calendarDestinationsOrigin === origin && calendarDestinationsCache) return Promise.resolve(calendarDestinationsCache);
    return fetch(`${API}/api/calendar/destinations?origin=${encodeURIComponent(origin)}`)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        const dests = (data.destinations || []).map(function (d) {
          return { code: d.code, minPrice: d.minPrice, label: getCityName(d.code) + ' (' + d.code + ')' };
        });
        calendarDestinationsCache = dests;
        calendarDestinationsOrigin = origin;
        return dests;
      })
      .catch(function () { return []; });
  }

  function showDestResults(dests, query, wrapper) {
    const q = (query || '').toLowerCase().trim();
    let filtered = dests;
    if (q.length >= 2) {
      filtered = dests.filter(function (d) {
        return d.label.toLowerCase().includes(q) || d.code.toLowerCase().includes(q);
      });
    }
    const limit = 12;
    const top = filtered.slice(0, limit);
    const hasSection = q.length < 2 && top.length > 0;
    let html = hasSection ? '<div class="dest-section-label">Popular</div>' : '';
    html += top.map(function (d) {
      return '<div class="dest-result-item" role="option" data-dest="' + escapeAttr(d.code) + '" tabindex="-1">' +
        '<span class="dest-name">' + escapeHtml(d.label) + '</span>' +
        '<span class="dest-price">from $' + Math.round(d.minPrice) + '</span></div>';
    }).join('');
    if (top.length === 0) html += '<div class="dest-result-item dest-no-results">No destinations found</div>';
    wrapper.innerHTML = html;
    wrapper.classList.remove('hidden');
    wrapper.querySelectorAll('.dest-result-item[data-dest]').forEach(function (el) {
      el.addEventListener('click', function () { selectCalendarDest(el.dataset.dest); });
    });
  }

  function selectCalendarDest(destCode) {
    const input = document.getElementById('calendar-dest-input');
    const results = document.getElementById('calendar-dest-results');
    const origin = (originSelect && originSelect.value) || currentOrigin;
    if (!origin || origin === 'ALL') return;
    if (input) input.value = getCityName(destCode) + ' (' + destCode + ')';
    if (results) results.classList.add('hidden');
    const now = new Date();
    loadMainCalendar(origin, destCode, now.getFullYear(), now.getMonth() + 1);
  }

  const calendarDestInput = document.getElementById('calendar-dest-input');
  const calendarDestResults = document.getElementById('calendar-dest-results');
  if (calendarDestInput && calendarDestResults) {
    let debounceTimer = null;
    calendarDestInput.addEventListener('focus', function () {
      const origin = (originSelect && originSelect.value) || currentOrigin;
      if (!origin || origin === 'ALL') return;
      fetchCalendarDestinations(origin).then(function (dests) {
        showDestResults(dests, calendarDestInput.value, calendarDestResults);
      });
    });
    calendarDestInput.addEventListener('input', function () {
      const origin = (originSelect && originSelect.value) || currentOrigin;
      if (!origin || origin === 'ALL') { calendarDestResults.classList.add('hidden'); return; }
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(function () {
        fetchCalendarDestinations(origin).then(function (dests) {
          showDestResults(dests, calendarDestInput.value, calendarDestResults);
        });
      }, 150);
    });
    calendarDestInput.addEventListener('blur', function () {
      setTimeout(function () { if (calendarDestResults) calendarDestResults.classList.add('hidden'); }, 200);
    });
    calendarDestInput.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') {
        const first = calendarDestResults.querySelector('.dest-result-item[data-dest]');
        if (first) { selectCalendarDest(first.dataset.dest); e.preventDefault(); }
      }
    });
  }

  document.getElementById('btn-save-dates')?.addEventListener('click', async function () {
    const fromVal = dateFromEl && dateFromEl.value;
    const toVal = dateToEl && dateToEl.value;
    if (!fromVal || !toVal || !currentUser) {
      if (!currentUser && Clerk) {
        if (confirm('Sign in to save your preferred dates. Sign in now?')) Clerk.openSignIn();
      } else {
        alert('Select a date range first.');
      }
      return;
    }
    try {
      const token = Clerk && Clerk.session ? await Clerk.session.getToken() : '';
      const res = await fetch(`${API}/api/date-preferences`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': token ? 'Bearer ' + token : '' },
        body: JSON.stringify({ date_from: fromVal, date_to: toVal })
      });
      if (res.ok) {
        window.preferredDates = { date_from: fromVal, date_to: toVal };
        alert('Preferred dates saved!');
      } else {
        alert('Failed to save.');
      }
    } catch (e) { alert('Failed to save.'); }
  });

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

  function showBookingLoader() {
    const loader = document.getElementById('booking-loader');
    const progressBar = document.getElementById('progress-bar');
    const title = document.getElementById('loader-title');
    const subtitle = document.getElementById('loader-subtitle');
    if (!loader || !progressBar) return;
    loader.style.display = 'flex';
    progressBar.style.width = '0%';
    if (title) title.textContent = 'Finding the best price...';
    if (subtitle) subtitle.textContent = 'This usually takes 5-10 seconds';
    let progress = 0;
    const iv = setInterval(function () {
      progress += Math.random() * 12;
      if (progress > 90) progress = 90;
      progressBar.style.width = progress + '%';
    }, 400);
    loader.dataset.progressInterval = String(iv);
    setTimeout(function () {
      if (title) title.textContent = 'Securing best rate...';
    }, 3000);
    setTimeout(function () {
      if (title) title.textContent = 'Almost there...';
      if (subtitle) subtitle.textContent = 'Redirecting you to booking page';
    }, 7000);
  }

  function hideBookingLoader() {
    const loader = document.getElementById('booking-loader');
    const progressBar = document.getElementById('progress-bar');
    if (loader && loader.dataset.progressInterval) {
      clearInterval(parseInt(loader.dataset.progressInterval, 10));
      loader.dataset.progressInterval = '';
    }
    if (progressBar) progressBar.style.width = '100%';
    if (loader) {
      setTimeout(function () {
        loader.style.display = 'none';
        if (progressBar) progressBar.style.width = '0%';
      }, 300);
    }
  }

  document.addEventListener('click', function (e) {
    const link = e.target.closest('a[href*="book-redirect"]');
    if (!link || !link.href || link.href.indexOf('book-redirect') === -1) return;
    if (e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey) return;
    e.preventDefault();
    e.stopPropagation();
    const url = link.href;
    const fetchUrl = url + (url.indexOf('?') >= 0 ? '&' : '?') + 'format=json';
    showBookingLoader();
    fetch(fetchUrl)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        hideBookingLoader();
        if (data && data.url) window.location.href = data.url;
        else window.location.href = url;
      })
      .catch(function () {
        hideBookingLoader();
        window.location.href = url;
      });
  }, true);

  if (dealsGrid) {
    dealsGrid.addEventListener('click', function (e) {
      const returnBtn = e.target.closest('.btn-return');
      if (returnBtn) {
        e.preventDefault();
        showReturnOptions(returnBtn.dataset.deal ? JSON.parse(returnBtn.dataset.deal) : null);
        return;
      }
      const alertBtn = e.target.closest('.btn-alert');
      if (alertBtn) {
        e.preventDefault();
        e.stopPropagation();
        try {
          const data = JSON.parse(alertBtn.dataset.alert || '{}');
          window.openAlertModal && openAlertModal(data);
        } catch (err) {}
        return;
      }
      const shareBtn = e.target.closest('.btn-share');
      if (shareBtn) {
        e.preventDefault();
        try {
          const data = JSON.parse(shareBtn.dataset.share || '{}');
          window.openShareModal && openShareModal(data);
        } catch (err) {}
        return;
      }
      const saveBtn = e.target.closest('.btn-save-flight');
      if (saveBtn && !saveBtn.disabled) {
        e.preventDefault();
        e.stopPropagation();
        const origin = saveBtn.dataset.saveOrigin;
        const dest = saveBtn.dataset.saveDest;
        if (origin && dest) saveFlightFromCard(origin, dest, saveBtn);
        return;
      }
      const calBtn = e.target.closest('.btn-calendar');
      if (calBtn) {
        e.preventDefault();
        const origin = calBtn.dataset.calOrigin;
        const dest = calBtn.dataset.calDest;
        if (origin && dest) openCalendarModal(origin, dest);
      }
    });
  }

  let calendarModalData = { origin: '', destination: '', dates: [], dateFrom: '', dateTo: '' };
  let calendarPriceChart = null;

  function renderCalendarTiles(dates, origin, destination, grid, selectedEl) {
    if (!dates.length) return;
    const prices = dates.map(function (d) { return d.price; });
    const minPrice = Math.min.apply(null, prices);
    const maxPrice = Math.max.apply(null, prices);
    const range = maxPrice - minPrice || 1;
    const dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    let html = '<div class="calendar-tiles">';
    dates.forEach(function (d) {
      const pct = range > 0 ? (d.price - minPrice) / range : 0;
      let priceClass = 'fair';
      if (d.price <= minPrice + range * 0.2) priceClass = 'cheapest';
      else if (pct < 0.5) priceClass = 'good-deal';
      else if (pct >= 0.8) priceClass = 'expensive';
      const dateObj = new Date(d.date + 'T12:00:00');
      const weekday = dayNames[dateObj.getDay()];
      const shortDate = dateObj.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
      const bookUrl = `${API}/api/book-redirect?origin=${encodeURIComponent(origin)}&destination=${encodeURIComponent(destination)}&date=${encodeURIComponent(d.date)}`;
      const flightJson = escapeAttr(JSON.stringify({ date: d.date, price: d.price, airline: d.airline, duration: d.duration, num_stops: d.num_stops || 0 }));
      html += '<div class="calendar-tile has-price ' + priceClass + '" data-date="' + escapeAttr(d.date) + '" data-price="' + d.price + '" data-book="' + escapeAttr(bookUrl) + '" data-flight="' + flightJson + '" title="Click to book">';
      html += '<span class="cal-day">' + weekday + ', ' + shortDate + '</span><span class="cal-price">$' + Math.round(d.price) + '</span></div>';
    });
    html += '</div>';
    grid.innerHTML = html;
    bindCalendarCellClicks(grid, selectedEl, 'calendar-tile');
  }

  function renderCalendarGrid(dates, origin, destination, grid, selectedEl) {
    if (!dates.length) return;
    const byDate = {};
    dates.forEach(function (d) { byDate[d.date] = d; });
    const prices = dates.map(function (d) { return d.price; });
    const minPrice = Math.min.apply(null, prices);
    const maxPrice = Math.max.apply(null, prices);
    const range = maxPrice - minPrice || 1;
    const first = new Date(dates[0].date);
    const last = new Date(dates[dates.length - 1].date);
    const start = new Date(first.getFullYear(), first.getMonth(), 1);
    const end = new Date(last.getFullYear(), last.getMonth() + 1, 0);
    const dayHeaders = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    let html = '<div class="calendar-month-grid"><div class="cal-grid-headers">' + dayHeaders.map(function (h) { return '<span>' + h + '</span>'; }).join('') + '</div><div class="cal-grid-cells">';
    for (let i = 0; i < start.getDay(); i++) html += '<div class="cal-grid-cell empty"></div>';
    const cur = new Date(start);
    while (cur <= end) {
      const dateStr = cur.getFullYear() + '-' + String(cur.getMonth() + 1).padStart(2, '0') + '-' + String(cur.getDate()).padStart(2, '0');
      const info = byDate[dateStr];
      if (info) {
        const pct = range > 0 ? (info.price - minPrice) / range : 0;
        let priceClass = 'fair';
        if (info.price <= minPrice + range * 0.2) priceClass = 'cheapest';
        else if (pct < 0.5) priceClass = 'good-deal';
        else if (pct >= 0.8) priceClass = 'expensive';
        const bookUrl = `${API}/api/book-redirect?origin=${encodeURIComponent(origin)}&destination=${encodeURIComponent(destination)}&date=${encodeURIComponent(dateStr)}`;
        const flightJson = escapeAttr(JSON.stringify({ date: dateStr, price: info.price, airline: info.airline, duration: info.duration, num_stops: info.num_stops || 0 }));
        html += '<div class="cal-grid-cell has-price ' + priceClass + '" data-date="' + escapeAttr(dateStr) + '" data-price="' + info.price + '" data-book="' + escapeAttr(bookUrl) + '" data-flight="' + flightJson + '" title="Click to book"><span class="cal-num">' + cur.getDate() + '</span><span class="cal-val">$' + Math.round(info.price) + '</span></div>';
      } else {
        html += '<div class="cal-grid-cell no-data"><span class="cal-num">' + cur.getDate() + '</span><span class="cal-val">—</span></div>';
      }
      cur.setDate(cur.getDate() + 1);
    }
    html += '</div></div>';
    grid.innerHTML = html;
    bindCalendarCellClicks(grid, selectedEl, 'cal-grid-cell.has-price');
  }

  window.openCalendarFlightModal = function (origin, destination, flightData) {
    const modal = document.getElementById('calendar-flight-modal');
    const routeEl = document.getElementById('cal-flight-route');
    const dateEl = document.getElementById('cal-flight-date');
    const priceEl = document.getElementById('cal-flight-price');
    const airlineEl = document.getElementById('cal-flight-airline');
    const durationEl = document.getElementById('cal-flight-duration');
    const stopsEl = document.getElementById('cal-flight-stops');
    const bookBtn = document.getElementById('cal-flight-book-btn');
    const googleBtn = document.getElementById('cal-flight-google-btn');
    if (!modal || !flightData) return;
    const dateStr = flightData.date || '';
    const price = flightData.price || 0;
    routeEl.textContent = (getCityName ? getCityName(origin) : origin) + ' → ' + (getCityName ? getCityName(destination) : destination);
    dateEl.textContent = dateStr ? new Date(dateStr + 'T12:00:00').toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' }) : '—';
    priceEl.textContent = '$' + Math.round(price);
    airlineEl.textContent = flightData.airline || '—';
    durationEl.textContent = flightData.duration || '—';
    const ns = flightData.num_stops;
    stopsEl.textContent = ns === 0 ? 'Nonstop' : ns === 1 ? '1 stop' : (ns || '—') + ' stops';
    const bookUrl = `${API}/api/book-redirect?origin=${encodeURIComponent(origin)}&destination=${encodeURIComponent(destination)}&date=${encodeURIComponent(dateStr)}`;
    const googleUrl = `https://www.google.com/travel/flights?q=${encodeURIComponent('One way flights from ' + origin + ' to ' + destination + ' on ' + dateStr)}`;
    if (bookBtn) { bookBtn.href = bookUrl; bookBtn.textContent = 'Book Now →'; }
    if (googleBtn) googleBtn.href = googleUrl;
    modal.classList.remove('hidden');
    modal.setAttribute('aria-hidden', 'false');
  };

  window.closeCalendarFlightModal = function () {
    const modal = document.getElementById('calendar-flight-modal');
    if (modal) {
      modal.classList.add('hidden');
      modal.setAttribute('aria-hidden', 'true');
    }
  };

  function bindCalendarCellClicks(container, selectedEl, selector) {
    container.querySelectorAll(selector).forEach(function (cell) {
      cell.addEventListener('click', function () {
        const book = cell.dataset.book;
        const flightRaw = cell.dataset.flight;
        if (!book || !flightRaw) return;
        let flightData;
        try { flightData = JSON.parse(flightRaw); } catch (e) { flightData = { date: cell.dataset.date, price: parseFloat(cell.dataset.price) || 0 }; }
        const origin = calendarModalData.origin;
        const destination = calendarModalData.destination;
        if (origin && destination && window.openCalendarFlightModal) {
          window.openCalendarFlightModal(origin, destination, flightData);
        } else {
          window.open(book, '_blank');
        }
      });
    });
  }

  function renderCalendarGraph(dates, graphContainer) {
    if (!dates.length) return;
    if (!window.Chart) {
      if (graphContainer) graphContainer.innerHTML = '<p class="calendar-error">Graph requires Chart.js. Please refresh the page.</p>';
      return;
    }
    if (calendarPriceChart) { calendarPriceChart.destroy(); calendarPriceChart = null; }
    const ctx = document.getElementById('calendar-price-chart');
    if (!ctx) return;
    const sorted = dates.slice().sort(function (a, b) { return new Date(a.date) - new Date(b.date); });
    calendarPriceChart = new Chart(ctx.getContext('2d'), {
      type: 'line',
      data: {
        labels: sorted.map(function (d) {
          const x = new Date(d.date + 'T12:00:00');
          return x.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
        }),
        datasets: [{
          label: 'Price',
          data: sorted.map(function (d) { return d.price; }),
          borderColor: '#1a73e8',
          backgroundColor: 'rgba(26, 115, 232, 0.1)',
          tension: 0.3,
          fill: true
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          y: { beginAtZero: false }
        }
      }
    });
  }

  async function openCalendarModal(origin, destination) {
    const modal = document.getElementById('calendar-modal');
    const routeLabel = document.getElementById('calendar-route-label');
    const grid = document.getElementById('calendar-grid');
    const graphContainer = document.getElementById('calendar-graph-container');
    const selectedEl = document.getElementById('calendar-selected');
    const modalDateFrom = document.getElementById('modal-date-from');
    const modalDateTo = document.getElementById('modal-date-to');
    if (!modal || !routeLabel || !grid) return;
    routeLabel.textContent = origin + ' → ' + destination;
    calendarModalData = { origin, destination, dates: [], dateFrom: '', dateTo: '' };
    grid.innerHTML = '<p class="calendar-loading">Loading…</p>';
    selectedEl.classList.add('hidden');
    graphContainer.classList.add('hidden');
    modal.classList.remove('hidden');
    const today = getClientDate();
    const toDefault = new Date();
    toDefault.setDate(toDefault.getDate() + 30);
    const toStr = toDefault.getFullYear() + '-' + String(toDefault.getMonth() + 1).padStart(2, '0') + '-' + String(toDefault.getDate()).padStart(2, '0');
    if (modalDateFrom) { modalDateFrom.value = today; modalDateFrom.min = today; }
    if (modalDateTo) { modalDateTo.value = toStr; modalDateTo.min = today; }
    try {
      let url = `${API}/api/price-calendar?origin=${encodeURIComponent(origin)}&destination=${encodeURIComponent(destination)}&days=30`;
      const res = await fetch(url);
      const data = await res.json();
      let dates = data.dates || [];
      if (dates.length === 0) {
        grid.innerHTML = '<p class="calendar-empty">No price data for this route in the next 30 days.</p>';
        return;
      }
      calendarModalData.dates = dates;
      const activeTab = (modal.querySelector('.cal-tab.active') || {}).dataset?.tab || 'tiles';
      if (activeTab === 'tiles') renderCalendarTiles(dates, origin, destination, grid, selectedEl);
      else if (activeTab === 'grid') renderCalendarGrid(dates, origin, destination, grid, selectedEl);
      else if (activeTab === 'graph') {
        grid.classList.add('hidden');
        graphContainer.classList.remove('hidden');
        graphContainer.style.height = '280px';
        renderCalendarGraph(dates, graphContainer);
      }
    } catch (err) {
      grid.innerHTML = '<p class="calendar-error">Failed to load prices. Please try again.</p>';
    }
  }

  document.querySelectorAll('.calendar-modal-tabs .cal-tab').forEach(function (tab) {
    tab.addEventListener('click', function () {
      document.querySelectorAll('.cal-tab').forEach(function (t) { t.classList.remove('active'); });
      tab.classList.add('active');
      const grid = document.getElementById('calendar-grid');
      const graphContainer = document.getElementById('calendar-graph-container');
      const d = calendarModalData;
      if (!d.dates.length) return;
      grid.classList.remove('hidden');
      graphContainer.classList.add('hidden');
      if (tab.dataset.tab === 'tiles') {
        renderCalendarTiles(d.dates, d.origin, d.destination, grid, document.getElementById('calendar-selected'));
      } else if (tab.dataset.tab === 'grid') {
        renderCalendarGrid(d.dates, d.origin, d.destination, grid, document.getElementById('calendar-selected'));
      } else if (tab.dataset.tab === 'graph') {
        grid.classList.add('hidden');
        graphContainer.classList.remove('hidden');
        graphContainer.style.height = '280px';
        renderCalendarGraph(d.dates, graphContainer);
      }
    });
  });
  document.getElementById('modal-apply-range')?.addEventListener('click', function () {
    const fromEl = document.getElementById('modal-date-from');
    const toEl = document.getElementById('modal-date-to');
    if (!fromEl || !toEl || !fromEl.value || !toEl.value) return;
    const d = calendarModalData;
    if (!d.origin || !d.destination) return;
    document.getElementById('calendar-grid').innerHTML = '<p class="calendar-loading">Loading…</p>';
    fetch(`${API}/api/price-calendar?origin=${encodeURIComponent(d.origin)}&destination=${encodeURIComponent(d.destination)}&date_from=${encodeURIComponent(fromEl.value)}&date_to=${encodeURIComponent(toEl.value)}`)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        const dates = data.dates || [];
        calendarModalData.dates = dates;
        const tab = document.querySelector('.cal-tab.active');
        const grid = document.getElementById('calendar-grid');
        const graphContainer = document.getElementById('calendar-graph-container');
        if (dates.length === 0) {
          grid.innerHTML = '<p class="calendar-empty">No price data for this date range.</p>';
        } else if (tab && tab.dataset.tab === 'graph') {
          grid.classList.add('hidden');
          graphContainer.classList.remove('hidden');
          renderCalendarGraph(dates, graphContainer);
        } else if (tab && tab.dataset.tab === 'grid') {
          renderCalendarGrid(dates, d.origin, d.destination, grid, document.getElementById('calendar-selected'));
        } else {
          renderCalendarTiles(dates, d.origin, d.destination, grid, document.getElementById('calendar-selected'));
        }
      })
      .catch(function () { document.getElementById('calendar-grid').innerHTML = '<p class="calendar-error">Failed to load.</p>'; });
  });

  window.closeCalendarModal = function () {
    if (calendarPriceChart) { calendarPriceChart.destroy(); calendarPriceChart = null; }
    document.getElementById('calendar-modal')?.classList.add('hidden');
  };

  const calendarModal = document.getElementById('calendar-modal');
  if (calendarModal) {
    calendarModal.querySelector('.modal-backdrop')?.addEventListener('click', closeCalendarModal);
    calendarModal.querySelector('.modal-close')?.addEventListener('click', closeCalendarModal);
    calendarModal.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') closeCalendarModal();
    });
  }

  window.openAlertModal = async function (data) {
    if (!data || !data.origin || !data.destination) return;
    if (!currentUser) {
      if (Clerk) {
        try { sessionStorage.setItem('flightgrab_pending_alert', JSON.stringify(data)); } catch (e) {}
        if (confirm('Sign in to set price alerts. Sign in now?')) Clerk.openSignIn();
      } else {
        alert('Sign in is required for price alerts. Set up Clerk to enable this feature.');
      }
      return;
    }
    document.getElementById('alert-route').textContent = data.origin + ' → ' + data.destination;
    document.getElementById('alert-current-price').textContent = Math.round(data.price || 0);
    document.getElementById('alert-target-price').value = Math.round((data.price || 0) * 0.8);
    document.getElementById('alert-origin').value = data.origin;
    document.getElementById('alert-destination').value = data.destination;
    var limitUsage = document.getElementById('alert-limit-usage');
    var upgradeCta = document.getElementById('alert-upgrade-cta');
    var form = document.getElementById('alert-form');
    limitUsage.classList.add('hidden');
    upgradeCta.classList.add('hidden');
    if (form) form.style.display = '';
    try {
      var token = Clerk && Clerk.session ? await Clerk.session.getToken() : '';
      var statusRes = await fetch((typeof API !== 'undefined' ? API : '') + '/api/subscription/status', {
        headers: { 'Authorization': token ? 'Bearer ' + token : '' }
      });
      if (statusRes.ok) {
        var status = await statusRes.json();
        document.getElementById('alert-count').textContent = status.alert_count;
        document.getElementById('alert-limit').textContent = status.alert_limit;
        limitUsage.classList.remove('hidden');
        if (!status.can_add_more) {
          upgradeCta.classList.remove('hidden');
          if (form) form.style.display = 'none';
        }
      }
    } catch (e) {}
    document.getElementById('alert-modal').classList.remove('hidden');
  };

  window.closeAlertModal = function () {
    document.getElementById('alert-modal').classList.add('hidden');
  };

  document.getElementById('alert-form')?.addEventListener('submit', async function (e) {
    e.preventDefault();
    if (!currentUser) {
      alert('Please sign in to set alerts');
      return;
    }
    const origin = document.getElementById('alert-origin').value;
    const destination = document.getElementById('alert-destination').value;
    const targetPrice = parseFloat(document.getElementById('alert-target-price').value);
    if (!origin || !destination || isNaN(targetPrice)) return;
    try {
      let token = '';
      if (Clerk && Clerk.session) token = await Clerk.session.getToken({ skipCache: true });
      const res = await fetch(`${API}/api/alerts/subscribe`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': token ? 'Bearer ' + token : ''
        },
        body: JSON.stringify({
          user_id: currentUser.id,
          email: currentUser.email,
          origin, destination, target_price: targetPrice
        })
      });
      const data = await res.json().catch(function () { return {}; });
      if (res.ok) {
        alert('Price alert set! We\'ll email you when the price drops.');
        closeAlertModal();
      } else if (res.status === 402) {
        if (confirm('Upgrade to Premium for unlimited alerts. Go to pricing?')) {
          window.location.href = '/pricing';
        }
      } else {
        alert(data.error || data.detail || 'Failed to set alert. Please try again.');
      }
    } catch (err) {
      console.error(err);
      alert('Failed to set alert. Please try again.');
    }
  });

  document.getElementById('alert-modal')?.querySelector('.modal-backdrop')?.addEventListener('click', closeAlertModal);
  document.getElementById('alert-modal')?.querySelector('.modal-close')?.addEventListener('click', closeAlertModal);

  let currentShareData = null;

  function generateShareUrl(origin, destination, date) {
    const base = (typeof window !== 'undefined' && window.location && window.location.origin) || 'https://flightgrab.cc';
    try {
      const u = new URL('/', base);
      u.searchParams.set('from', origin);
      u.searchParams.set('to', destination);
      u.searchParams.set('date', date || '');
      return u.toString();
    } catch (e) {
      return base + '/?from=' + encodeURIComponent(origin) + '&to=' + encodeURIComponent(destination) + '&date=' + encodeURIComponent(date || '');
    }
  }

  window.openShareModal = function (data) {
    if (!data || !data.origin || !data.destination) return;
    currentShareData = data;
    const routeEl = document.getElementById('share-route');
    const priceEl = document.getElementById('share-price');
    const dateEl = document.getElementById('share-date');
    const urlInput = document.getElementById('share-url-input');
    const copySuccess = document.getElementById('copy-success');
    if (routeEl) routeEl.textContent = data.origin + ' → ' + data.destination;
    if (priceEl) priceEl.textContent = '$' + Math.round(data.price || 0);
    if (dateEl) dateEl.textContent = 'Departs ' + (formatDate(data.departure_date) || '—');
    const shareUrl = generateShareUrl(data.origin, data.destination, data.departure_date || '');
    if (urlInput) urlInput.value = shareUrl;
    if (copySuccess) copySuccess.classList.add('hidden');
    const fbBtn = document.querySelector('.share-facebook');
    const twBtn = document.querySelector('.share-twitter');
    const waBtn = document.querySelector('.share-whatsapp');
    const emBtn = document.querySelector('.share-email');
    const text = '✈️ Found a deal! ' + data.origin + ' → ' + data.destination + ' for only $' + Math.round(data.price || 0);
    if (fbBtn) fbBtn.href = 'https://www.facebook.com/sharer/sharer.php?u=' + encodeURIComponent(shareUrl) + '&quote=' + encodeURIComponent(text);
    if (twBtn) twBtn.href = 'https://twitter.com/intent/tweet?text=' + encodeURIComponent('✈️ Found a deal on FlightGrab! ' + data.origin + ' → ' + data.destination + ' for only $' + Math.round(data.price || 0) + ' 🎉') + '&url=' + encodeURIComponent(shareUrl);
    if (waBtn) waBtn.href = 'https://wa.me/?text=' + encodeURIComponent(text + '\n' + shareUrl);
    if (emBtn) {
      emBtn.href = 'mailto:?subject=' + encodeURIComponent('✈️ Flight Deal: ' + data.origin + ' → ' + data.destination + ' for $' + Math.round(data.price || 0)) + '&body=' + encodeURIComponent('Hey!\n\nI found this flight deal on FlightGrab:\n\n' + data.origin + ' → ' + data.destination + '\nPrice: $' + Math.round(data.price || 0) + ' (one-way)\nDate: ' + (formatDate(data.departure_date) || '') + '\n\nCheck it out: ' + shareUrl + '\n\nHappy travels! ✈️');
    }
    const modal = document.getElementById('share-modal');
    if (modal) { modal.classList.remove('hidden'); modal.setAttribute('aria-hidden', 'false'); }
  };

  window.closeShareModal = function () {
    const modal = document.getElementById('share-modal');
    if (modal) { modal.classList.add('hidden'); modal.setAttribute('aria-hidden', 'true'); }
    document.getElementById('copy-success')?.classList.add('hidden');
  };

  document.getElementById('btn-copy-share')?.addEventListener('click', function () {
    const input = document.getElementById('share-url-input');
    if (!input) return;
    input.select();
    input.setSelectionRange(0, 99999);
    navigator.clipboard.writeText(input.value).then(function () {
      const success = document.getElementById('copy-success');
      const btn = document.getElementById('btn-copy-share');
      if (success) { success.classList.remove('hidden'); success.textContent = '✓ Link copied!'; }
      if (btn) { var t = btn.textContent; btn.textContent = 'Copied!'; setTimeout(function () { btn.textContent = t; }, 2000); }
      setTimeout(function () { document.getElementById('copy-success')?.classList.add('hidden'); }, 2000);
    }).catch(function () { alert('Press Ctrl+C (or Cmd+C) to copy the link'); });
  });

  document.getElementById('share-modal')?.querySelector('.modal-backdrop')?.addEventListener('click', closeShareModal);
  document.getElementById('share-modal')?.querySelector('.modal-close')?.addEventListener('click', closeShareModal);
  document.getElementById('share-modal')?.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeShareModal(); });

  const calendarFlightModal = document.getElementById('calendar-flight-modal');
  if (calendarFlightModal) {
    calendarFlightModal.querySelector('.modal-backdrop')?.addEventListener('click', closeCalendarFlightModal);
    calendarFlightModal.querySelector('.modal-close')?.addEventListener('click', closeCalendarFlightModal);
    calendarFlightModal.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeCalendarFlightModal(); });
  }

  [document.getElementById('my-alerts-modal'), document.getElementById('saved-flights-modal')].forEach(function (m) {
    if (!m) return;
    m.querySelector('.modal-backdrop')?.addEventListener('click', function () {
      if (m.id === 'my-alerts-modal') closeMyAlertsModal(); else closeSavedFlightsModal();
    });
    m.querySelector('.modal-close')?.addEventListener('click', function () {
      if (m.id === 'my-alerts-modal') closeMyAlertsModal(); else closeSavedFlightsModal();
    });
    m.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        if (m.id === 'my-alerts-modal') closeMyAlertsModal(); else closeSavedFlightsModal();
      }
    });
  });

  document.getElementById('btn-sign-in')?.addEventListener('click', function () {
    if (Clerk) Clerk.openSignIn();
  });
  document.getElementById('btn-sign-up')?.addEventListener('click', function () {
    if (Clerk) Clerk.openSignUp();
  });

  const userMenuTrigger = document.getElementById('user-menu-trigger');
  const userDropdown = document.getElementById('user-dropdown');
  if (userMenuTrigger && userDropdown) {
    userMenuTrigger.addEventListener('click', function (e) {
      e.stopPropagation();
      userDropdown.classList.toggle('hidden');
    });
    document.addEventListener('click', function () {
      userDropdown.classList.add('hidden');
    });
  }
  document.getElementById('link-sign-out')?.addEventListener('click', function (e) {
    e.preventDefault();
    if (Clerk) Clerk.signOut();
  });
  document.getElementById('link-my-alerts')?.addEventListener('click', function (e) {
    e.preventDefault();
    if (currentUser) openMyAlertsModal(); else if (Clerk) Clerk.openSignIn();
  });

  document.getElementById('link-saved-flights')?.addEventListener('click', function (e) {
    e.preventDefault();
    if (currentUser) openSavedFlightsModal(); else if (Clerk) Clerk.openSignIn();
  });

  function checkHashAndOpenModals() {
    const hash = (window.location.hash || '').toLowerCase();
    if (hash === '#alerts' && currentUser) openMyAlertsModal();
    if (hash === '#saved' && currentUser) openSavedFlightsModal();
  }

  window.addEventListener('hashchange', checkHashAndOpenModals);

  window.openMyAlertsModal = function () {
    const modal = document.getElementById('my-alerts-modal');
    const listEl = document.getElementById('my-alerts-list');
    const emptyEl = document.getElementById('my-alerts-empty');
    if (!modal || !listEl) return;
    listEl.innerHTML = '<p class="alerts-loading">Loading...</p>';
    emptyEl.classList.add('hidden');
    modal.classList.remove('hidden');
    modal.setAttribute('aria-hidden', 'false');
    fetchMyAlerts();
  };

  window.closeMyAlertsModal = function () {
    const modal = document.getElementById('my-alerts-modal');
    if (modal) {
      modal.classList.add('hidden');
      modal.setAttribute('aria-hidden', 'true');
    }
    if (window.location.hash === '#alerts') history.replaceState(null, '', window.location.pathname);
  };

  async function fetchMyAlerts() {
    const listEl = document.getElementById('my-alerts-list');
    const emptyEl = document.getElementById('my-alerts-empty');
    const upgradeCta = document.getElementById('my-alerts-upgrade-cta');
    if (!listEl) return;
    try {
      let token = '';
      if (Clerk && Clerk.session) token = await Clerk.session.getToken();
      const res = await fetch(`${API}/api/alerts`, {
        headers: { 'Authorization': token ? 'Bearer ' + token : '' }
      });
      if (res.status === 401) {
        listEl.innerHTML = '<p class="alerts-loading">Please sign in to view your alerts.</p>';
        emptyEl.classList.add('hidden');
        if (upgradeCta) upgradeCta.classList.add('hidden');
        return;
      }
      const data = await res.json().catch(function () { return {}; });
      const alerts = data.alerts || [];
      if (upgradeCta) {
        var statusRes = await fetch(`${API}/api/subscription/status`, { headers: { 'Authorization': token ? 'Bearer ' + token : '' } });
        if (statusRes.ok) {
          var sub = await statusRes.json();
          if (!sub.can_add_more && !sub.is_premium) upgradeCta.classList.remove('hidden');
          else upgradeCta.classList.add('hidden');
        } else {
          upgradeCta.classList.add('hidden');
        }
      }
      if (alerts.length === 0) {
        listEl.innerHTML = '';
        emptyEl.classList.remove('hidden');
        return;
      }
      emptyEl.classList.add('hidden');
      listEl.innerHTML = alerts.map(function (a) {
        const created = a.created_at ? new Date(a.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '—';
        return `<div class="alert-item" data-id="${a.id}">
          <div class="alert-item-info">
            <div class="alert-item-route">${escapeHtml(a.origin)} → ${escapeHtml(a.destination)}</div>
            <div class="alert-item-meta">Target: $${Math.round(a.target_price)} · Created ${created}</div>
          </div>
          <button type="button" class="btn-delete" data-delete-alert="${a.id}" aria-label="Delete alert">Delete</button>
        </div>`;
      }).join('');
      listEl.querySelectorAll('.btn-delete').forEach(function (btn) {
        btn.addEventListener('click', function () {
          const id = parseInt(btn.dataset.deleteAlert, 10);
          if (id) deleteAlert(id, btn);
        });
      });
    } catch (e) {
      listEl.innerHTML = '<p class="alerts-loading">Failed to load alerts. Please try again.</p>';
    }
  }

  async function deleteAlert(id, btnEl) {
    if (!confirm('Remove this price alert?')) return;
    try {
      let token = '';
      if (Clerk && Clerk.session) token = await Clerk.session.getToken();
      const res = await fetch(`${API}/api/alerts/${id}`, {
        method: 'DELETE',
        headers: { 'Authorization': token ? 'Bearer ' + token : '' }
      });
      if (res.ok) {
        const item = btnEl.closest('.alert-item');
        if (item) item.remove();
        const listEl = document.getElementById('my-alerts-list');
        const emptyEl = document.getElementById('my-alerts-empty');
        if (listEl && listEl.children.length === 0 && emptyEl) emptyEl.classList.remove('hidden');
      } else {
        alert('Failed to delete alert.');
      }
    } catch (e) {
      alert('Failed to delete alert.');
    }
  }

  window.openSavedFlightsModal = function () {
    const modal = document.getElementById('saved-flights-modal');
    const listEl = document.getElementById('saved-flights-list');
    const emptyEl = document.getElementById('saved-flights-empty');
    if (!modal || !listEl) return;
    listEl.innerHTML = '<p class="alerts-loading">Loading...</p>';
    emptyEl.classList.add('hidden');
    modal.classList.remove('hidden');
    modal.setAttribute('aria-hidden', 'false');
    fetchSavedFlights();
  };

  window.closeSavedFlightsModal = function () {
    const modal = document.getElementById('saved-flights-modal');
    if (modal) {
      modal.classList.add('hidden');
      modal.setAttribute('aria-hidden', 'true');
    }
    if (window.location.hash === '#saved') history.replaceState(null, '', window.location.pathname);
  };

  async function fetchSavedFlights() {
    const listEl = document.getElementById('saved-flights-list');
    const emptyEl = document.getElementById('saved-flights-empty');
    if (!listEl) return;
    try {
      let token = '';
      if (Clerk && Clerk.session) token = await Clerk.session.getToken();
      const res = await fetch(`${API}/api/saved-flights`, {
        headers: { 'Authorization': token ? 'Bearer ' + token : '' }
      });
      if (res.status === 401) {
        listEl.innerHTML = '<p class="alerts-loading">Please sign in to view saved flights.</p>';
        emptyEl.classList.add('hidden');
        return;
      }
      const data = await res.json().catch(function () { return {}; });
      const flights = data.saved_flights || [];
      if (flights.length === 0) {
        listEl.innerHTML = '';
        emptyEl.classList.remove('hidden');
        return;
      }
      emptyEl.classList.add('hidden');
      listEl.innerHTML = flights.map(function (f) {
        const created = f.created_at ? new Date(f.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '';
        const searchUrl = `https://www.google.com/travel/flights?q=${encodeURIComponent('One way flights from ' + f.origin + ' to ' + f.destination)}`;
        const note = f.notes ? escapeHtml(f.notes) : '';
        return `<div class="saved-flight-item" data-id="${f.id}">
          <div class="saved-flight-info">
            <div class="saved-flight-route">${escapeHtml(f.origin)} → ${escapeHtml(f.destination)}</div>
            <div class="saved-flight-meta">${note || created || ''}</div>
          </div>
          <div class="saved-flight-actions">
            <a href="${escapeAttr(searchUrl)}" target="_blank" rel="noopener" class="btn-secondary" style="padding:8px 12px;font-size:0.85rem;">Search</a>
            <button type="button" class="btn-delete" data-delete-saved="${f.id}" aria-label="Remove">Remove</button>
          </div>
        </div>`;
      }).join('');
      listEl.querySelectorAll('.btn-delete').forEach(function (btn) {
        btn.addEventListener('click', function () {
          const id = parseInt(btn.dataset.deleteSaved, 10);
          if (id) deleteSavedFlight(id, btn);
        });
      });
    } catch (e) {
      listEl.innerHTML = '<p class="alerts-loading">Failed to load saved flights. Please try again.</p>';
    }
  }

  async function deleteSavedFlight(id, btnEl) {
    try {
      let token = '';
      if (Clerk && Clerk.session) token = await Clerk.session.getToken();
      const res = await fetch(`${API}/api/saved-flights/${id}`, {
        method: 'DELETE',
        headers: { 'Authorization': token ? 'Bearer ' + token : '' }
      });
      if (res.ok) {
        const item = btnEl.closest('.saved-flight-item');
        if (item) item.remove();
        const listEl = document.getElementById('saved-flights-list');
        const emptyEl = document.getElementById('saved-flights-empty');
        if (listEl && listEl.children.length === 0 && emptyEl) emptyEl.classList.remove('hidden');
      } else {
        alert('Failed to remove saved flight.');
      }
    } catch (e) {
      alert('Failed to remove saved flight.');
    }
  }

  async function saveFlightFromCard(origin, destination, btnEl) {
    if (!currentUser) {
      try { sessionStorage.setItem('flightgrab_pending_save', JSON.stringify({ origin, destination })); } catch (e) {}
      if (Clerk) Clerk.openSignIn();
      return;
    }
    try {
      let token = '';
      if (Clerk && Clerk.session) {
        token = await Clerk.session.getToken({ skipCache: true });
      }
      if (!token) {
        try { sessionStorage.setItem('flightgrab_pending_save', JSON.stringify({ origin, destination })); } catch (e) {}
        if (Clerk) Clerk.openSignIn();
        else alert('Please sign in to save flights.');
        return;
      }
      const res = await fetch(`${API}/api/saved-flights`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer ' + token
        },
        body: JSON.stringify({ origin, destination })
      });
      const data = await res.json().catch(function () { return {}; });
      if (res.ok) {
        if (btnEl) {
          btnEl.textContent = 'Saved ✓';
          btnEl.classList.add('saved');
          btnEl.disabled = true;
        }
      } else if (res.status === 401) {
        if (Clerk) Clerk.openSignIn();
        else alert('Session expired. Please sign in again.');
      } else {
        alert(data.error || data.detail || 'Failed to save.');
      }
    } catch (e) {
      console.error('Save flight error:', e);
      alert('Failed to save flight. Please try again.');
    }
  }

  loadAirports();
  loadHomepageWidgets();
  Promise.resolve(initializeAuth()).then(function () {
    checkHashAndOpenModals();
    tryPendingAlert();
    tryPendingSave();
  });
  }

  async function bootstrap() {
    try {
      const res = await fetch(`${API}/api/config`);
      const config = await res.json();
      await loadClerkAndRun(config.clerkPublishableKey || '');
    } catch (e) {
      runApp();
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bootstrap);
  } else {
    bootstrap();
  }
})();
