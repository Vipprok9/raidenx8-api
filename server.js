// === RAIDENX8 API v22.x — Full Music + WS Demo ===
// ES Module (Node 18+)

import express from "express";
import cors from "cors";
import { WebSocketServer } from "ws";

// --- APP BASE ---
const app = express();

// Cấu hình CORS động (Render ENV)
const allowList = (process.env.CORS_ORIGINS || "")
  .split(",")
  .map(s => s.trim())
  .filter(Boolean);
app.use(cors({
  origin: (origin, cb) => {
    if (!origin || allowList.length === 0 || allowList.includes(origin)) return cb(null, true);
    return cb(new Error("Not allowed by CORS"));
  }
}));

app.use(express.json());

// --- ROUTES CƠ BẢN ---
app.get("/", (req, res) => {
  res.json({ ok: true, name: "RaidenX8 API", time: Date.now() });
});
app.get("/health", (req, res) => res.send("OK"));

// --- MUSIC SEARCH & STREAM (Zing Style mock) ---
app.get("/music/search", (req, res) => {
  const q = (req.query.q || "").toString().trim();
  if (!q) return res.json({ items: [] });

  // fake list hiển thị bên frontend
  res.json({
    items: [
      { id: "demo1", title: `${q} (Lofi)`, artist: "RaidenX8" },
      { id: "demo2", title: `${q} (Remix)`, artist: "Zing Proxy" },
      { id: "demo3", title: `${q} (Acoustic)`, artist: "AI Music" }
    ]
  });
});

// Stream thử để frontend Play được
app.get("/music/stream", (req, res) => {
  const id = (req.query.id || "").toString();
  if (!id) return res.status(400).send("Missing id");
  // redirect tới mp3 mẫu online
  res.redirect("https://file-examples.com/storage/fe3d4d3e1df/example.mp3");
});

// --- WEBSOCKET DEMO ---
const PORT = process.env.PORT || 8080;
const server = app.listen(PORT, () =>
  console.log(`✅ RaidenX8 API running on port ${PORT}`)
);

const wss = new WebSocketServer({ server, path: "/ws" });
wss.on("connection", (ws) => {
  console.log("⚡ WebSocket connected");
  ws.send(JSON.stringify({ from: "server", text: "🎧 Welcome to RaidenX8 Realtime" }));

  ws.on("message", (msg) => {
    console.log("💬 WS message:", msg.toString());
    ws.send(JSON.stringify({ echo: msg.toString() }));
  });
});

// --- ERROR HANDLER ---
process.on("uncaughtException", (err) => {
  console.error("🔥 Uncaught error:", err);
});
