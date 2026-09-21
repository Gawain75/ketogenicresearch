(() => {
  const cfg = window.KR_SUPABASE;
  if (!cfg?.url || !cfg?.publishableKey || cfg.url.includes('YOUR_PROJECT')) {
    document.getElementById('status').className = 'status error';
    document.getElementById('status').textContent = 'Supabase configuration missing.';
    return;
  }

  const client = window.supabase.createClient(cfg.url, cfg.publishableKey);
  const $ = id => document.getElementById(id);
  let lang = localStorage.getItem('kr-lang') || 'en';

  function setLang(next) {
    lang = next;
    localStorage.setItem('kr-lang', lang);
    document.documentElement.lang = lang;
    document.querySelectorAll('[data-en]').forEach(el => {
      const value = lang === 'it' ? el.dataset.it : el.dataset.en;
      if (value) el.textContent = value;
    });
    document.querySelectorAll('[data-lang]').forEach(b => b.classList.toggle('active', b.dataset.lang === lang));
  }
  document.querySelectorAll('[data-lang]').forEach(b => b.addEventListener('click', () => setLang(b.dataset.lang)));
  setLang(lang);

  function status(msg, error=false) {
    const el = $('status');
    el.textContent = msg;
    el.className = 'status' + (error ? ' error' : '');
  }
  function clearStatus() { $('status').className = 'status hidden'; }

  function show(mode) {
    clearStatus();
    const login = mode === 'login';
    $('loginForm').classList.toggle('hidden', !login);
    $('registerForm').classList.toggle('hidden', login);
    $('loginTab').classList.toggle('active', login);
    $('registerTab').classList.toggle('active', !login);
  }
  $('loginTab').onclick = () => show('login');
  $('registerTab').onclick = () => show('register');

  const GEO = 'https://comuni-ita.nicolorebaioli.dev/v5';

  async function getJson(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error('Geographic service unavailable');
    return r.json();
  }
  function rows(payload) {
    if (Array.isArray(payload)) return payload;
    for (const key of ['data','results','items','regioni','province','comuni']) {
      if (Array.isArray(payload?.[key])) return payload[key];
    }
    return [];
  }
  function valueOf(obj, keys) {
    if (typeof obj === 'string') return obj;
    for (const k of keys) if (obj?.[k]) return obj[k];
    return '';
  }
  function fill(select, values, placeholder='—') {
    select.innerHTML = `<option value="">${placeholder}</option>`;
    [...new Set(values.filter(Boolean))].sort((a,b)=>a.localeCompare(b,'it')).forEach(v => {
      const o=document.createElement('option'); o.value=v; o.textContent=v; select.appendChild(o);
    });
  }

  async function loadRegions() {
    try {
      const data = rows(await getJson(`${GEO}/regioni`));
      fill($('region'), data.map(x => valueOf(x,['nome','name','regione'])));
    } catch (e) {
      status(lang === 'it' ? 'Servizio geografico momentaneamente non disponibile.' : 'Geographic service temporarily unavailable.', true);
    }
  }
  async function loadProvinces(region) {
    $('province').disabled = true; $('city').disabled = true;
    fill($('province'), []); fill($('city'), []);
    if (!region) return;
    const data = rows(await getJson(`${GEO}/province/${encodeURIComponent(region)}`));
    fill($('province'), data.map(x => valueOf(x,['nome','name','provincia'])));
    $('province').disabled = false;
  }
  async function loadCities(province) {
    $('city').disabled = true; fill($('city'), []);
    if (!province) return;
    const data = rows(await getJson(`${GEO}/comuni/provincia/${encodeURIComponent(province)}`));
    fill($('city'), data.map(x => valueOf(x,['nome','name','comune'])));
    $('city').disabled = false;
  }

  $('region').addEventListener('change', e => loadProvinces(e.target.value).catch(err => status(err.message,true)));
  $('province').addEventListener('change', e => loadCities(e.target.value).catch(err => status(err.message,true)));

  document.querySelectorAll('input[name="hcp"]').forEach(r => r.addEventListener('change', () => {
    const yes = document.querySelector('input[name="hcp"]:checked')?.value === 'yes';
    $('professionWrap').classList.toggle('hidden', !yes);
    if (!yes) { $('profession').value=''; $('professionOtherWrap').classList.add('hidden'); $('professionOther').value=''; }
  }));
  $('profession').addEventListener('change', e => $('professionOtherWrap').classList.toggle('hidden', e.target.value !== 'altro'));

  $('country').addEventListener('change', e => {
    const italy = e.target.value === 'Italy';
    $('italyFields').classList.toggle('hidden', !italy);
    $('foreignFields').classList.toggle('hidden', italy);
  });

  function setSessionCookies(session) {
    const secure = location.protocol === 'https:' ? '; Secure' : '';
    const maxAge = 60 * 60 * 24 * 30;
    document.cookie = `kr_access_token=${encodeURIComponent(session.access_token)}; Path=/; SameSite=Lax${secure}; Max-Age=${maxAge}`;
    document.cookie = `kr_refresh_token=${encodeURIComponent(session.refresh_token)}; Path=/; SameSite=Lax${secure}; Max-Age=${maxAge}`;
  }

  $('loginForm').addEventListener('submit', async e => {
    e.preventDefault(); clearStatus();
    const { data, error } = await client.auth.signInWithPassword({
      email: $('loginEmail').value.trim(),
      password: $('loginPassword').value
    });
    if (error) return status(error.message, true);
    setSessionCookies(data.session);
    location.href = 'library.html';
  });

  $('registerForm').addEventListener('submit', async e => {
    e.preventDefault(); clearStatus();

    const italy = $('country').value === 'Italy';
    const hcpChecked = document.querySelector('input[name="hcp"]:checked');
    const isHcp = italy ? (hcpChecked?.value === 'yes') : null;

    if (italy && !hcpChecked) return status(lang==='it' ? 'Indica se sei un professionista sanitario.' : 'Please indicate whether you are a healthcare professional.', true);

    const profile = italy ? {
      country: 'Italy',
      first_name: $('firstName').value.trim(),
      last_name: $('lastName').value.trim(),
      is_healthcare_professional: isHcp,
      profession: isHcp ? $('profession').value : null,
      profession_other: isHcp && $('profession').value === 'altro' ? $('professionOther').value.trim() : null,
      region: $('region').value,
      province: $('province').value,
      city: $('city').value,
      phone: $('phone').value.trim(),
    } : {
      country: $('foreignCountry').value.trim(),
      first_name: null,
      last_name: null,
      is_healthcare_professional: null,
      profession: null,
      profession_other: null,
      region: null,
      province: null,
      city: $('foreignCity').value.trim(),
      phone: null,
    };

    if (italy) {
      const required = ['first_name','last_name','region','province','city','phone'];
      if (required.some(k => !profile[k])) return status(lang==='it' ? 'Completa tutti i campi obbligatori.' : 'Complete all required fields.', true);
      if (isHcp && !profile.profession) return status(lang==='it' ? 'Seleziona la professione.' : 'Select your profession.', true);
      if (profile.profession === 'altro' && !profile.profession_other) return status(lang==='it' ? 'Specifica la professione.' : 'Specify your profession.', true);
    } else {
      if (!profile.country || !profile.city) return status(lang==='it' ? 'Inserisci Stato e città.' : 'Enter country/state and city.', true);
    }

    const email = $('registerEmail').value.trim();
    const password = $('registerPassword').value;
    const { data, error } = await client.auth.signUp({
      email, password,
      options: {
        emailRedirectTo: `${cfg.siteUrl}/library-access.html?confirmed=1`,
        data: { registration_source: 'scientific_library' }
      }
    });
    if (error) return status(error.message, true);

    if (data.session) {
      const { error: pErr } = await client.from('library_profiles').upsert({
        user_id: data.user.id,
        email,
        ...profile,
        privacy_version: '2026-09',
        privacy_accepted_at: new Date().toISOString()
      });
      if (pErr) return status(pErr.message, true);
      setSessionCookies(data.session);
      location.href = 'library.html';
    } else {
      // Save pending profile locally; after email confirmation the page will finalize it.
      localStorage.setItem('kr_pending_profile', JSON.stringify({ email, profile }));
      status(lang === 'it'
        ? 'Registrazione ricevuta. Controlla la tua email e conferma l’indirizzo per accedere alla Libreria.'
        : 'Registration received. Check your email and confirm your address to access the Library.');
    }
  });

  async function finalizePendingProfile() {
    const { data } = await client.auth.getSession();
    if (!data.session) return;
    setSessionCookies(data.session);

    const raw = localStorage.getItem('kr_pending_profile');
    if (raw) {
      try {
        const pending = JSON.parse(raw);
        await client.from('library_profiles').upsert({
          user_id: data.session.user.id,
          email: pending.email || data.session.user.email,
          ...pending.profile,
          privacy_version: '2026-09',
          privacy_accepted_at: new Date().toISOString()
        });
        localStorage.removeItem('kr_pending_profile');
      } catch {}
    }
    if (new URLSearchParams(location.search).get('confirmed') === '1') location.href = 'library.html';
  }

  client.auth.onAuthStateChange((_event, session) => { if (session) setSessionCookies(session); });
  loadRegions();
  finalizePendingProfile();
})();
