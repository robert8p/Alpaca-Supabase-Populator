(() => {
  const load = (src, done) => {
    const script = document.createElement('script');
    script.src = src;
    script.async = false;
    script.onload = () => done?.();
    document.head.appendChild(script);
  };
  load('/static/oversold_tracking_v3_base.js?v=1', () => {
    load('/static/oversold_day3_ui.js?v=1', () => {
      load('/static/oversold_fundamentals_rating_v2.js?v=1', () => {
        load('/static/oversold_v33_ui.js?v=1', () => {
          load('/static/oversold_chatgpt_v33.js?v=1', () => {
            load('/static/oversold_v33_explainability.js?v=1', () => {
              load('/static/oversold_primary_evidence_ui.js?v=1');
            });
          });
        });
      });
    });
  });
})();
