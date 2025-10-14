import express from "express";
import cors from "cors";

const app = express();

const corsOrigins = (process.env.CORS_ORIGINS || "")
  .split(",")
  .map(s => s.trim())
  .filter(Boolean);

app.use(cors({ origin: corsOrigins.length ? corsOrigins : true }));
app.get("/", (_req, res) => res.send("RaidenX8 API is running"));

/** Fake search để frontend hoạt động ngay */
app.get("/music/search", (req, res) => {
  const q = (req.query.q || "").toString().trim();
  if (!q) return res.json({ items: [] });
  res.json({
    items: [
      { id: "demo1", title: `${q} (lofi remix)`, artist: "RaidenX8" },
      { id: "demo2", title: `${q} (live ver)`, artist: "Kim Thọ Chill" },
      { id: "demo3", title: `${q} (Zing Style)`, artist: "Aurora Neon" }
    ]
  });
});

/** Tạm thời stream 1 file mp3 mẫu để Play được */
app.get("/music/stream", (req, res) => {
  const id = (req.query.id || "").toString();
  if (!id) return res.status(400).send("Missing id");
  res.redirect("https://file-examples.com/storage/fe0c2aaec97b4a8b9e0db02/2017/11/file_example_MP3_700KB.mp3");
});

const port = process.env.PORT || 8080;
app.listen(port, () => console.log(`API on :${port}`));
