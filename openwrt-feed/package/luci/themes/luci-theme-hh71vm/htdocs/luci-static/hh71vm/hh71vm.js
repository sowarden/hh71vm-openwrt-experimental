/*
 * luci-theme-hh71vm -- theme runtime.
 * Licensed to the public under the Apache License 2.0.
 *
 * Four jobs:
 *   1. the light/dark switch,
 *   2. the navigation -- we render the menu into a sidebar ourselves, because
 *      luci-base's menu-bootstrap.js only knows how to build a horizontal bar,
 *   3. the modem status strip in the top bar,
 *   4. copy-to-clipboard on values worth copying.
 *
 * Everything here degrades: without the modem daemon the strip stays hidden, and
 * without a session the menu simply is not rendered.
 */
(function () {
	'use strict';

	var root = document.documentElement;
	var HH = window.HH71 = {};

	var SVG = 'http://www.w3.org/2000/svg';

	/* Feather-style 24x24 stroke icons.  Inline SVG rather than a font or images:
	   it inherits currentColor, needs no network, and costs a few hundred bytes. */
	var ICONS = {
		activity: '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>',
		sliders:  '<line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/>' +
		          '<line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/>' +
		          '<line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/>' +
		          '<line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/>' +
		          '<line x1="17" y1="16" x2="23" y2="16"/>',
		globe:    '<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/>' +
		          '<path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>',
		radio:    '<circle cx="12" cy="12" r="2"/><path d="M16.24 7.76a6 6 0 0 1 0 8.48m-8.48 0a6 6 0 0 1 0-8.48m11.31-2.83a10 10 0 0 1 0 14.14m-14.14 0a10 10 0 0 1 0-14.14"/>',
		layers:   '<polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>',
		shield:   '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
		chart:    '<line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>',
		dot:      '<circle cx="12" cy="12" r="8"/>',
		caret:    '<polyline points="9 18 15 12 9 6"/>',
		sun:      '<circle cx="12" cy="12" r="4.5"/><line x1="12" y1="1.5" x2="12" y2="3.5"/>' +
		          '<line x1="12" y1="20.5" x2="12" y2="22.5"/><line x1="4" y1="4" x2="5.5" y2="5.5"/>' +
		          '<line x1="18.5" y1="18.5" x2="20" y2="20"/><line x1="1.5" y1="12" x2="3.5" y2="12"/>' +
		          '<line x1="20.5" y1="12" x2="22.5" y2="12"/><line x1="4" y1="20" x2="5.5" y2="18.5"/>' +
		          '<line x1="18.5" y1="5.5" x2="20" y2="4"/>',
		moon:     '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
		copy:     '<rect x="9" y="9" width="12" height="12" rx="2"/>' +
		          '<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
		check:    '<polyline points="20 6 9 17 4 12"/>'
	};

	/* menu category -> icon, matched on the dispatcher node name */
	var GROUP_ICONS = {
		status: 'activity', system: 'sliders', network: 'globe', modem: 'radio',
		services: 'layers', vpn: 'shield', statistics: 'chart', bandwidth: 'chart'
	};

	function icon(name, cls) {
		var s = document.createElementNS(SVG, 'svg');
		s.setAttribute('viewBox', '0 0 24 24');
		s.setAttribute('fill', 'none');
		s.setAttribute('stroke', 'currentColor');
		s.setAttribute('stroke-width', '2');
		s.setAttribute('stroke-linecap', 'round');
		s.setAttribute('stroke-linejoin', 'round');
		s.setAttribute('aria-hidden', 'true');
		if (cls) s.setAttribute('class', cls);
		s.innerHTML = ICONS[name] || ICONS.dot;
		return s;
	}

	function el(tag, attrs, kids) {
		var e = document.createElement(tag);
		for (var k in attrs || {})
			if (attrs[k] != null) e.setAttribute(k, attrs[k]);
		(Array.isArray(kids) ? kids : (kids != null ? [kids] : [])).forEach(function (k) {
			e.appendChild(typeof k === 'string' ? document.createTextNode(k) : k);
		});
		return e;
	}

	/* ------------------------------------------------------------ theme */

	function setTheme(t, remember) {
		root.setAttribute('data-theme', t);
		if (remember) { try { localStorage.setItem('hh71vm-theme', t); } catch (e) {} }
		var b = document.getElementById('theme-toggle');
		if (b) {
			b.textContent = '';
			b.appendChild(icon(t === 'dark' ? 'sun' : 'moon'));
		}
	}

	// A choice the user never made should follow the system, including when the
	// system changes while the page is open.
	try {
		var mq = matchMedia('(prefers-color-scheme: dark)');
		var onSys = function () {
			var saved = null;
			try { saved = localStorage.getItem('hh71vm-theme'); } catch (e) {}
			if (saved !== 'light' && saved !== 'dark')
				setTheme(mq.matches ? 'dark' : 'light', false);
		};
		if (mq.addEventListener) mq.addEventListener('change', onSys);
		else if (mq.addListener) mq.addListener(onSys);
	} catch (e) {}

	/* ------------------------------------------------------- navigation */

	var NAV_STATE = 'hh71vm-nav-open';

	function readOpen() {
		try { return JSON.parse(localStorage.getItem(NAV_STATE)) || {}; } catch (e) { return {}; }
	}
	function writeOpen(o) {
		try { localStorage.setItem(NAV_STATE, JSON.stringify(o)); } catch (e) {}
	}

	function renderSideNav(ui, mode, modeName) {
		var nav = document.getElementById('sidenav');
		if (!nav) return;

		var open = readOpen();
		var path = L.env.dispatchpath || [];
		var groups = ui.menu.getChildren(mode);

		groups.forEach(function (g) {
			/* Logout lives in the sidebar footer, where it cannot be mistaken for
			   a settings page. */
			if (g.name === 'logout') return;

			var items = ui.menu.getChildren(g);
			var groupUrl = modeName + '/' + g.name;

			/* A category without visible children is a page in its own right. */
			if (!items.length) {
				var solo = el('div', { 'class': 'sb-group' }, [
					el('ul', { 'class': 'sb-items', 'style': 'display:block' },
					   el('li', { 'class': path[1] === g.name ? 'active' : null },
					      el('a', { 'href': L.url(groupUrl) }, String(g.title || g.name))))
				]);
				nav.appendChild(solo);
				return;
			}

			var isActive = (path[1] === g.name);
			var isOpen = isActive || open[g.name] === true;

			var list = el('ul', { 'class': 'sb-items' });
			items.forEach(function (it) {
				var li = el('li', { 'class': (isActive && path[2] === it.name) ? 'active' : null },
				            el('a', {
				                'href': L.url(groupUrl, it.name),
				                'aria-current': (isActive && path[2] === it.name) ? 'page' : null
				            }, String(it.title || it.name)));
				list.appendChild(li);
			});

			var head = el('button', { 'type': 'button', 'class': 'sb-head',
			                          'aria-expanded': isOpen ? 'true' : 'false' }, [
				icon(GROUP_ICONS[g.name] || 'dot'),
				el('span', {}, String(g.title || g.name)),
				icon('caret', 'sb-caret')
			]);

			var group = el('div', {
				'class': 'sb-group' + (isOpen ? ' open' : '') + (isActive ? ' has-active' : '')
			}, [head, list]);

			head.addEventListener('click', function () {
				var nowOpen = !group.classList.contains('open');
				group.classList.toggle('open', nowOpen);
				head.setAttribute('aria-expanded', nowOpen ? 'true' : 'false');
				var st = readOpen();
				st[g.name] = nowOpen;
				writeOpen(st);
			});

			nav.appendChild(group);
		});
	}

	function renderModeMenu(ui, modes, activeName) {
		var ul = document.getElementById('modemenu');
		if (!ul || modes.length < 2) return;
		modes.forEach(function (m) {
			ul.appendChild(el('li', { 'class': m.name === activeName ? 'active' : null },
			                  el('a', { 'href': L.url(m.name) }, String(m.title || m.name))));
		});
		ul.hidden = false;
	}

	/* Page tabs: the fourth dispatcher level and below.  Same walk as
	   menu-bootstrap.js does, so third-party pages keep their tabs. */
	function renderTabMenu(ui, node, url, level) {
		var container = document.getElementById('tabmenu');
		if (!container) return;

		var children = ui.menu.getChildren(node);
		if (!children.length) return;

		var ul = el('ul', { 'class': 'tabs' });
		var activeNode = null;

		children.forEach(function (c) {
			var isActive = (L.env.dispatchpath[3 + (level || 0)] === c.name);
			ul.appendChild(el('li', {
				'class': 'tabmenu-item-' + c.name + (isActive ? ' active' : '')
			}, el('a', { 'href': L.url(url, c.name) }, String(c.title || c.name))));
			if (isActive) activeNode = c;
		});

		container.appendChild(ul);
		if (activeNode)
			renderTabMenu(ui, activeNode, url + '/' + activeNode.name, (level || 0) + 1);
	}

	function renderMenu() {
		if (!window.L || !L.require) return Promise.resolve();
		return L.require('ui').then(function (ui) {
			return ui.menu.load().then(function (tree) {
				var modes = ui.menu.getChildren(tree);
				if (!modes.length) return;

				var first = (L.env.requestpath && L.env.requestpath.length)
				          ? L.env.requestpath[0] : null;
				var mode = null;
				for (var i = 0; i < modes.length; i++)
					if (modes[i].name === first) mode = modes[i];
				if (!mode) mode = modes[0];

				renderModeMenu(ui, modes, mode.name);
				renderSideNav(ui, mode, mode.name);

				/* tabs hang off the third dispatcher level */
				var node = tree, url = '';
				if (L.env.dispatchpath.length >= 3) {
					for (var j = 0; j < 3 && node; j++) {
						node = node.children ? node.children[L.env.dispatchpath[j]] : null;
						url = url + (url ? '/' : '') + L.env.dispatchpath[j];
					}
					if (node) renderTabMenu(ui, node, url);
				}
			});
		}).catch(function () { /* no session, no menu -- the login page needs none */ });
	}

	/* Every navigation is a full page load, so the sidebar is rebuilt from scratch
	   and lands back at the top.  On a menu this tall that means scrolling down to
	   the same place again after every click, so the offset is remembered for the
	   tab.  sessionStorage, not localStorage: it is a property of this browsing
	   session, and a new window should start at the top. */
	var NAV_SCROLL = 'hh71vm-nav-scroll';

	function restoreNavScroll() {
		var nav = document.getElementById('sidenav');
		if (!nav) return;

		nav.addEventListener('scroll', function () {
			try { sessionStorage.setItem(NAV_SCROLL, String(nav.scrollTop)); } catch (e) {}
		}, { passive: true });

		renderMenu().then(function () {
			var y = 0;
			try { y = parseInt(sessionStorage.getItem(NAV_SCROLL), 10) || 0; } catch (e) {}
			if (y > 0) nav.scrollTop = y;

			/* The offset was taken from the previous page, whose groups may have been
			   open where this page's are closed.  If the current entry ended up out of
			   sight the remembered offset is simply wrong -- show the entry instead.
			   Measured with rects, not offsetTop: the nav is not the offset parent
			   (the fixed #sidebar is), so offsetTop is not an offset into the scroll
			   box and comparing it against scrollTop gives nonsense. */
			var cur = nav.querySelector('.sb-items li.active > a');
			if (!cur) return;
			var nr = nav.getBoundingClientRect(), cr = cur.getBoundingClientRect();
			if (cr.top < nr.top || cr.bottom > nr.bottom)
				nav.scrollTop += (cr.top - nr.top) - (nr.height - cr.height) / 2;
		});
	}

	/* -------------------------------------------------------- clipboard */

	// The web UI is served over plain HTTP, where navigator.clipboard does not exist
	// in any current browser -- so the textarea path is the normal one here, not a
	// fallback.
	HH.copy = function (text) {
		var ok = false;
		try {
			var ta = document.createElement('textarea');
			ta.value = text;
			ta.setAttribute('readonly', '');
			ta.style.cssText = 'position:fixed;top:-1000px;opacity:0';
			document.body.appendChild(ta);
			ta.select();
			ta.setSelectionRange(0, ta.value.length);
			ok = document.execCommand('copy');
			document.body.removeChild(ta);
		} catch (e) { ok = false; }
		if (!ok && navigator.clipboard) {
			navigator.clipboard.writeText(text);
			ok = true;
		}
		return ok;
	};

	var toastTimer = null;
	HH.toast = function (msg) {
		var e = document.querySelector('.toast');
		if (!e) {
			e = document.createElement('div');
			e.className = 'toast';
			e.setAttribute('role', 'status');
			document.body.appendChild(e);
		}
		e.textContent = msg;
		clearTimeout(toastTimer);
		toastTimer = setTimeout(function () { e.remove(); }, 1800);
	};

	HH.copyButton = function (getValue) {
		var b = el('button', { 'type': 'button', 'class': 'copy-btn', 'title': 'Copy',
		                       'aria-label': 'Copy' }, icon('copy'));
		b.addEventListener('click', function (ev) {
			ev.preventDefault();
			ev.stopPropagation();
			var v = getValue();
			if (!v) return;
			if (HH.copy(v)) {
				b.classList.add('done');
				b.textContent = '';
				b.appendChild(icon('check'));
				HH.toast('Copied: ' + (v.length > 42 ? v.slice(0, 42) + '…' : v));
				setTimeout(function () {
					b.classList.remove('done');
					b.textContent = '';
					b.appendChild(icon('copy'));
				}, 1400);
			}
		});
		return b;
	};

	/* ------------------------------------------------------ zone colours */

	/* LuCI shows which firewall zone an interface belongs to by writing a pastel
	   straight onto the element as an inline background-color.  On the stock white
	   theme that is a mint or salmon block with black text on it; here the text is
	   light, and in the dark theme the block is both loud and unreadable.
	   The colour carries real information, so it moves into a dot and the chip goes
	   back to a normal surface.  The stylesheet neutralises the inline background
	   (matching on the style attribute, so nothing flashes before this runs) and
	   leaves the value in place for us to read here. */
	function zoneDots(scope) {
		var list = (scope || document).querySelectorAll(
			'.ifacebox-head[style*="background-color"]:not([data-zdot]),' +
			'.zonebadge[style*="background-color"]:not([data-zdot])');
		for (var i = 0; i < list.length; i++) {
			var e = list[i], c = e.style.backgroundColor;
			e.setAttribute('data-zdot', '1');
			if (!c) continue;
			var d = el('span', { 'class': 'zdot' });
			d.style.background = c;
			/* A zone chip is small and reads as "<dot> lan"; an interface box has a
			   heading of its own, and the dot belongs at the far end of it. */
			if (e.classList.contains('zonebadge')) e.insertBefore(d, e.firstChild);
			else e.appendChild(d);
		}
	}

	// Any element carrying data-copy gets a discreet button; the value copied is the
	// attribute when it has content, otherwise the element's own text.
	HH.decorate = function (scope) {
		var list = (scope || document).querySelectorAll('[data-copy]:not([data-copy-done])');
		for (var i = 0; i < list.length; i++) {
			(function (e) {
				e.setAttribute('data-copy-done', '1');
				e.classList.add('copyable');
				e.appendChild(HH.copyButton(function () {
					return e.getAttribute('data-copy') || (e.textContent || '').trim();
				}));
			})(list[i]);
		}
		zoneDots(scope);
	};

	/* Most views redraw themselves on a timer, and every redraw hands back plain
	   LuCI markup -- so decoration has to be reapplied, not applied once.  Both
	   passes mark what they have touched, which is also what stops the observer
	   from feeding on its own changes. */
	function watchContent() {
		if (!window.MutationObserver) return;
		/* The whole body, not #maincontent: ui.js hangs its modal dialogs off <body>,
		   and those carry the same badges as the page behind them. */
		var timer = null;
		new MutationObserver(function () {
			if (timer) return;
			timer = setTimeout(function () { timer = null; HH.decorate(document); }, 120);
		}).observe(document.body, { childList: true, subtree: true });
	}

	/* ----------------------------------------------------- modem strip */

	function bars(n, cls) {
		var b = el('span', { 'class': 'bars ' + (cls || '') });
		for (var i = 1; i <= 5; i++) b.appendChild(el('i', i <= n ? { 'class': 'on' } : {}));
		return b;
	}

	function human(n) {
		if (n == null) return '';
		var u = ['B', 'KiB', 'MiB', 'GiB', 'TiB'], i = 0;
		while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
		return (i === 0 ? n : n.toFixed(n < 10 ? 2 : 1)) + ' ' + u[i];
	}

	function chip(kids, cls, title) {
		return el('span', { 'class': 'mi' + (cls ? ' ' + cls : ''), 'title': title || null }, kids);
	}

	HH.renderStrip = function (s) {
		var box = document.getElementById('modem-strip');
		if (!box) return;

		var link = s.link || {}, net = s.net || {}, sig = s.signal || {},
		    data = s.data || {}, sms = s.sms || {}, use = s.usage || {},
		    radio = s.radio || {};
		var out = [];

		if (link.state !== 'ready') {
			out.push(chip([
				el('span', { 'class': 'tech off' }, String(link.state || 'down').toUpperCase()),
				el('b', {}, link.error || 'modem channel unavailable')
			], 'warnpill'));
		} else if (radio.on === false) {
			out.push(chip([
				el('span', { 'class': 'tech off' }, 'OFF'),
				el('b', {}, 'Radio disabled')
			], 'warnpill'));
		} else {
			var n = sig.bars || 0;
			var cls = n >= 4 ? '' : (n >= 2 ? 'weak' : 'bad');
			var lvl = (sig.rsrp != null) ? sig.rsrp + ' dBm'
			        : (sig.rssi_dbm != null ? sig.rssi_dbm + ' dBm' : '–');
			out.push(chip([bars(n, cls), el('b', {}, lvl)], null,
			              (sig.rsrp != null ? 'RSRP ' : 'RSSI ') + lvl));
			out.push(chip([
				el('span', { 'class': 'tech' }, net.act_name || net.sysmode || '–'),
				el('b', {}, net.operator || (net.registered ? '–' : 'not registered'))
			].concat(net.roaming ? [el('span', { 'class': 'label warning' }, 'roaming')] : [])));
			if (sig.band)
				out.push(chip([el('span', { 'class': 'mi-k' }, 'Band'), el('b', {}, String(sig.band))]));
			if (data.ipv4)
				out.push(chip([el('span', { 'class': 'mi-k' }, 'IP'), el('b', {}, data.ipv4)]));
		}

		if (use.rx != null)
			out.push(chip([
				el('span', { 'class': 'mi-k' }, '↓'), el('b', {}, human(use.rx)),
				el('span', { 'class': 'mi-k' }, '↑'), el('b', {}, human(use.tx))
			], null, 'Traffic on the WAN interface since the counter was last reset'));

		out.push(el('span', { 'class': 'sep', 'style': 'flex:1 1 auto' }));

		/* The counter follows the message list, not the storage slots: a long text
		   occupies several slots but is still one message. */
		var unread = sms.unread || 0;
		var count = (sms.count != null) ? sms.count : null;
		var smsKids = [el('span', { 'class': 'mi-k' }, 'SMS')];
		if (unread) smsKids.push(el('span', { 'class': 'badge-n' }, String(unread)));
		else if (count != null) smsKids.push(el('b', {}, String(count)));
		out.push(el('a', { 'class': 'mi', 'href': HH.url('admin/modem/sms'),
		                   'title': unread ? unread + ' unread' : 'Messages' }, smsKids));

		/* A drawn chevron, not the text one: the glyph's ink sits below the middle of
		   its own line box in most faces, so however the box is centred the mark still
		   reads as sitting low. */
		out.push(el('a', { 'class': 'mi', 'href': HH.url('admin/modem') }, [
			el('b', {}, 'Modem'), icon('caret', 'mi-arrow')
		]));

		box.textContent = '';
		out.forEach(function (o) { box.appendChild(o); });
	};

	HH.base = (window.L && L.env && L.env.scriptname) ? L.env.scriptname : '/cgi-bin/luci';
	HH.url = function (p) { return HH.base + '/' + p; };

	// The strip reads the same ubus object the modem pages use, so it inherits the
	// session ACL and needs no endpoint of its own.
	var stripTimer = null, stripFails = 0, statusCall = null;

	// force: draw once even on a tab that is not in front, so the bar is already
	// filled in when the user comes back to it; only the repeat respects visibility
	function pollStrip(force) {
		if ((document.hidden && !force) || !window.L || !L.require) return;
		L.require('rpc').then(function (rpc) {
			if (!statusCall)
				statusCall = rpc.declare({ object: 'hh71vm-modem', method: 'status' });
			return statusCall();
		}).then(function (res) {
			stripFails = 0;
			HH.renderStrip(res || {});
		}).catch(function () {
			// optional by design: without the modem app the strip stays empty
			if (++stripFails >= 3 && stripTimer) {
				clearInterval(stripTimer);
				stripTimer = null;
			}
		});
	}

	/* ------------------------------------------------------------- init */

	function init() {
		setTheme(root.getAttribute('data-theme') || 'light', false);

		var btn = document.getElementById('theme-toggle');
		if (btn) btn.addEventListener('click', function () {
			setTheme(root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark', true);
		});

		HH.decorate(document);
		watchContent();

		/* The login page carries no session.  Any ubus call from here comes back
		   -32002, and luci.js answers that with the global "Session expired" modal
		   -- on the login page itself, on top of the form, with a button that only
		   reloads the page and brings the modal straight back.  So on that page the
		   theme does nothing that needs a session.  header.htm marks it: no-nav. */
		if (document.body.classList.contains('no-nav'))
			return;

		restoreNavScroll();   /* renders the menu, then puts the scroll offset back */

		if (document.getElementById('modem-strip')) {
			pollStrip(true);
			stripTimer = setInterval(pollStrip, 10000);
			document.addEventListener('visibilitychange', function () {
				if (!document.hidden) pollStrip(true);
			});
		}
	}

	if (document.readyState === 'loading')
		document.addEventListener('DOMContentLoaded', init);
	else
		init();
})();
