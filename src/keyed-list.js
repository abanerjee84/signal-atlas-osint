// Move only changed rows; retain focused buttons and measured row heights.
export function reconcileList(parent, rows) {
  const retained = new Set(rows);
  for (const child of [...parent.children])
    if (!retained.has(child)) child.remove();
  let cursor = parent.firstElementChild;
  for (const row of rows) {
    if (row === cursor) cursor = cursor.nextElementSibling;
    else parent.insertBefore(row, cursor);
  }
}
