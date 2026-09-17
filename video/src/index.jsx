import React from 'react';
import {AbsoluteFill, Composition, Sequence, interpolate, useCurrentFrame, registerRoot} from 'remotion';

const C={bg:'#020b18',panel:'#080d13',text:'#f4fbff',muted:'#81909c',accent:'#39d7c4'};
const base={fontFamily:'Arial, sans-serif',background:C.bg,color:C.text};

const Fade=({duration,children})=>{
  const f=useCurrentFrame();
  const opacity=interpolate(f,[0,12,Math.max(13,duration-12),duration],[0,1,1,0],{extrapolateLeft:'clamp',extrapolateRight:'clamp'});
  return <AbsoluteFill style={{opacity}}>{children}</AbsoluteFill>;
};

const NexusMark=()=> <div style={{width:250,height:250,borderRadius:70,border:`5px solid ${C.accent}`,display:'flex',alignItems:'center',justifyContent:'center',boxShadow:'0 0 80px rgba(57,215,196,.25)'}}><div style={{fontSize:126,fontWeight:900,color:C.accent}}>N</div></div>;

const Brand=({outro=false})=>{
  const f=useCurrentFrame();
  const scale=interpolate(f,[0,outro?40:80],[.94,outro?1:1.045],{extrapolateRight:'clamp'});
  return <AbsoluteFill style={{...base,alignItems:'center',justifyContent:'center',transform:`scale(${scale})`}}><NexusMark/><div style={{fontSize:outro?72:68,fontWeight:900,letterSpacing:9,marginTop:44}}>NEXUS</div><div style={{fontSize:outro?42:34,marginTop:20,color:C.muted}}>{outro?'Signals • Charts • Execution':'Trading Intelligence'}</div></AbsoluteFill>;
};

const Phone=({title,eyebrow,children,active})=><AbsoluteFill style={{...base,alignItems:'center',justifyContent:'center'}}><div style={{width:850,height:1540,borderRadius:64,background:C.panel,border:'2px solid #173044',boxShadow:'0 0 90px rgba(57,215,196,.12)',overflow:'hidden',padding:46,boxSizing:'border-box',position:'relative'}}><div style={{fontSize:25,letterSpacing:4,color:C.accent}}>{eyebrow}</div><div style={{fontSize:54,fontWeight:800,marginTop:12}}>{title}</div><div style={{marginTop:52}}>{children}</div><div style={{position:'absolute',bottom:48,left:45,right:45,display:'flex',justifyContent:'space-between',fontSize:19,color:C.muted}}>{['HOME','SIGNALS','CHARTS','PLANS','ACCOUNT'].map(x=><span key={x} style={{color:x===active?C.accent:C.muted,fontWeight:x===active?800:500}}>{x}</span>)}</div></div></AbsoluteFill>;

const Cards=()=> <div style={{display:'grid',gap:28}}>{['FREE SIGNAL','VIP SIGNAL'].map((x,i)=><div key={x} style={{padding:38,borderRadius:34,border:`2px solid ${i===1?C.accent:'#162735'}`,background:'#0b121b',fontSize:38}}><b>{x}</b><div style={{fontSize:25,color:C.muted,marginTop:14}}>{i?'Premium signal access':'Daily public signal access'}</div></div>)}</div>;

const Chart=()=> <div><div style={{display:'flex',gap:16,marginBottom:28}}>{['BTC','ETH','SOL','XAU'].map((x,i)=><span key={x} style={{padding:'14px 22px',borderRadius:22,background:i===0?C.accent:'#101a24',color:i===0?'#02100e':C.text,fontSize:26}}>{x}</span>)}</div><div style={{height:650,borderRadius:32,background:'#060b10',border:'1px solid #17232d',position:'relative',overflow:'hidden'}}><div style={{position:'absolute',inset:0,background:'repeating-linear-gradient(0deg,transparent,transparent 79px,#101a22 80px), repeating-linear-gradient(90deg,transparent,transparent 94px,#101a22 95px)',opacity:.7}}/><svg style={{position:'absolute',inset:0}} width="100%" height="100%" viewBox="0 0 760 650"><polyline points="0,480 80,430 140,470 210,320 280,350 350,250 430,310 500,180 580,230 650,130 760,170" fill="none" stroke={C.accent} strokeWidth="7" opacity=".9"/></svg><div style={{position:'absolute',top:24,left:28,fontSize:30}}>BTCUSDT</div><div style={{position:'absolute',bottom:24,right:28,color:C.accent,fontSize:24}}>DEMO VISUAL</div></div><div style={{display:'flex',gap:15,marginTop:24}}>{['1m','5m','15m','1h','1D'].map(x=><span key={x} style={{padding:'12px 19px',borderRadius:18,background:x==='5m'?C.accent:'#101a24',color:x==='5m'?'#02100e':C.text,fontSize:23}}>{x}</span>)}</div></div>;

const Overlay=({children})=><div style={{position:'absolute',left:100,right:100,bottom:115,fontSize:48,fontWeight:800,textAlign:'center',textShadow:'0 4px 25px #000'}}>{children}</div>;

const NexusLaunch=()=> <AbsoluteFill style={base}><Sequence from={0} durationInFrames={90}><Fade duration={90}><Brand/></Fade></Sequence><Sequence from={90} durationInFrames={120}><Fade duration={120}><Phone title="NEXUS" eyebrow="TRADING INTELLIGENCE" active="HOME"><div dir="rtl" style={{fontSize:46,fontWeight:700}}>مرکز هوشمند سیگنال و ابزارهای معاملاتی</div><div style={{height:300,marginTop:45,borderRadius:36,background:'linear-gradient(145deg,#0c1721,#071018)',border:'1px solid #173044'}}/></Phone><Overlay>Your Trading Hub</Overlay></Fade></Sequence><Sequence from={210} durationInFrames={120}><Fade duration={120}><Phone title="Signal Center" eyebrow="SIGNALS" active="SIGNALS"><Cards/></Phone><Overlay>Signals. Clear. Connected.</Overlay></Fade></Sequence><Sequence from={330} durationInFrames={150}><Fade duration={150}><Phone title="Live Charts" eyebrow="LIVE MARKET" active="CHARTS"><Chart/></Phone><Overlay>Live Market. One Screen.</Overlay></Fade></Sequence><Sequence from={480} durationInFrames={90}><Fade duration={90}><Phone title="Plans" eyebrow="AUTOTRADE" active="PLANS"><div style={{padding:42,borderRadius:38,background:'#0b121b',border:`2px solid ${C.accent}`,fontSize:42}}><b>AutoTrade</b><div style={{fontSize:27,color:C.muted,marginTop:18}}>Connect signals to your execution workflow.</div></div></Phone><Overlay>From Signal to Execution</Overlay></Fade></Sequence><Sequence from={570} durationInFrames={90}><Brand outro/></Sequence></AbsoluteFill>;

const RemotionRoot=()=> <Composition id="NexusLaunchV1" component={NexusLaunch} durationInFrames={660} fps={30} width={1080} height={1920}/>;
registerRoot(RemotionRoot);
