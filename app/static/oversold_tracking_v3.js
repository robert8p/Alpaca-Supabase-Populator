(() => {
  const load = (src, done) => {
    const script = document.createElement('script');
    script.src = src;
    script.async = false;
    script.onload = () => done?.();
    document.head.appendChild(script);
  };
  load('/static/oversold_tracking_v3_base.js?v=1', () => {
    load('/static/oversold_day3_ui.js?v=1');
  });
})();
