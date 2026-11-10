(function () {
  'use strict';
  var FONT = {" ":"...................................","-":"................###................","/":"....#....#...#...#...#...#....#....","0":".###.#...##..###.#.###..##...#.###.","1":"..#...##....#....#....#....#...###.","2":".###.#...#....#...#...#...#...#####","3":"#####...#...#.....#.....##...#.###.","4":"...#...##..#.#.#..#.#####...#....#.","5":"######....####.....#....##...#.###.","6":"..##..#...#....####.#...##...#.###.","7":"#####....#...#...#...#....#....#...","8":".###.#...##...#.###.#...##...#.###.","9":".###.#...##...#.####....#...#..##..","?":".###.#...#....#...#...#.........#..","A":".###.#...##...#######...##...##...#","B":"####.#...##...#####.#...##...#####.","C":".###.#...##....#....#....#...#.###.","D":"####.#...##...##...##...##...#####.","E":"######....#....####.#....#....#####","F":"######....#....####.#....#....#....","G":".###.#...##....#.####...##...#.###.","H":"#...##...##...#######...##...##...#","I":".###...#....#....#....#....#...###.","J":"..###...#....#....#....#.#..#..##..","K":"#...##..#.#.#..##...#.#..#..#.#...#","L":"#....#....#....#....#....#....#####","M":"#...###.###.#.##.#.##...##...##...#","N":"#...##...###..##.#.##..###...##...#","O":".###.#...##...##...##...##...#.###.","P":"####.#...##...#####.#....#....#....","Q":".###.#...##...##...##.#.##..#..##.#","R":"####.#...##...#####.#.#..#..#.#...#","S":".#####....#.....###.....#....#####.","T":"#####..#....#....#....#....#....#..","U":"#...##...##...##...##...##...#.###.","V":"#...##...##...##...##...#.#.#...#..","W":"#...##...##...##.#.##.#.##.#.#.#.#.","X":"#...##...#.#.#...#...#.#.#...##...#","Y":"#...##...#.#.#...#....#....#....#..","Z":"#####....#...#...#...#...#....#####"};
  var LABELS = {"all":"ALL","character":"CAST","cover":"COVERS","game":"GAMES","kit":"KITS","sound":"SOUNDS","style":"STYLES"};
  var cards = Array.prototype.slice.call(document.querySelectorAll('.card'));
  var kinds = Array.prototype.slice.call(document.querySelectorAll('.kind'));
  var input = document.getElementById('q');
  var counter = document.getElementById('count');
  var empty = document.getElementById('empty');
  var current = 'all';

  function pixel(text, scale, fill) {
    var rows = ['', '', '', '', '', '', ''];
    text.toUpperCase().split('').forEach(function (ch, i) {
      var cells = FONT[ch] || FONT['?'];
      for (var y = 0; y < 7; y++) { rows[y] += (i ? '.' : '') + cells.substr(y * 5, 5); }
    });
    var rects = '';
    rows.forEach(function (row, y) {
      row.replace(/#+/g, function (run, x) { rects += '<rect x="' + x + '" y="' + y + '" width="' + run.length + '" height="1"/>'; return run; });
    });
    var w = rows[0].length;
    return '<svg class="px" viewBox="0 0 ' + w + ' 7" width="' + w * scale + '" height="' + 7 * scale +
      '" fill="' + fill + '" shape-rendering="crispEdges" aria-hidden="true">' + rects + '</svg>';
  }

  function apply() {
    var words = input.value.toLowerCase().split(/[^a-z0-9]+/).filter(Boolean);
    var shown = 0;
    cards.forEach(function (card) {
      var hay = card.getAttribute('data-search');
      var ok = (current === 'all' || card.getAttribute('data-kind') === current) &&
        words.every(function (w) {
          // Like `hub search`: a plural also matches its singular as a word prefix ("steps" finds "stepping").
          return hay.indexOf(w) !== -1 || (w.length > 3 && w.charAt(w.length - 1) === 's' && hay.indexOf(w.slice(0, -1)) !== -1);
        });
      card.hidden = !ok;
      if (ok) { shown++; }
    });
    var label = LABELS[current] + ' ' + shown + '/' + cards.length;
    counter.innerHTML = pixel(label, 2, '#b0202a');
    counter.setAttribute('aria-label', label);
    empty.hidden = shown !== 0;
    var hash = (current === 'all' ? '' : 'kind=' + current) + (words.length ? (current === 'all' ? '' : '&') + 'q=' +
      encodeURIComponent(words.join(' ')) : '');
    if (history.replaceState) { history.replaceState(null, '', hash ? '#' + hash : location.pathname); }
  }

  function choose(button, focus) {
    current = button.getAttribute('data-kind');
    kinds.forEach(function (b) {
      var on = b === button;
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
      b.tabIndex = on ? 0 : -1;
    });
    if (focus) { button.focus(); }
    apply();
  }

  kinds.forEach(function (button, i) {
    button.addEventListener('click', function () { choose(button, false); });
    button.addEventListener('keydown', function (e) {
      var step = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
      if (step) { e.preventDefault(); choose(kinds[(i + step + kinds.length) % kinds.length], true); }
    });
  });

  input.addEventListener('input', apply);
  input.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { input.value = ''; apply(); }
  });
  document.addEventListener('keydown', function (e) {
    var typing = document.activeElement && /^(INPUT|TEXTAREA)$/.test(document.activeElement.tagName);
    if (e.key === '/' && !typing) { e.preventDefault(); input.focus(); input.select(); }
  });

  function copy(text, done) {
    function fallback() {
      var area = document.createElement('textarea');
      area.value = text;
      area.setAttribute('readonly', '');
      area.style.position = 'fixed';
      area.style.opacity = '0';
      document.body.appendChild(area);
      area.select();
      try { document.execCommand('copy'); } catch (err) { /* selection stays for a manual copy */ }
      document.body.removeChild(area);
      done();
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, fallback);
    } else { fallback(); }
  }

  document.addEventListener('click', function (e) {
    var button = e.target.closest ? e.target.closest('.copy') : null;
    if (!button) { return; }
    copy(button.getAttribute('data-cmd'), function () {
      var label = button.querySelector('.go');
      button.classList.add('done');
      label.textContent = 'COPIED';
      setTimeout(function () { button.classList.remove('done'); label.textContent = 'COPY'; }, 1400);
    });
  });

  location.hash.replace(/^#/, '').split('&').forEach(function (part) {   // shareable #kind=sound&q=rain
    var pair = part.split('=');
    if (pair[0] === 'q') { input.value = decodeURIComponent(pair[1] || ''); }
    if (pair[0] === 'kind') {
      kinds.forEach(function (b) { if (b.getAttribute('data-kind') === pair[1]) { choose(b, false); } });
    }
  });
  apply();
}());
