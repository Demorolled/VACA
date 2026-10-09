(() => {
  function find(root) {
    for (const el of root.querySelectorAll('*')) {
      if (el.shadowRoot) {
        const r = find(el.shadowRoot);
        if (r) return r;
      }
      const t = (el.textContent || '').trim().replace(/\s+/g, ' ');
      if ((el.tagName.includes('MD-') || el.tagName === 'BUTTON') && t.toLowerCase().includes('upload notebook')) {
        return el;
      }
    }
    return null;
  }
  const el = find(document);
  if (!el) return 'NOT FOUND: upload notebook';
  el.click();
  return 'clicked: ' + el.tagName + ' | ' + el.textContent.trim().slice(0, 40);
})()
