(() => {
  const search = document.getElementById('registration-search');
  const results = document.getElementById('registration-results');
  const status = document.getElementById('registration-status');
  const add = document.getElementById('add-business');
  const registered = document.getElementById('registered-business');
  const form = document.getElementById('business-registration-form');
  const error = document.getElementById('registration-error');
  let sequence = 0;
  let timer;
  let saving = false;

  function showRegistered(business) {
    form.hidden = true;
    add.hidden = true;
    results.hidden = true;
    registered.hidden = false;
    document.getElementById('registered-business-name').textContent =
      [business.name, business.phone, business.area].filter(Boolean).join(' · ');
    status.textContent = business.active
      ? 'This business is already registered.'
      : 'This business is inactive. Contact Command Center to update it.';
  }

  function showMatches(matches) {
    results.replaceChildren();
    results.hidden = matches.length === 0;
    for (const business of matches) {
      const item = document.createElement('li');
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = [business.name, business.phone, business.area,
        business.active ? '' : 'Inactive'].filter(Boolean).join(' · ');
      button.addEventListener('click', () => showRegistered(business));
      item.append(button);
      results.append(item);
    }
  }

  async function refresh(query, current) {
    try {
      const response = await fetch('/business-search?q=' + encodeURIComponent(query));
      if (!response.ok) throw new Error('Search unavailable');
      const data = await response.json();
      if (current !== sequence) return;
      results.replaceChildren();
      results.hidden = data.matches.length === 0;
      add.hidden = data.matches.length !== 0;
      status.textContent = data.matches.length
        ? 'Select your business from the matching results.'
        : 'No matching business found. Register it below.';
      showMatches(data.matches);
    } catch {
      if (current !== sequence) return;
      add.hidden = true;
      status.textContent = 'Could not search businesses. Type again to retry.';
    }
  }

  search.addEventListener('input', () => {
    clearTimeout(timer);
    const current = ++sequence;
    const query = search.value.trim();
    results.hidden = true;
    add.hidden = true;
    registered.hidden = true;
    form.hidden = true;
    error.hidden = true;
    status.textContent = query ? 'Searching…' : '';
    if (query) timer = setTimeout(() => refresh(query, current), 180);
  });

  add.addEventListener('click', () => {
    const query = search.value.trim();
    form.reset();
    const phoneQuery = /^[+\d\s()-]+$/.test(query);
    form.elements.business_name.value = phoneQuery ? '' : query;
    form.elements.phone.value = phoneQuery ? query : '';
    form.hidden = false;
    add.hidden = true;
    status.textContent = 'Enter the business details and save.';
    form.scrollIntoView({behavior: 'smooth', block: 'start'});
    (phoneQuery ? form.elements.business_name : form.elements.phone).focus();
  });

  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (saving || !form.reportValidity()) return;
    saving = true;
    const button = form.querySelector('button[type=submit]');
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 20000);
    button.disabled = true;
    button.textContent = 'Saving…';
    search.disabled = true;
    error.hidden = true;
    try {
      const response = await fetch(form.action, {
        method: 'POST', body: new FormData(form), signal: controller.signal,
        headers: {Accept: 'application/json'},
      });
      if (response.redirected && response.ok) {
        location.assign(response.url);
        return;
      }
      let detail = 'Could not save the business. Please try again.';
      if ((response.headers.get('content-type') || '').includes('application/json')) {
        const data = await response.json();
        if (response.ok && data.redirect === '/workspace') {
          location.assign(data.redirect);
          return;
        }
        detail = typeof data.detail === 'string' ? data.detail : detail;
        if (response.status === 409 && data.matches?.length) {
          form.hidden = true;
          add.hidden = true;
          status.textContent = data.detail;
          showMatches(data.matches);
          return;
        }
      } else if (response.status === 409) {
        detail = 'Punch In before registering a business, then try again.';
      } else if (response.status === 403) {
        detail = 'Reload this page and sign in again if needed.';
      }
      error.textContent = detail;
      error.hidden = false;
    } catch {
      error.textContent = 'Connection interrupted. Search for the business before retrying to check whether it was saved.';
      error.hidden = false;
    } finally {
      clearTimeout(timeout);
      saving = false;
      button.disabled = false;
      button.textContent = 'Save Business';
      search.disabled = false;
    }
  });
})();
