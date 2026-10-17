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
  // Reference geometry reads as published context, deliberately cooler and
  // quieter than any observed-signal colour so it cannot be mistaken for one.
  reference: "#93a7b5",
  terminator: "#5f7280",
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
  reference: "RF",
  terminator: "DN",
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
      ctx.closePath();
      break;
    case "terminator":
      // Half-lit disc: the shaded half is night, never an observation.
      ctx.arc(0, 0, 10, 0, Math.PI * 2);
      break;
    case "reference":
      // Survey marker: a published fixed location, not a detected event.
      ctx.rect(-8, -8, 16, 16);
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
  if (category === "terminator") {
    // Shade the night half, then re-stroke the lit rim so the disc stays legible.
    ctx.beginPath();
    ctx.arc(0, 0, 10, Math.PI / 2, -Math.PI / 2);
    ctx.closePath();
    ctx.fillStyle = context ? "#14212a" : "#2b3b46";
    ctx.fill();
    ctx.strokeStyle = context ? tint : "#101b22";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, -10);
    ctx.lineTo(0, 10);
    ctx.stroke();
  }
  if (category === "reference") {
    // Corner ticks mark a surveyed coordinate rather than a measured value.
    ctx.strokeStyle = context ? tint : "#101b22";
    ctx.lineWidth = 1;
    for (const [x, y] of [
      [-8, -8],
      [8, -8],
      [8, 8],
      [-8, 8],
    ]) {
      ctx.beginPath();
      ctx.moveTo(x, y + (y < 0 ? 3 : -3));
      ctx.lineTo(x, y);
      ctx.lineTo(x + (x < 0 ? 3 : -3), y);
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
  } else if (category !== "terminator")
    // The terminator's half-lit disc is the whole symbol; lettering would cover it.
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

// Reference geometry is published context, so each kind gets its own pictogram
// rather than sharing one dot. Shape separates the layer; colour, where it is
// used, separates subtypes inside it.
export const REFERENCE_ICONS = {
  military: { color: "#9fb3c2" },
  naval: { color: "#8dc7da" },
  air: { color: "#e5b06a" },
  nuclear: { color: "#f0c05a" },
  spaceport: { color: "#c6bcff" },
  port: { color: "#8dc7da" },
  terminator: { color: "#5f7280" },
};

export function referenceCanvas(category, { color, size = 48 } = {}) {
  const tint = color || REFERENCE_ICONS[category]?.color || "#93a7b5";
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  canvas.className = "layer-symbol";
  canvas.setAttribute("aria-hidden", "true");
  const c = canvas.getContext("2d");
  c.scale(size / 24, size / 24);
  c.translate(12, 12);
  c.lineJoin = "round";
  c.lineCap = "round";

  const shield = () => {
    c.beginPath();
    c.moveTo(0, -10.5);
    c.lineTo(8.8, -6.6);
    c.lineTo(8.8, 1.4);
    c.quadraticCurveTo(8.8, 8.4, 0, 11);
    c.quadraticCurveTo(-8.8, 8.4, -8.8, 1.4);
    c.lineTo(-8.8, -6.6);
    c.closePath();
    c.fillStyle = tint;
    c.fill();
    c.strokeStyle = "#101b22";
    c.lineWidth = 1.1;
    c.stroke();
    // A chevron reads as defence without pretending to be an insignia.
    c.beginPath();
    c.moveTo(0, -4.4);
    c.lineTo(4.6, 0.4);
    c.lineTo(2.2, 0.4);
    c.lineTo(2.2, 5.2);
    c.lineTo(-2.2, 5.2);
    c.lineTo(-2.2, 0.4);
    c.lineTo(-4.6, 0.4);
    c.closePath();
    c.fillStyle = "#14212a";
    c.fill();
  };

  const trefoil = () => {
    // The standard radiation trefoil: three annular blades around a centre.
    for (let blade = 0; blade < 3; blade++) {
      const angle = -Math.PI / 2 + (blade * 2 * Math.PI) / 3;
      c.beginPath();
      c.arc(0, 0, 9.2, angle - 0.52, angle + 0.52);
      c.arc(0, 0, 3.1, angle + 0.52, angle - 0.52, true);
      c.closePath();
      c.fillStyle = tint;
      c.fill();
      c.strokeStyle = "#101b22";
      c.lineWidth = 0.9;
      c.stroke();
    }
    c.beginPath();
    c.arc(0, 0, 3.4, 0, Math.PI * 2);
    c.fillStyle = tint;
    c.fill();
    c.strokeStyle = "#101b22";
    c.lineWidth = 0.9;
    c.stroke();
  };

  const rocket = () => {
    c.beginPath();
    c.moveTo(0, -11);
    c.quadraticCurveTo(4.4, -6, 4.4, 1);
    c.lineTo(4.4, 6.4);
    c.lineTo(-4.4, 6.4);
    c.lineTo(-4.4, 1);
    c.quadraticCurveTo(-4.4, -6, 0, -11);
    c.closePath();
    c.fillStyle = tint;
    c.fill();
    c.strokeStyle = "#101b22";
    c.lineWidth = 1.1;
    c.stroke();
    c.beginPath();
    c.moveTo(-4.4, 2.2);
    c.lineTo(-8, 8.2);
    c.lineTo(-4.4, 6.4);
    c.moveTo(4.4, 2.2);
    c.lineTo(8, 8.2);
    c.lineTo(4.4, 6.4);
    c.closePath();
    c.fillStyle = tint;
    c.fill();
    c.strokeStyle = "#101b22";
    c.lineWidth = 1;
    c.stroke();
    c.beginPath();
    c.arc(0, -3.4, 2.1, 0, Math.PI * 2);
    c.fillStyle = "#14212a";
    c.fill();
  };

  const anchor = () => {
    c.strokeStyle = tint;
    c.lineWidth = 2.1;
    c.beginPath();
    c.arc(0, -8, 2.9, Math.PI * 0.15, Math.PI * 0.85, true);
    c.stroke();
    c.beginPath();
    c.moveTo(0, -5.4);
    c.lineTo(0, 8.6);
    c.moveTo(-6, -2.2);
    c.lineTo(6, -2.2);
    c.stroke();
    c.beginPath();
    c.arc(0, 1.6, 7.4, 0.28 * Math.PI, 0.72 * Math.PI);
    c.stroke();
    c.fillStyle = tint;
    for (const x of [-7.4, 7.4]) {
      c.beginPath();
      c.moveTo(x, 1.6 + 7.4 * Math.sin(0.28 * Math.PI));
      c.lineTo(x, 5.4);
      c.lineTo(x + (x < 0 ? -2.6 : 2.6), 2.4);
      c.closePath();
      c.fill();
    }
  };

  const terminatorGlyph = () => {
    c.beginPath();
    c.arc(0, 0, 9.6, 0, Math.PI * 2);
    c.fillStyle = tint;
    c.fill();
    c.strokeStyle = "#101b22";
    c.lineWidth = 1.1;
    c.stroke();
    // The night half is shaded; the lit half stays open to the basemap.
    c.beginPath();
    c.arc(0, 0, 9.6, Math.PI / 2, -Math.PI / 2);
    c.closePath();
    c.fillStyle = "#2b3b46";
    c.fill();
    c.beginPath();
    c.moveTo(0, -9.6);
    c.lineTo(0, 9.6);
    c.strokeStyle = tint;
    c.lineWidth = 1;
    c.stroke();
  };

  ({
    military: shield,
    naval: shield,
    air: shield,
    nuclear: trefoil,
    spaceport: rocket,
    port: anchor,
    terminator: terminatorGlyph,
  })[category]?.();
  return canvas;
}

export function referenceImage(category, options) {
  const canvas = referenceCanvas(category, options);
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
