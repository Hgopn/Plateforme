console.log("MARBLE.JS chargé (Neo Tube)");

document.addEventListener("DOMContentLoaded", () => {
  const canvas = document.getElementById("marble-canvas");
  const ctx = canvas.getContext("2d");

  const W = canvas.width;
  const H = canvas.height;

  // ==========================
  // PARAMÈTRES DU TUBE
  // ==========================
  const tube = {
    centerX: W / 2,
    innerWidth: 220,   // largeur "jouable"
    outerWidth: 320,   // pour le glow
    topPadding: 40,
    bottomPadding: 40
  };

  // ==========================
  // BILLES
  // ==========================
  const marbles = [
    {
      id: "gifts",
      color: "#ff6bd5",
      glow: "rgba(255,107,213,0.9)",
      xOffset: -40,    // légèrement à gauche
      y: 60,
      speed: 90,       // px / seconde
      radius: 12
    },
    {
      id: "likes",
      color: "#00d4ff",
      glow: "rgba(0,212,255,0.9)",
      xOffset: 40,     // légèrement à droite
      y: 30,
      speed: 100,
      radius: 12
    }
  ];

  // ==========================
  // OBSTACLES LUMINEUX
  // ==========================
  const obstacles = [];
  const OBSTACLE_COUNT = 10;

  function randomBetween(min, max) {
    return min + Math.random() * (max - min);
  }

  function createObstacle(initialY) {
    return {
      y: initialY,
      thickness: randomBetween(8, 16),
      gap: randomBetween(80, 140),   // "Trou" dans le tube
      tilt: randomBetween(-0.25, 0.25), // inclinaison
      hue: randomBetween(180, 320)
    };
  }

  // créer une pile d'obstacles sur toute la hauteur
  for (let i = 0; i < OBSTACLE_COUNT; i++) {
    obstacles.push(createObstacle(randomBetween(-H, H)));
  }

  // ==========================
  // BACKGROUND GALAXIE
  // ==========================
  function drawBackground() {
    // fond dégradé
    const g = ctx.createLinearGradient(0, 0, 0, H);
    g.addColorStop(0, "#050014");
    g.addColorStop(0.4, "#090822");
    g.addColorStop(1, "#020006");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, W, H);

    // quelques "étoiles"
    ctx.save();
    ctx.globalAlpha = 0.6;
    for (let i = 0; i < 40; i++) {
      const x = Math.random() * W;
      const y = Math.random() * H;
      const r = Math.random() * 1.4;
      ctx.fillStyle = "rgba(255,255,255,0.7)";
      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }

  // ==========================
  // TUBE FUTURISTE
  // ==========================
  function drawTube() {
    const cx = tube.centerX;
    const iw = tube.innerWidth;
    const ow = tube.outerWidth;

    // Glow externe
    const gOuter = ctx.createLinearGradient(cx - ow / 2, 0, cx + ow / 2, 0);
    gOuter.addColorStop(0, "rgba(0,255,255,0)");
    gOuter.addColorStop(0.3, "rgba(0,255,255,0.20)");
    gOuter.addColorStop(0.5, "rgba(138,43,226,0.45)");
    gOuter.addColorStop(0.7, "rgba(0,255,255,0.20)");
    gOuter.addColorStop(1, "rgba(0,255,255,0)");

    ctx.save();
    ctx.globalCompositeOperation = "screen";
    ctx.fillStyle = gOuter;
    ctx.fillRect(cx - ow / 2, tube.topPadding, ow, H - tube.topPadding - tube.bottomPadding);
    ctx.restore();

    // Corps du tube
    const gInner = ctx.createLinearGradient(cx - iw / 2, 0, cx + iw / 2, 0);
    gInner.addColorStop(0, "#05020c");
    gInner.addColorStop(0.48, "#04001f");
    gInner.addColorStop(0.52, "#04001f");
    gInner.addColorStop(1, "#05020c");

    ctx.save();
    ctx.fillStyle = gInner;
    ctx.strokeStyle = "rgba(255,255,255,0.12)";
    ctx.lineWidth = 2;

    const top = tube.topPadding;
    const bottom = H - tube.bottomPadding;
    const radius = 60;

    ctx.beginPath();
    ctx.moveTo(cx - iw / 2, top + radius);
    ctx.quadraticCurveTo(cx - iw / 2, top, cx - iw / 2 + radius, top);
    ctx.lineTo(cx + iw / 2 - radius, top);
    ctx.quadraticCurveTo(cx + iw / 2, top, cx + iw / 2, top + radius);
    ctx.lineTo(cx + iw / 2, bottom - radius);
    ctx.quadraticCurveTo(cx + iw / 2, bottom, cx + iw / 2 - radius, bottom);
    ctx.lineTo(cx - iw / 2 + radius, bottom);
    ctx.quadraticCurveTo(cx - iw / 2, bottom, cx - iw / 2, bottom - radius);
    ctx.closePath();

    ctx.fill();
    ctx.stroke();
    ctx.restore();

    // Lignes "néon" verticales
    ctx.save();
    ctx.globalAlpha = 0.3;
    ctx.strokeStyle = "rgba(0,255,255,0.5)";
    ctx.lineWidth = 1;
    ctx.setLineDash([10, 12]);

    ctx.beginPath();
    ctx.moveTo(cx - iw / 4, top + 10);
    ctx.lineTo(cx - iw / 4, bottom - 10);
    ctx.stroke();

    ctx.beginPath();
    ctx.moveTo(cx + iw / 4, top + 10);
    ctx.lineTo(cx + iw / 4, bottom - 10);
    ctx.stroke();

    ctx.restore();
  }

  // ==========================
  // OBSTACLES
  // ==========================
  function drawObstacles(dt) {
    const cx = tube.centerX;
    const iw = tube.innerWidth;
    const speed = 80; // vitesse vers le bas

    obstacles.forEach((obs) => {
      // Met à jour la position
      obs.y += speed * dt;
      if (obs.y > H + 50) {
        // on recycle l'obstacle au-dessus
        obs.y = -randomBetween(50, 250);
        obs.thickness = randomBetween(8, 16);
        obs.gap = randomBetween(80, 140);
        obs.tilt = randomBetween(-0.25, 0.25);
        obs.hue = randomBetween(180, 320);
      }

      const halfWidth = (iw - obs.gap) / 2;

      ctx.save();
      ctx.translate(cx, obs.y);
      ctx.rotate(obs.tilt);

      const color = `hsl(${obs.hue}, 85%, 60%)`;
      const glow = `hsla(${obs.hue}, 90%, 65%, 0.8)`;

      ctx.shadowColor = glow;
      ctx.shadowBlur = 18;
      ctx.fillStyle = color;

      // barres gauche et droite
      const t = obs.thickness;
      ctx.fillRect(-iw / 2, -t / 2, halfWidth, t);
      ctx.fillRect(iw / 2 - halfWidth, -t / 2, halfWidth, t);

      ctx.restore();
    });
  }

  // ==========================
  // BILLES
  // ==========================
  function drawMarbles(dt) {
    const cx = tube.centerX;

    marbles.forEach((m) => {
      // Mise à jour de la position (descente)
      m.y += m.speed * dt;
      if (m.y > H - tube.bottomPadding - 20) {
        m.y = tube.topPadding + 20 + Math.random() * 60;
      }

      // Calcul de la position dans le tube
      const x = cx + m.xOffset;
      const y = m.y;

      ctx.save();
      ctx.beginPath();
      const g = ctx.createRadialGradient(x - 4, y - 4, 2, x, y, m.radius + 6);
      g.addColorStop(0, "#ffffff");
      g.addColorStop(0.3, m.color);
      g.addColorStop(1, "rgba(0,0,0,0)");

      ctx.fillStyle = g;
      ctx.arc(x, y, m.radius, 0, Math.PI * 2);
      ctx.shadowColor = m.glow;
      ctx.shadowBlur = 18;
      ctx.fill();
      ctx.restore();
    });
  }

  // ==========================
  // BOUCLE D'ANIMATION
  // ==========================
  let lastTime = performance.now();

  function loop(now) {
    const dt = Math.min((now - lastTime) / 1000, 0.03); // clamp dt
    lastTime = now;

    drawBackground();
    drawTube();
    drawObstacles(dt);
    drawMarbles(dt);

    requestAnimationFrame(loop);
  }

  requestAnimationFrame(loop);
});
