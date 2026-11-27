(() => {
  function showName(root, name) {
    const value = root.closest('.account-content')?.querySelector('.account-profile .guest-facts dd');
    if (value) value.textContent = name;
    document.dispatchEvent(new CustomEvent('restaurant-profile-updated', {detail:{name}}));
  }
  async function load(root) {
    if (root.dataset.loading) return;
    root.dataset.loading = 'true';
    const feedback = root.querySelector('[data-settings-feedback]');
    try {
      const [{profile}, {requests}] = await Promise.all([
        restaurantRequest('/auth/settings'), restaurantRequest('/auth/link-requests')
      ]);
      root.querySelector('[name=name]').value = profile.name;
      showName(root, profile.name);
      root.querySelector('[data-settings-summary]').textContent = profile.email
        ? 'Verified recovery email: ' + profile.email : 'No verified recovery email. Bind one before you need to recover your password.';
      const list = root.querySelector('[data-account-link-requests]');
      list.replaceChildren();
      if (requests.length) {
        const heading = document.createElement('h3'); heading.textContent = 'Front desk link requests'; list.append(heading);
      }
      for (const request of requests) {
        const article = document.createElement('article');
        const summary = document.createElement('p');
        const arrival = request.arrival_at ? new Date(request.arrival_at) : null;
        const time = arrival && Number.isFinite(arrival.getTime()) ? arrival.toLocaleTimeString('en-GB',
          {timeZone:'Asia/Shanghai',hour:'2-digit',minute:'2-digit'}) : '';
        summary.textContent = 'Link this ' + request.target_type + ' to your account? ' +
          [request.booking_date, time, request.party_size + ' guests'].filter(Boolean).join(' · ');
        article.append(summary);
        for (const action of ['confirm','decline']) {
          const button = document.createElement('button'); button.type = 'button'; button.className = 'secondary';
          button.textContent = action === 'confirm' ? 'Confirm this is mine' : 'Decline';
          button.dataset.linkAction = action; button.dataset.linkId = request.link_id;
          if (request.version != null) button.dataset.version = request.version;
          article.append(button);
        }
        list.append(article);
      }
    } catch (error) { feedback.textContent = error.message; }
    finally { delete root.dataset.loading; }
  }
  document.addEventListener('submit', async event => {
    const form = event.target.closest('[data-profile-settings],[data-email-settings]');
    if (!form) return;
    event.preventDefault();
    const root = form.closest('[data-account-settings]');
    const button = form.querySelector('[type=submit]');
    if (button.disabled) return;
    button.disabled = true;
    const feedback = root.querySelector('[data-settings-feedback]');
    try {
      const nameForm = form.matches('[data-profile-settings]');
      const result = await restaurantRequest(nameForm ? '/auth/profile' : '/auth/recovery-email', Object.fromEntries(new FormData(form)));
      feedback.textContent = result.message || 'Name saved. It applies to future reservations; existing contact records are preserved.';
      if (nameForm) showName(root, result.name);
      if (!nameForm) form.elements.current_password.value = '';
    } catch (error) { feedback.textContent = error.message; }
    finally { button.disabled = false; feedback.focus(); }
  });
  document.addEventListener('click', async event => {
    const button = event.target.closest('[data-link-action]');
    if (!button || button.disabled) return;
    const root = button.closest('[data-account-settings]'); button.disabled = true;
    const feedback = root.querySelector('[data-settings-feedback]');
    try {
      await restaurantRequest('/auth/link-requests/' + button.dataset.linkId + '/' + button.dataset.linkAction,
        button.dataset.version ? {expected_version:button.dataset.version} : {});
      feedback.textContent = button.dataset.linkAction === 'confirm' ? 'Account link confirmed. Refresh your visit to see its records.' : 'Link request declined.';
      await load(root);
    } catch (error) { feedback.textContent = error.message; button.disabled = false; }
    feedback.focus();
  });
  function mount() {
    for (const root of document.querySelectorAll('[data-account-settings]:not([data-mounted])')) {
      root.dataset.mounted = 'true'; load(root);
    }
  }
  new MutationObserver(mount).observe(document.querySelector('#app') || document.body, {childList:true,subtree:true});
  mount();
})();
