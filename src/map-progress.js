// Progress counts completed work, never an estimate of time remaining.
export function createMapProgress(root) {
  const tasks = new Map();
  const title = root.querySelector("[data-progress-title]");
  const detail = root.querySelector("[data-progress-detail]");
  const bar = root.querySelector('[role="progressbar"]');
  const fill = root.querySelector("[data-progress-fill]");
  let timer;
  function render() {
    const task = [...tasks.values()].sort(
      (a, b) => b.priority - a.priority || a.started - b.started,
    )[0];
    root.hidden = !task || performance.now() - task.started < 350;
    if (!task) {
      clearInterval(timer);
      timer = undefined;
      return;
    }
    title.textContent = task.label;
    const seconds = Math.floor((performance.now() - task.started) / 1000);
    detail.textContent = task.total
      ? `${task.done} of ${task.total} sections checked${task.pending.size ? " · " + [...task.pending][0] : ""}`
      : `${task.phase || "Waiting for results"}${seconds > 2 ? " · " + seconds + "s elapsed" : ""}`;
    bar.setAttribute("aria-label", task.label);
    bar.setAttribute("aria-valuetext", detail.textContent);
    root.classList.toggle("indeterminate", !task.total);
    if (task.total) {
      bar.setAttribute(
        "aria-valuenow",
        String(Math.round((task.done / task.total) * 100)),
      );
      fill.style.transform = `scaleX(${task.done / task.total})`;
    } else {
      bar.removeAttribute("aria-valuenow");
      fill.style.removeProperty("transform");
    }
  }
  return {
    begin(label, { total = 0, priority = 1 } = {}) {
      const key = Symbol(label);
      const task = {
        label,
        total,
        priority,
        started: performance.now(),
        done: 0,
        pending: new Set(),
        phase: "",
      };
      tasks.set(key, task);
      timer ??= setInterval(render, 150);
      render();
      return {
        phase(label) {
          task.phase = label;
          render();
        },
        track(promise, label) {
          task.pending.add(label);
          render();
          return Promise.resolve(promise).finally(() => {
            task.pending.delete(label);
            task.done += 1;
            render();
          });
        },
        end() {
          tasks.delete(key);
          render();
        },
      };
    },
  };
}
