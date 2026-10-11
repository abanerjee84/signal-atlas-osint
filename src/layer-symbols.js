// One visual vocabulary for map markers, layer switches and the map key.
export const colors = {
  geopolitical: "#dcad73",
  military: "#d88f89",
  aviation: "#ffdf38",
  maritime: "#8dc7da",
  sentiment: "#79c69f",
  cyber: "#b2a3db",
  threat: "#ef8ca2",
  economic: "#e4cc8a",
  environment: "#79c9b1",
  analysis: "#a2b1bc",
};
export const CATEGORY_NAMES = {
  geopolitical: "Geopolitical events",
  military: "Military OSINT",
  aviation: "Aviation",
  maritime: "Maritime",
  sentiment: "Global sentiment",
  cyber: "Cyber intelligence",
  threat: "Threat Actor",
  economic: "Economic and energy",
  environment: "Environment and humanitarian",
  analysis: "Analysis and anomaly alerts",
};
const marks = {
  geopolitical: "GP",
  military: "MI",
  aviation: "✈",
  maritime: "MT",
  sentiment: "S",
  cyber: "CY",
  threat: "TA",
  economic: "EC",
  environment: "EN",
  analysis: "AN",
  mixed: "+",
  publisher: "P",
};

export function symbolCanvas(category, { context = false, count, color } = {}) {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = count ? 64 : 48;
  canvas.className = "layer-symbol";
  canvas.setAttribute("aria-hidden", "true");
  const ctx = canvas.getContext("2d");
  ctx.scale(2, 2);
  ctx.translate(count ? 13 : 12, count ? 16 : 12);
  ctx.beginPath();
  switch (category) {
    case "geopolitical":
      for (const [x, y] of [
        [-5, -10],
        [5, -10],
        [10, 0],
        [5, 10],
        [-5, 10],
        [-10, 0],
      ])
        ctx.lineTo(x, y);
      break;
    case "threat":
    case "military":
      ctx.moveTo(-9, -9);
      ctx.lineTo(9, -9);
      ctx.lineTo(8, 3);
      ctx.quadraticCurveTo(6, 8, 0, 11);
      ctx.quadraticCurveTo(-6, 8, -8, 3);
      break;
    case "maritime":
      ctx.moveTo(-9, -9);
      ctx.lineTo(9, -9);
      ctx.lineTo(9, 3);
      ctx.lineTo(5, 9);
      ctx.lineTo(-5, 9);
      ctx.lineTo(-9, 3);
      break;
    case "sentiment":
      ctx.roundRect(-10, -9, 20, 16, 4);
      ctx.moveTo(-5, 6);
      ctx.lineTo(-7, 11);
      ctx.lineTo(2, 6);
      break;
    case "economic":
      ctx.moveTo(0, -11);
      ctx.lineTo(11, 0);
      ctx.lineTo(0, 11);
      ctx.lineTo(-11, 0);
      break;
    case "environment":
      ctx.moveTo(-9, 8);
      ctx.quadraticCurveTo(-14, -10, 9, -10);
      ctx.quadraticCurveTo(14, 10, -9, 8);
      break;
    case "analysis":
      ctx.moveTo(0, -11);
      ctx.lineTo(11, 9);
      ctx.lineTo(-11, 9);
      break;
    default:
      ctx.roundRect(-9, -9, 18, 18, 2);
  }
  ctx.closePath();
  const tint = color || colors[category] || "#bccbd3";
  ctx.fillStyle = context ? "#14212a" : tint;
  ctx.fill();
  ctx.strokeStyle = context ? tint : "#101b22";
  ctx.lineWidth = context ? 1.4 : 1.1;
  if (context) ctx.setLineDash([2, 1.5]);
  ctx.stroke();
  ctx.setLineDash([]);
  if (category === "cyber") {
    ctx.strokeStyle = tint;
    ctx.lineWidth = 1.3;
    for (const n of [-5, 0, 5]) {
      ctx.beginPath();
      ctx.moveTo(n, -12);
      ctx.lineTo(n, -9);
      ctx.moveTo(n, 9);
      ctx.lineTo(n, 12);
      ctx.moveTo(-12, n);
      ctx.lineTo(-9, n);
      ctx.moveTo(9, n);
      ctx.lineTo(12, n);
      ctx.stroke();
    }
  }
  ctx.fillStyle = context ? tint : "#101b22";
  ctx.font = `700 ${category === "analysis" ? 6.5 : 7.5}px Segoe UI, Arial, sans-serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(marks[category] || "?", 0, category === "analysis" ? 3 : -0.2);
  if (count) {
    ctx.fillStyle = "#14212a";
    ctx.strokeStyle = tint;
    ctx.lineWidth = 0.8;
    ctx.beginPath();
    ctx.roundRect(2, -15, 16, 11, 3);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = "#eef4f6";
    ctx.font = "700 6.5px Segoe UI, Arial, sans-serif";
    ctx.fillText(String(count), 10, -9.4);
  }
  return canvas;
}

export function symbolImage(category, options) {
  const canvas = symbolCanvas(category, options);
  return canvas
    .getContext("2d")
    .getImageData(0, 0, canvas.width, canvas.height);
}
