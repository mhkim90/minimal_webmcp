// Minimal offline DOM-to-canvas screenshot.
// Uses SVG foreignObject hack — no external deps, no internet.
// Returns Promise<string> resolving to base64 PNG (without data: prefix).
(function() {
  window.__minimal_webmcp_screenshot = async function() {
    try {
      // Get full page dimensions
      const w = Math.max(
        document.documentElement.scrollWidth,
        document.body ? document.body.scrollWidth : 0
      );
      const h = Math.max(
        document.documentElement.scrollHeight,
        document.body ? document.body.scrollHeight : 0
      );
      // Clone body, inline all computed styles (best-effort)
      const clone = document.documentElement.cloneNode(true);
      // Inline styles for visibility into foreignObject
      const sheets = document.styleSheets;
      let cssText = '';
      try {
        for (const sheet of sheets) {
          try {
            for (const rule of sheet.cssRules) cssText += rule.cssText + '\n';
          } catch(e) { /* cross-origin */ }
        }
      } catch(e) {}
      const style = document.createElement('style');
      style.textContent = cssText;
      const head = clone.querySelector('head') || (function(){
        const h = document.createElement('head');
        clone.insertBefore(h, clone.firstChild);
        return h;
      })();
      head.appendChild(style);
      // Build SVG
      const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="' + w + '" height="' + h + '">'
        + '<foreignObject width="100%" height="100%">'
        + new XMLSerializer().serializeToString(clone)
        + '</foreignObject></svg>';
      const blob = new Blob([svg], {type: 'image/svg+xml'});
      const url = URL.createObjectURL(blob);
      const img = new Image();
      await new Promise((resolve, reject) => {
        img.onload = resolve;
        img.onerror = reject;
        img.src = url;
      });
      const canvas = document.createElement('canvas');
      canvas.width = w;
      canvas.height = h;
      const ctx = canvas.getContext('2d');
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(0, 0, w, h);
      ctx.drawImage(img, 0, 0);
      URL.revokeObjectURL(url);
      const data = canvas.toDataURL('image/png');
      return data.split(',')[1];
    } catch (e) {
      throw new Error('screenshot failed: ' + e.message);
    }
  };
})();
