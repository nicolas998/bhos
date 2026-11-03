// Streamlit component (components v2) that reports zooming and panning on any plot to Python,
// which then redraws every plot over that range, so all x axes move together.
// Sends trigger value "range": [start, end] as local-time strings, or "reset" on double-click.
export default function ({ setTriggerValue }) {
  const listening = new Map();  // plot element -> its relayout listener

  const onRelayout = (event) => {
    if (event["xaxis.autorange"]) {
      setTriggerValue("range", "reset");
    } else if (event["xaxis.range[0]"] !== undefined) {
      setTriggerValue("range", [String(event["xaxis.range[0]"]), String(event["xaxis.range[1]"])]);
    } else if (event["xaxis.range"]) {
      setTriggerValue("range", event["xaxis.range"].map(String));
    }
  };

  const listen = () => {
    for (const gd of document.querySelectorAll(".js-plotly-plot")) {
      // A redraw can drop a plot's listeners, so check the listener itself, not just the map.
      const attached = listening.get(gd);
      if (!gd.on || (attached && gd._ev && gd._ev.listeners("plotly_relayout").includes(attached))) continue;
      gd.on("plotly_relayout", onRelayout);
      listening.set(gd, onRelayout);
    }
  };

  let timer;
  const observer = new MutationObserver(() => {
    clearTimeout(timer);
    timer = setTimeout(listen, 200);
  });
  observer.observe(document.body, { childList: true, subtree: true });
  listen();

  return () => {
    observer.disconnect();
    clearTimeout(timer);
    for (const [gd, listener] of listening) gd.removeListener && gd.removeListener("plotly_relayout", listener);
  };
}
