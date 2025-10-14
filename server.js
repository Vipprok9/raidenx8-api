// === MUSIC SEARCH & STREAM (Zing Style Test) ===
app.get("/music/search", (req, res) => {
  const q = (req.query.q || "").toString().trim();
  if (!q) return res.json({ items: [] });

  // Fake dữ liệu cho frontend hiển thị
  res.json({
    items: [
      { id: "demo1", title: `${q} (lofi remix)`, artist: "RaidenX8" },
      { id: "demo2", title: `${q} (live ver)`, artist: "Kim Thọ Chill" },
      { id: "demo3", title: `${q} (Zing Style)`, artist: "Aurora Neon" }
    ]
  });
});

// Stream giả để có nhạc nghe
app.get("/music/stream", (req, res) => {
  const id = (req.query.id || "").toString();
  if (!id) return res.status(400).send("Missing id");

  // Tạm redirect tới mp3 mẫu để test
  res.redirect(
    "https://file-examples.com/storage/fe0c2aaec97b4a8b9e0db02/2017/11/file_example_MP3_700KB.mp3"
  );
});
