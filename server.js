import 'dotenv/config';
import express from 'express';
import cors from 'cors';
import rateLimit from 'express-rate-limit';
import morgan from 'morgan';
import { ZingMp3 } from 'zingmp3-api-full';

const app = express();
app.set('trust proxy', 1);

const allowList = (process.env.CORS_ORIGINS || '*').split(',').map(s=>s.trim()).filter(Boolean);
app.use(cors({
  origin: (origin, cb) => {
    if (!origin) return cb(null, true);
    if (allowList.includes('*')) return cb(null, true);
    const ok = allowList.some(p => p.startsWith('*.') ? origin.endsWith(p.replace('*.','')) : origin === p);
    cb(ok ? null : new Error('CORS blocked'), ok);
  }
}));
app.use(morgan('tiny'));
app.use(rateLimit({ windowMs: 60*1000, limit: 60 }));

const cache = new Map();
const setCache = (k,v,ttl=300000)=> cache.set(k,{v,exp:Date.now()+ttl});
const getCache = (k)=>{const o=cache.get(k); if(!o||o.exp<Date.now()) return null; return o.v;};

app.get('/', (req,res)=>res.json({ok:true,name:'RaidenX8 Zing Proxy',time:Date.now()}));
app.get('/healthz', (req,res)=>res.send('ok'));

app.get('/music/search', async (req,res)=>{
  try{
    const q = (req.query.q||'').toString().trim();
    if(!q) return res.status(400).json({error:'missing_q'});
    const key='s:'+q.toLowerCase(); const hit=getCache(key); if(hit) return res.json(hit);
    const data = await ZingMp3.search(q);
    const items = (data?.songs||[]).map(s=>({
      id:s.encodeId,title:s.title,artist:s.artistsNames,thumbnail:s.thumbnailM||s.thumbnail,duration:s.duration
    }));
    const payload={q,count:items.length,items}; setCache(key,payload,180000); res.json(payload);
  }catch(e){ res.status(500).json({error:'search_failed',detail:String(e)}); }
});

app.get('/music/stream', async (req,res)=>{
  try{
    const id = (req.query.id||'').toString().trim();
    if(!id) return res.status(400).json({error:'missing_id'});
    const key='u:'+id; const hit=getCache(key); if(hit){ if(req.query.redirect) return res.redirect(hit.url); return res.json(hit); }
    const song = await ZingMp3.getSong(id);
    const url = song?.data?.['320'] || song?.data?.['128'] || song?.data?.['lossless'] || song?.data?.['m4a'] || song?.data?.['hls'];
    if(!url) return res.status(404).json({error:'no_stream_url'});
    const payload={id,url}; setCache(key,payload,600000); if(req.query.redirect) return res.redirect(url); res.json(payload);
  }catch(e){ res.status(500).json({error:'stream_failed',detail:String(e)}); }
});

app.get('/music/lyric', async (req,res)=>{
  try{
    const id = (req.query.id||'').toString().trim();
    if(!id) return res.status(400).json({error:'missing_id'});
    const key='l:'+id; const hit=getCache(key); if(hit) return res.json(hit);
    const data = await ZingMp3.getLyric(id);
    const payload={id,lyric:data?.data?.file||null}; setCache(key,payload,600000); res.json(payload);
  }catch(e){ res.status(500).json({error:'lyric_failed',detail:String(e)}); }
});

const PORT = process.env.PORT || 8080;
app.listen(PORT, ()=> console.log('Zing proxy on :'+PORT));
