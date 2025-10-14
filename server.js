// server.js
import express from "express";
import cors from "cors";
import { WebSocketServer } from "ws";
// Nếu dùng node < 18, cài thêm: npm i node-fetch
// import fetch from "node-fetch";

const app = express();
app.use(express.json());

// --- CORS: đọc từ biến môi trường CORS_ORIGINS (danh sách, ngăn cách bằng dấu phẩy) ---
const ALLOWED = (process.env.CORS_ORIGINS || "")
  .split(",")
  .map(s => s.trim())
  .filter(Boolean);

app.use(cors({
  origin: (origin, cb) => {
    if (!origin || ALLOWED.length === 0) return cb(null, true);
    const ok = ALLOWED.some(pat => {
      if (pat.includes("*")) {
        // *.vercel.app -> regex
        const re = new RegExp("^" + pat.replace(/\./g, "\\.").replace(/\*/g, ".*") + "$");
        return re.test(origin);
      }
      return pat === origin;
    });
    return ok ? cb(null, true) : cb(new Error("Not allowed by CORS"));
  },
  credentials: true
}));

// --- Health check cho Render ---
app.get("/health", (_req, res) => res.status(200).send("ok"));

// --- Demo API (giữ chỗ): Zing-style search/stream ---
app.get("/music/search", async (req, res) => {
  const q = (req.query.q || "").toString().trim();
  if (!q) return res.json({ items: [] });
  // TODO: gọi backend thật của bạn ở đây
  // res.json({ items: [{ id: "demo-1", title: `Kết quả cho ${q}`, artist: "Demo" }] });
  res.json({ items: [] });
});

app.get("/music/stream", async (req, res) => {
  const id = (req.query.id || "").toString();
  if (!id) return res.status(400).send("missing id");
  // TODO: pipe stream thật ở đây
  res.status(501).send("stream not implemented");
});

// --- Khởi động server đúng PORT Render cấp + 0.0.0.0 ---
const PORT = process.env.PORT || 3000;
const server = app.listen(PORT, "0.0.0.0", () => {
  console.log("Server listening on", PORT);
});

// --- WebSocket (giữ chỗ), Render reuses same server ---
const wss = new WebSocketServer({ server, path: "/ws" });
wss.on("connection", ws => {
  ws.send(JSON.stringify({ from: "system", text: "connected ✨" }));
  ws.on("message", msg => {
    // echo đơn giản
    ws.send(JSON.stringify({ from: "ai", text: `Bạn nói: ${msg}` }));
  });
});
