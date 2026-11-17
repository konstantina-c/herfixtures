/*
 * HerFixtures cookie consent (shared by every page).
 *
 * Google Analytics 4 (gtag.js) loads ONLY after the visitor clicks
 * "Accept analytics". Never add a direct gtag.js <script> tag to a page.
 *
 * Each page keeps an inline stub in <head>:
 *   window.dataLayer = window.dataLayer || [];
 *   function gtag(){dataLayer.push(arguments);}
 * so gtag('event', ...) calls never throw. Anything queued before consent
 * is discarded when consent is given, so it is never sent.
 *
 * Footer link: any element with [data-cookie-settings] reopens the banner.
 * It is styled by each page's own footer CSS (same as the @Konstantina__C link).
 */
(function () {
  'use strict';

  var GA_ID = 'G-TSQNRYCCSL';
  var STORAGE_KEY = 'hf_consent';
  var MAX_AGE_MS = 365 * 24 * 60 * 60 * 1000; // ask again after 12 months
  // Privacy policy page (next session). Set to '/privacy/' once it exists.
  var PRIVACY_URL = null;

  var gaLoaded = false;
  var banner = null;
  var returnFocusTo = null;

  // ---- stored choice ---------------------------------------------------
  function readChoice() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return null;
      var c = JSON.parse(raw);
      if (!c || (c.v !== 'granted' && c.v !== 'denied')) return null;
      if (typeof c.t !== 'number' || Date.now() - c.t > MAX_AGE_MS) return null;
      return c.v;
    } catch (e) { return null; }
  }

  function saveChoice(v) {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify({ v: v, t: Date.now() })); } catch (e) {}
  }

  // ---- Google Analytics ----------------------------------------------------
  function enableAnalytics() {
    window['ga-disable-' + GA_ID] = false;
    window.dataLayer = window.dataLayer || [];
    if (typeof window.gtag !== 'function') {
      window.gtag = function () { window.dataLayer.push(arguments); };
    }
    if (!gaLoaded) {
      // Drop everything queued before consent so it is never sent.
      window.dataLayer.length = 0;
      window.gtag('js', new Date());
      window.gtag('config', GA_ID);
      var s = document.createElement('script');
      s.async = true;
      s.src = 'https://www.googletagmanager.com/gtag/js?id=' + GA_ID;
      document.head.appendChild(s);
      gaLoaded = true;
    } else {
      window.gtag('config', GA_ID);
    }
  }

  function disableAnalytics() {
    // Stops gtag.js from sending anything more on this page.
    window['ga-disable-' + GA_ID] = true;
    deleteGaCookies();
  }

  function deleteGaCookies() {
    var names = document.cookie.split(';').map(function (c) {
      return c.split('=')[0].trim();
    }).filter(function (n) {
      return n === '_ga' || n.indexOf('_ga_') === 0 || n === '_gid' || n === '_gat' || n.indexOf('_gat_') === 0;
    });
    var host = location.hostname;
    var parts = host.split('.');
    var domains = [''];
    for (var i = 0; i < parts.length - 1; i++) {
      domains.push('; domain=.' + parts.slice(i).join('.'));
    }
    domains.push('; domain=' + host);
    names.forEach(function (n) {
      domains.forEach(function (d) {
        document.cookie = n + '=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/' + d;
      });
    });
  }

  // ---- banner ------------------------------------------------------------
  var CSS = [
    '.hf-consent{position:fixed;z-index:400;right:20px;bottom:20px;width:360px;max-width:calc(100vw - 32px);',
    'box-sizing:border-box;background:var(--card,#181830);color:var(--text,#EFEFFA);',
    'border:1px solid var(--border2,rgba(255,255,255,.15));border-radius:16px;overflow:hidden;',
    "box-shadow:0 12px 40px rgba(0,0,0,.28);font-family:'DM Sans',sans-serif;",
    'opacity:0;transform:translateY(12px);transition:opacity .25s ease,transform .25s ease}',
    '.hf-consent.is-open{opacity:1;transform:none}',
    '.hf-consent[hidden]{display:none}',
    '.hf-consent__bar{height:4px;background:linear-gradient(90deg,#073EE3,#FF4D4D)}',
    '.hf-consent__body{padding:18px 20px 20px}',
    ".hf-consent__title{margin:0 0 6px;font-family:'Zalando Sans Expanded',sans-serif;font-weight:800;font-size:15px;line-height:1.3;color:var(--text,#EFEFFA)}",
    '.hf-consent__text{margin:0 0 16px;font-size:14px;line-height:1.5;color:var(--text2,#9898BB)}',
    '.hf-consent__text a{color:var(--brand-fg,#5E86FF)}',
    '.hf-consent__actions{display:grid;grid-template-columns:1fr 1fr;gap:10px}',
    /* Both buttons share one class: identical size, style and contrast. */
    ".hf-consent__btn{appearance:none;margin:0;min-height:38px;padding:8px 12px;border-radius:10px;",
    "border:1px solid var(--text2,#9898BB);background:transparent;color:var(--text,#EFEFFA);",
    "font-family:'DM Sans',sans-serif;font-size:13px;font-weight:600;line-height:1.2;cursor:pointer;",
    "transition:background-color .15s ease,border-color .15s ease}",
    '.hf-consent__btn:hover{background:var(--border,rgba(255,255,255,.08));border-color:var(--text,#EFEFFA)}',
    '.hf-consent__btn:focus-visible{outline:3px solid var(--brand-fg,#5E86FF);outline-offset:2px}',
    '.hf-consent__title:focus{outline:none}',
    '[data-cookie-settings]:focus-visible{outline:2px solid var(--brand-fg,#5E86FF);outline-offset:2px;border-radius:2px}',
    '@media (max-width:600px){.hf-consent{left:0;right:0;bottom:0;width:auto;max-width:none;',
    'border-radius:16px 16px 0 0;border-bottom:0;box-shadow:0 -8px 30px rgba(0,0,0,.25)}',
    '.hf-consent__body{padding:14px 16px calc(14px + env(safe-area-inset-bottom))}',
    '.hf-consent__text{font-size:13px;margin-bottom:12px}.hf-consent__btn{min-height:44px}}',
    '@media (prefers-reduced-motion:reduce){.hf-consent,.hf-consent__btn{transition:none}.hf-consent{transform:none}}'
  ].join('');

  function build() {
    var style = document.createElement('style');
    style.id = 'hf-consent-style';
    style.textContent = CSS;
    document.head.appendChild(style);

    banner = document.createElement('section');
    banner.className = 'hf-consent';
    banner.setAttribute('role', 'dialog');
    banner.setAttribute('aria-modal', 'false');
    banner.setAttribute('aria-labelledby', 'hf-consent-title');
    banner.setAttribute('aria-describedby', 'hf-consent-text');
    banner.hidden = true;
    var privacy = PRIVACY_URL
      ? ' <a href="' + PRIVACY_URL + '">Privacy policy</a>'
      : '';
    banner.innerHTML =
      '<div class="hf-consent__bar" aria-hidden="true"></div>' +
      '<div class="hf-consent__body">' +
        '<h2 class="hf-consent__title" id="hf-consent-title" tabindex="-1">Your privacy, your call</h2>' +
        '<p class="hf-consent__text" id="hf-consent-text">We’d like to set analytics cookies (Google Analytics) to understand how fans use HerFixtures. You can change your mind anytime under Cookie settings.' + privacy + '</p>' +
        '<div class="hf-consent__actions">' +
          '<button type="button" class="hf-consent__btn" data-consent="denied">Reject analytics</button>' +
          '<button type="button" class="hf-consent__btn" data-consent="granted">Accept analytics</button>' +
        '</div>' +
      '</div>';
    banner.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-consent]');
      if (btn) choose(btn.getAttribute('data-consent'));
    });
    document.body.appendChild(banner);
  }

  function open(moveFocus) {
    if (!banner) build();
    banner.hidden = false;
    // next frame so the entry transition runs
    requestAnimationFrame(function () { banner.classList.add('is-open'); });
    if (moveFocus) banner.querySelector('.hf-consent__title').focus();
  }

  function close() {
    if (!banner) return;
    banner.classList.remove('is-open');
    banner.hidden = true;
    if (returnFocusTo && document.contains(returnFocusTo)) returnFocusTo.focus();
    returnFocusTo = null;
  }

  function choose(v) {
    saveChoice(v);
    if (v === 'granted') enableAnalytics(); else disableAnalytics();
    close();
  }

  // ---- start ---------------------------------------------------------------
  function init() {
    document.addEventListener('click', function (e) {
      var link = e.target.closest && e.target.closest('[data-cookie-settings]');
      if (!link) return;
      e.preventDefault();
      returnFocusTo = link;
      open(true);
    });
    document.addEventListener('keydown', function (e) {
      // the footer link has role="button", so Space activates it too
      if (e.key === ' ' && e.target.closest && e.target.closest('[data-cookie-settings]')) {
        e.preventDefault();
        e.target.click();
        return;
      }
      if (e.key === 'Escape' && banner && !banner.hidden && returnFocusTo) close();
    });
    var choice = readChoice();
    if (choice === 'granted') enableAnalytics();
    else if (choice === null) open(false);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
