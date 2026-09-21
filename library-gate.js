(() => {
  const ACCESS_PAGE = '/library-access.html';
  const cfg = window.KR_SUPABASE;

  function goToAccess(reason = '') {
    const url = new URL(ACCESS_PAGE, window.location.origin);
    url.searchParams.set('next', '/library.html');
    if (reason) url.searchParams.set('reason', reason);
    window.location.replace(url.toString());
  }

  async function runGate() {
    try {
      if (!cfg?.url || !cfg?.publishableKey || !window.supabase) {
        return goToAccess('config');
      }

      const client = window.supabase.createClient(cfg.url, cfg.publishableKey, {
        auth: {
          persistSession: true,
          autoRefreshToken: true,
          detectSessionInUrl: true
        }
      });

      // getUser() validates the current access token with Supabase Auth.
      const { data: userData, error: userError } = await client.auth.getUser();
      const user = userData?.user;

      if (userError || !user) {
        return goToAccess('login');
      }

      // Email confirmation must be complete.
      if (!user.email_confirmed_at) {
        await client.auth.signOut();
        return goToAccess('email');
      }

      // Access is granted only when the registration profile exists.
      const { data: profile, error: profileError } = await client
        .from('library_profiles')
        .select('user_id')
        .eq('user_id', user.id)
        .maybeSingle();

      if (profileError || !profile) {
        return goToAccess('profile');
      }

      document.documentElement.classList.remove('kr-auth-pending');

      const logout = document.createElement('button');
      logout.type = 'button';
      logout.id = 'kr-library-logout';
      logout.textContent = (localStorage.getItem('kr-lang') === 'it') ? 'Esci' : 'Logout';
      logout.setAttribute('aria-label', logout.textContent);
      Object.assign(logout.style, {
        position: 'fixed',
        right: '16px',
        bottom: '16px',
        zIndex: '99999',
        border: '1px solid rgba(20,55,75,.18)',
        borderRadius: '999px',
        padding: '9px 14px',
        background: '#ffffff',
        color: '#123247',
        font: '600 13px system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif',
        boxShadow: '0 5px 18px rgba(20,55,75,.12)',
        cursor: 'pointer'
      });
      logout.addEventListener('click', async () => {
        logout.disabled = true;
        await client.auth.signOut();
        window.location.replace(ACCESS_PAGE);
      });
      document.body.appendChild(logout);

      client.auth.onAuthStateChange((event) => {
        if (event === 'SIGNED_OUT') goToAccess('logout');
      });
    } catch (err) {
      console.error('Scientific Library auth gate:', err);
      goToAccess('error');
    }
  }

  runGate();
})();
