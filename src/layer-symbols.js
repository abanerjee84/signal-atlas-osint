// One visual vocabulary for map markers, layer switches and the map key.
export const colors = {
  geopolitical: "#dcad73",
  military: "#d88f89",
  aviation: "#ffdf38",
  maritime: "#8dc7da",
  sentiment: "#79c69f",
  cyber: "#b2a3db",
  infrastructure: "#65dfc5",
  threat: "#ef8ca2",
  economic: "#e4cc8a",
  environment: "#79c9b1",
  analysis: "#a2b1bc",
  space: "#c6bcff",
};
export const CATEGORY_NAMES = {
  geopolitical: "Geopolitical events",
  military: "Military OSINT",
  aviation: "Aviation",
  maritime: "Maritime",
  sentiment: "Global sentiment",
  cyber: "Cyber: Threat Actors",
  infrastructure: "Cyber infrastructure",
  threat: "Cyber: Threat Actors — attack report / detection",
  economic: "Economic and energy",
  environment: "Environment and humanitarian",
  analysis: "Reporting signals & alerts",
  space: "Satellites & ISS",
};
const marks = {
  geopolitical: "GP",
  military: "MI",
  aviation: "✈",
  maritime: "MT",
  sentiment: "S",
  cyber: "CY",
  infrastructure: "CI",
  threat: "TA",
  economic: "EC",
  environment: "EN",
  analysis: "AN",
  mixed: "+",
  publisher: "P",
  attacker: "A",
  victim: "V",
  space: "ST",
};

// Activity colors belong to the military glyphs, never the map or defence links.
// General reporting stays neutral; a country mention is not combat evidence.
const militaryIconColors = {
  alert: "#ffd166",
  drone: "#ffae62",
  airstrike: "#ff857b",
  missile: "#ffae62",
  shelling: "#ffae62",
  explosion: "#ff857b",
  clashes: "#ff857b",
  naval: "#70c6f2",
  deployment: "#dcbf7e",
  weapons: "#dcbf7e",
  diplomacy: "#76d6b0",
  protest: "#ffd166",
  conflict: "#ff7474",
};
export function conflictColor(type, category) {
  return category === "military"
    ? militaryIconColors[type] || "#b6c3cc"
    : colors[category];
}

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
    case "infrastructure":
      ctx.roundRect(-10, -10, 20, 20, 3);
      break;
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
    case "military":
      ctx.moveTo(-3, -2);
      ctx.lineTo(3, -2);
      ctx.lineTo(2, 5);
      ctx.lineTo(0, 10);
      ctx.lineTo(-2, 5);
      break;
    case "threat":
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
  const tint =
    color ||
    (category === "military"
      ? conflictColor("conflict", category)
      : colors[category]) ||
    "#bccbd3";
  ctx.fillStyle = category === "military" ? tint : context ? "#14212a" : tint;
  ctx.fill();
  ctx.strokeStyle = context || category === "military" ? tint : "#101b22";
  ctx.lineWidth = category === "military" ? 1.8 : context ? 1.4 : 1.1;
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
  if (category === "infrastructure") {
    ctx.strokeStyle = context ? tint : "#101b22";
    ctx.lineWidth = 1;
    for (const y of [-6, 6]) {
      ctx.beginPath();
      ctx.moveTo(-7, y);
      ctx.lineTo(7, y);
      ctx.stroke();
    }
  }
  ctx.fillStyle = context ? tint : "#101b22";
  ctx.font = `700 ${category === "analysis" ? 6.5 : 7.5}px Segoe UI, Arial, sans-serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  if (category === "military") {
    ctx.strokeStyle = tint;
    ctx.fillStyle = tint;
    ctx.fillRect(-7, -4, 14, 2);
    ctx.fillRect(-1.5, -10, 3, 6);
  } else
    ctx.fillText(marks[category] || "?", 0, category === "analysis" ? 3 : -0.2);
  if (count) {
    ctx.fillStyle = "#14212a";
    ctx.strokeStyle = tint;
    ctx.lineWidth = 0.8;
    ctx.beginPath();
    ctx.roundRect(
      2,
      -15,
      category === "military" ? 17 : 16,
      category === "military" ? 12 : 11,
      3,
    );
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = "#eef4f6";
    ctx.font = `700 ${category === "military" ? 8 : 6.5}px Segoe UI, Arial, sans-serif`;
    ctx.fillText(
      String(count),
      category === "military" ? 10.5 : 10,
      category === "military" ? -9 : -9.4,
    );
  }
  return canvas;
}

export function symbolImage(category, options) {
  const canvas = symbolCanvas(category, options);
  return canvas
    .getContext("2d")
    .getImageData(0, 0, canvas.width, canvas.height);
}

// Small, drawn pictograms remain legible without platform-specific emoji fonts.
export function conflictIcon(
  type,
  color,
  context = false,
  count = null,
  emphasis = false,
) {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = count ? 64 : 48;
  const c = canvas.getContext("2d");
  c.scale(2, 2);
  c.translate(12, 12);
  c.lineWidth = emphasis ? 1 : 1.6;
  c.lineCap = "round";
  c.lineJoin = "round";
  c.fillStyle = context ? "#14212a" : color;
  c.strokeStyle = color;
  c.beginPath();
  c.arc(0, 0, 10.5, 0, Math.PI * 2);
  c.fillStyle = "#14212a";
  c.fill();
  if (context) c.setLineDash([2, 2]);
  c.stroke();
  c.setLineDash([]);
  c.lineWidth = emphasis ? 2 : 1.6;
  c.fillStyle = color;
  const line = (points) => {
    c.beginPath();
    points.forEach(([x, y], i) => (i ? c.lineTo(x, y) : c.moveTo(x, y)));
    c.stroke();
  };
  const circle = (x, y, r) => {
    c.beginPath();
    c.arc(x, y, r, 0, Math.PI * 2);
    c.stroke();
  };
  switch (type) {
    case "drone":
      line([
        [-5, -5],
        [5, 5],
      ]);
      line([
        [5, -5],
        [-5, 5],
      ]);
      for (const x of [-5, 5]) for (const y of [-5, 5]) circle(x, y, 2.2);
      circle(0, 0, 1.5);
      break;
    case "airstrike":
      line([
        [0, -7],
        [0, 0],
        [-6, 2],
        [0, 1],
        [6, 2],
        [0, 0],
      ]);
      line([
        [0, 3],
        [0, 7],
      ]);
      line([
        [-3, 5],
        [0, 7],
        [3, 5],
      ]);
      break;
    case "missile":
      line([
        [-4, 5],
        [-2, -3],
        [3, -7],
        [6, -2],
        [1, 5],
        [-4, 5],
      ]);
      line([
        [-4, 5],
        [-6, 7],
      ]);
      line([
        [0, 5],
        [-1, 8],
      ]);
      break;
    case "explosion":
      circle(-1, 2, 4.5);
      line([
        [2, -2],
        [4, -5],
        [6, -5],
      ]);
      line([
        [5, -7],
        [6, -6],
        [8, -6],
      ]);
      break;
    case "alert":
      line([
        [-6, 6],
        [6, 6],
      ]);
      line([
        [-4, 4],
        [-4, 0],
        [-2, -3],
        [2, -3],
        [4, 0],
        [4, 4],
        [-4, 4],
      ]);
      line([
        [0, -5],
        [0, -8],
      ]);
      line([
        [-6, -3],
        [-8, -5],
      ]);
      line([
        [6, -3],
        [8, -5],
      ]);
      break;
    case "shelling":
      circle(-3, 5, 2);
      circle(4, 5, 2);
      line([
        [-6, 3],
        [5, 3],
        [5, 0],
        [-3, 0],
        [-6, 3],
      ]);
      line([
        [-1, 0],
        [7, -6],
      ]);
      break;
    case "clashes":
      line([
        [-6, -7],
        [6, 6],
      ]);
      line([
        [6, -7],
        [-6, 6],
      ]);
      line([
        [-7, 3],
        [-3, 7],
      ]);
      line([
        [3, 7],
        [7, 3],
      ]);
      break;
    case "naval":
      line([
        [0, -6],
        [0, 6],
      ]);
      circle(0, -6, 1.8);
      line([
        [-6, 1],
        [-6, 4],
        [0, 7],
        [6, 4],
        [6, 1],
      ]);
      line([
        [-3, -2],
        [3, -2],
      ]);
      break;
    case "deployment":
      // Troop movement, rather than a tank inferred from a deployment report.
      circle(-3, -4, 2);
      line([
        [-7, 4],
        [-6, 0],
        [0, 0],
        [1, 4],
      ]);
      line([
        [2, -2],
        [7, -2],
        [5, -5],
      ]);
      line([
        [7, -2],
        [5, 1],
      ]);
      line([
        [-5, 5],
        [-5, 7],
      ]);
      line([
        [-1, 5],
        [-1, 7],
      ]);
      break;
    case "weapons":
      // Equipment crate: procurement and supplies do not imply a strike.
      c.strokeRect(-7, -4, 14, 11);
      line([
        [-7, -1],
        [7, -1],
      ]);
      line([
        [-3, -4],
        [-3, 7],
      ]);
      line([
        [3, -4],
        [3, 7],
      ]);
      line([
        [-3, -4],
        [-3, -7],
        [3, -7],
        [3, -4],
      ]);
      break;
    case "diplomacy":
      line([
        [0, 7],
        [0, -7],
        [7, -5],
        [0, -2],
      ]);
      line([
        [-6, 6],
        [-6, -3],
        [-1, -1],
      ]);
      break;
    case "protest":
      c.strokeRect(-7, -7, 14, 9);
      line([
        [0, 2],
        [0, 8],
      ]);
      line([
        [-3, -3],
        [3, -3],
      ]);
      break;
    case "security":
      line([
        [-6, -6],
        [6, -6],
        [5, 3],
        [0, 7],
        [-5, 3],
        [-6, -6],
      ]);
      line([
        [0, -3],
        [0, 1],
      ]);
      circle(0, 4, 0.5);
      break;
    default:
      if (emphasis) {
        // The layer's dagger identifies military reporting; it is not an incident claim.
        c.beginPath();
        c.moveTo(-2.5, -1);
        c.lineTo(2.5, -1);
        c.lineTo(1.5, 4);
        c.lineTo(0, 8);
        c.lineTo(-1.5, 4);
        c.closePath();
        c.fill();
        c.fillRect(-6, -3, 12, 2);
        c.fillRect(-1.2, -8, 2.4, 5);
      } else {
        // Other unspecified reporting retains a neutral document.
        line([
          [-5, -7],
          [2, -7],
          [6, -3],
          [6, 7],
          [-5, 7],
          [-5, -7],
        ]);
        line([
          [2, -7],
          [2, -3],
          [6, -3],
        ]);
        line([
          [-2, 0],
          [3, 0],
        ]);
        line([
          [-2, 4],
          [3, 4],
        ]);
      }
  }
  if (count) {
    c.fillStyle = "#14212a";
    c.beginPath();
    c.roundRect(2, -12, 17, 10, 2);
    c.fill();
    c.stroke();
    c.fillStyle = "#eef4f6";
    c.font = "700 6.5px Segoe UI, Arial, sans-serif";
    c.textAlign = "center";
    c.textBaseline = "middle";
    c.fillText(String(count), 10.5, -7);
  }
  return c.getImageData(0, 0, canvas.width, canvas.height);
}

export function conflictCanvas(type, category, context = false) {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 48;
  canvas.className = "layer-symbol";
  canvas.setAttribute("aria-hidden", "true");
  canvas
    .getContext("2d")
    .putImageData(
      conflictIcon(
        type,
        conflictColor(type, category),
        context,
        null,
        category === "military",
      ),
      0,
      0,
    );
  return canvas;
}
