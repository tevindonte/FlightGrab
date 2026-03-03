/**
 * Standalone auth modal for deals, pricing, and other non-homepage pages.
 * Avoids navigation to homepage (and any external redirects like Clerk).
 */
(function () {
  const AUTH_TOKEN_KEY = 'flightgrab_auth_token';

  function openAuthModal(mode) {
    mode = mode || 'signin';
    var title = document.getElementById('auth-modal-title');
    var subtitle = document.getElementById('auth-modal-subtitle');
    var signupFields = document.getElementById('auth-signup-fields');
    var submitBtn = document.getElementById('auth-submit');
    var toggleEl = document.getElementById('auth-toggle');
    var errorEl = document.getElementById('auth-error');
    var form = document.getElementById('auth-form');
    if (!title) return;
    window.authModalMode = mode;
    if (mode === 'signup') {
      title.textContent = 'Sign Up';
      subtitle.textContent = 'Create an account to save flights and set price alerts. We\'ll send a verification link to your email.';
      if (signupFields) signupFields.classList.remove('hidden');
      if (submitBtn) submitBtn.textContent = 'Sign Up';
      if (toggleEl) toggleEl.innerHTML = 'Already have an account? <a href="#" id="auth-toggle-link">Sign in</a>';
    } else {
      title.textContent = 'Sign In';
      subtitle.textContent = 'Sign in to save flights and set price alerts.';
      if (signupFields) signupFields.classList.add('hidden');
      if (submitBtn) submitBtn.textContent = 'Sign In';
      if (toggleEl) toggleEl.innerHTML = 'Don\'t have an account? <a href="#" id="auth-toggle-link">Sign up</a>';
    }
    if (errorEl) { errorEl.classList.add('hidden'); errorEl.textContent = ''; }
    if (form) form.reset();
    document.getElementById('auth-modal').classList.remove('hidden');
    document.getElementById('auth-modal').setAttribute('aria-hidden', 'false');
    var newLink = document.getElementById('auth-toggle-link');
    if (newLink) {
      newLink.onclick = function (e) { e.preventDefault(); openAuthModal(mode === 'signup' ? 'signin' : 'signup'); };
    }
  }

  window.closeAuthModal = function () {
    var m = document.getElementById('auth-modal');
    if (m) { m.classList.add('hidden'); m.setAttribute('aria-hidden', 'true'); }
  };

  function setupAuth() {
    var btnSignIn = document.getElementById('btn-sign-in');
    var btnSignUp = document.getElementById('btn-sign-up');
    if (btnSignIn) btnSignIn.addEventListener('click', function () { openAuthModal('signin'); });
    if (btnSignUp) btnSignUp.addEventListener('click', function () { openAuthModal('signup'); });
    [].forEach.call(document.querySelectorAll('#link-signin, a[href="/#signin"], a[href="#signin"]'), function (el) {
      el.href = '#'; el.addEventListener('click', function (e) { e.preventDefault(); openAuthModal('signin'); });
    });
    [].forEach.call(document.querySelectorAll('#link-signup, a[href="/#signup"], a[href="#signup"]'), function (el) {
      el.href = '#'; el.addEventListener('click', function (e) { e.preventDefault(); openAuthModal('signup'); });
    });

    document.getElementById('auth-modal')?.querySelector('.modal-backdrop')?.addEventListener('click', window.closeAuthModal);
    document.getElementById('auth-modal')?.querySelector('.modal-close')?.addEventListener('click', window.closeAuthModal);

    document.getElementById('auth-form')?.addEventListener('submit', async function (e) {
      e.preventDefault();
      var email = (document.getElementById('auth-email')?.value || '').trim().toLowerCase();
      var password = (document.getElementById('auth-password')?.value || '').trim();
      var firstName = (document.getElementById('auth-first-name')?.value || '').trim();
      var errorEl = document.getElementById('auth-error');
      var submitBtn = document.getElementById('auth-submit');
      if (!email || !password) {
        if (errorEl) { errorEl.textContent = 'Email and password required'; errorEl.classList.remove('hidden'); }
        return;
      }
      if (password.length < 6) {
        if (errorEl) { errorEl.textContent = 'Password must be at least 6 characters'; errorEl.classList.remove('hidden'); }
        return;
      }
      if (errorEl) errorEl.classList.add('hidden');
      if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = 'Please wait...'; }
      try {
        var endpoint = window.authModalMode === 'signup' ? '/api/auth/signup' : '/api/auth/signin';
        var body = { email: email, password: password };
        if (window.authModalMode === 'signup') body.first_name = firstName;
        var res = await fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body)
        });
        var data = await res.json().catch(function () { return {}; });
        if (res.ok) {
          localStorage.setItem(AUTH_TOKEN_KEY, data.token);
          window.closeAuthModal();
          window.location.reload();
        } else {
          if (errorEl) { errorEl.textContent = data.detail || 'Something went wrong'; errorEl.classList.remove('hidden'); }
        }
      } catch (err) {
        if (errorEl) { errorEl.textContent = 'Network error. Please try again.'; errorEl.classList.remove('hidden'); }
      }
      if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = window.authModalMode === 'signup' ? 'Sign Up' : 'Sign In'; }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setupAuth);
  } else {
    setupAuth();
  }
})();
