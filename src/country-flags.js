// Local flag graphics render consistently without emoji fonts or network calls.
export function drawCountryFlag(ctx, code, x, y, width = 18, height = 12) {
  ctx.save();
  ctx.translate(x, y);
  ctx.scale(width / 18, height / 12);
  const rect = (color, x, y, w, h) => {
    ctx.fillStyle = color;
    ctx.fillRect(x, y, w, h);
  };
  const circle = (color, x, y, r) => {
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
  };
  const star = (color, x, y, r) => {
    ctx.fillStyle = color;
    ctx.beginPath();
    for (let i = 0; i < 10; i++) {
      const a = (i * Math.PI) / 5 - Math.PI / 2,
        radius = i % 2 ? r * 0.4 : r;
      ctx.lineTo(x + Math.cos(a) * radius, y + Math.sin(a) * radius);
    }
    ctx.closePath();
    ctx.fill();
  };
  rect("#fff", 0, 0, 18, 12);
  if (code === "US") {
    for (let i = 0; i < 13; i += 2)
      rect("#b22234", 0, (i * 12) / 13, 18, 12 / 13);
    rect("#3c3b6e", 0, 0, 8, (12 * 7) / 13);
    for (let row = 0; row < 9; row++)
      for (let col = 0; col < (row % 2 ? 5 : 6); col++)
        star(
          "#fff",
          0.7 + col * 1.3 + (row % 2 ? 0.65 : 0),
          0.4 + row * 0.64,
          0.28,
        );
  } else if (code === "GB") {
    rect("#012169", 0, 0, 18, 12);
    const cross = (color, thickness) => {
      ctx.strokeStyle = color;
      ctx.lineWidth = thickness;
      ctx.beginPath();
      ctx.moveTo(0, 0);
      ctx.lineTo(18, 12);
      ctx.moveTo(18, 0);
      ctx.lineTo(0, 12);
      ctx.stroke();
    };
    ctx.beginPath();
    ctx.rect(0, 0, 18, 12);
    ctx.clip();
    cross("#fff", 3);
    cross("#c8102e", 1);
    rect("#fff", 0, 4, 18, 4);
    rect("#fff", 7, 0, 4, 12);
    rect("#c8102e", 0, 4.8, 18, 2.4);
    rect("#c8102e", 7.8, 0, 2.4, 12);
  } else if (["DE", "RU", "IN", "AR"].includes(code)) {
    const bands = {
      DE: ["#111", "#dd0000", "#ffce00"],
      RU: ["#fff", "#0039a6", "#d52b1e"],
      IN: ["#ff9933", "#fff", "#138808"],
      AR: ["#74acdf", "#fff", "#74acdf"],
    }[code];
    bands.forEach((color, i) => rect(color, 0, i * 4, 18, 4));
    if (code === "IN") {
      ctx.strokeStyle = "#000080";
      ctx.lineWidth = 0.22;
      ctx.beginPath();
      ctx.arc(9, 6, 1.5, 0, Math.PI * 2);
      ctx.stroke();
      for (let i = 0; i < 24; i++) {
        const a = (i * Math.PI) / 12;
        ctx.beginPath();
        ctx.moveTo(9, 6);
        ctx.lineTo(9 + Math.cos(a) * 1.5, 6 + Math.sin(a) * 1.5);
        ctx.stroke();
      }
    }
    if (code === "AR") circle("#f6b40e", 9, 6, 1.1);
  } else if (["FR", "IT", "CA"].includes(code)) {
    const bands = {
      FR: ["#002395", "#fff", "#ed2939"],
      IT: ["#009246", "#fff", "#ce2b37"],
      CA: ["#d80621", "#fff", "#d80621"],
    }[code];
    if (code === "CA") {
      rect(bands[0], 0, 0, 4.5, 12);
      rect(bands[2], 13.5, 0, 4.5, 12);
      ctx.fillStyle = bands[0];
      ctx.fill(
        new Path2D(
          "M9 2 L10 4.5 L11 4 L10.7 6 L12.4 5.3 L12 7 L13 7.5 L10 9 L10.2 10 L9.2 9.8 L9.2 11 L8.8 11 L8.8 9.8 L7.8 10 L8 9 L5 7.5 L6 7 L5.6 5.3 L7.3 6 L7 4 L8 4.5 Z",
        ),
      );
    } else bands.forEach((color, i) => rect(color, i * 6, 0, 6, 12));
  } else if (code === "JP") circle("#bc002d", 9, 6, 3.2);
  else if (code === "CN") {
    rect("#de2910", 0, 0, 18, 12);
    star("#ffde00", 3, 3, 1.7);
    for (const [x, y] of [
      [5.5, 1.2],
      [6.4, 2.5],
      [6.4, 4],
      [5.5, 5.2],
    ])
      star("#ffde00", x, y, 0.6);
  } else if (code === "ID") rect("#ce1126", 0, 0, 18, 6);
  else if (code === "QA") {
    rect("#8a1538", 0, 0, 18, 12);
    rect("#fff", 0, 0, 5.5, 12);
    ctx.fillStyle = "#fff";
    ctx.beginPath();
    ctx.moveTo(5.5, 0);
    for (let i = 0; i < 9; i++) {
      ctx.lineTo(7, ((i + 0.5) * 12) / 9);
      ctx.lineTo(5.5, ((i + 1) * 12) / 9);
    }
    ctx.closePath();
    ctx.fill();
  } else {
    // Multinational programmes use a globe; unidentified origins use a question mark.
    rect("#213846", 0, 0, 18, 12);
    ctx.strokeStyle = "#9ac6d2";
    ctx.lineWidth = 0.8;
    if (code === "INT") {
      ctx.beginPath();
      ctx.arc(9, 6, 4.5, 0, Math.PI * 2);
      ctx.stroke();
      ctx.beginPath();
      ctx.ellipse(9, 6, 2.2, 4.5, 0, 0, Math.PI * 2);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(4.5, 6);
      ctx.lineTo(13.5, 6);
      ctx.stroke();
    } else {
      ctx.fillStyle = "#c2d1d9";
      ctx.font = "bold 10px Arial";
      ctx.textAlign = "center";
      ctx.fillText("?", 9, 10);
    }
  }
  ctx.restore();
}

const flagImages = new Map();
export function countryFlagImage(code, label) {
  if (!flagImages.has(code)) {
    const canvas = document.createElement("canvas");
    canvas.width = 36;
    canvas.height = 24;
    drawCountryFlag(canvas.getContext("2d"), code, 0, 0, 36, 24);
    flagImages.set(code, canvas.toDataURL());
  }
  const image = document.createElement("img");
  image.src = flagImages.get(code);
  image.width = 18;
  image.height = 12;
  image.className = "orbital-country-flag";
  image.alt = label;
  image.title = label;
  return image;
}
