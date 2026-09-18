(() => {
  'use strict';

  const canonicalHosts = new Set([
    'telegrab-signal-bot.vercel.app',
    'telegrab-signal-bot-fallahsajed-2126s-projects.vercel.app',
    'telegrab-signal-bot-git-main-fallahsajed-2126s-projects.vercel.app'
  ]);
  const params = new URLSearchParams(location.search);
  const host = location.hostname.toLowerCase();
  const active = host.endsWith('.vercel.app') &&
    !canonicalHosts.has(host) &&
    params.get('nexus_preview') === '1';

  const now = '2026-09-19T00:00:00+03:30';
  const later = '2026-10-19T00:00:00+03:30';

  const navigation = [
    {route:'home',label_fa:'خانه',icon:'home'},
    {route:'signals',label_fa:'سیگنال‌ها',icon:'signals'},
    {route:'charts',label_fa:'چارت',icon:'chart'},
    {route:'subscriptions',label_fa:'پلن‌ها',icon:'plans'},
    {route:'account',label_fa:'حساب من',icon:'account'}
  ];

  const plans = [];
  const planDefs = [
    ['vip','VIP','دسترسی VIP',19,true,false],
    ['autotrade','AUTO','AutoTrade',6,false,true],
    ['bundle','BUNDLE','VIP + AutoTrade',23,true,true]
  ];
  [30,90,180,365].forEach(days => {
    const multiplier = ({30:1,90:2.7,180:5,365:9})[days];
    planDefs.forEach(([category,prefix,title,base,vip,auto]) => plans.push({
      category,
      code:`${prefix}${days}`,
      title_fa:title,
      days,
      price_usdt:Number((base * multiplier).toFixed(0)),
      vip_access:vip,
      autotrade_access:auto
    }));
  });

  const bootstrap = {
    user:{id:990001,first_name:'کاربر',last_name:'Preview',username:'nexus_preview',level:{key:'gold',en:'GOLD'}},
    entitlements:{active:true,vip:true,autotrade:true,plan_code:'BUNDLE30',vip_expires_at:later,autotrade_expires_at:later},
    plans,
    links:{public_channel:'https://t.me/nexus_publicc',support:'https://t.me/nexus_publicc'},
    autotrade:{
      entitled:true,
      mt5:{account_number:'90001234',status:'ACTIVE',last_seen_at:now},
      open_positions:[],
      pending_orders:[],
      history:[]
    }
  };

  const home = {
    experience:{
      segment:'BUNDLE',
      lifecycle:'ACTIVE',
      features:{trades:true},
      navigation
    },
    spotlight:{},
    performance:{period:'30',total:28,wins:18,losses:7,be:3,win_rate:64.3,avg_rr:1.62,disclaimer_fa:'PREVIEW DATA — فقط برای بررسی رابط کاربری.'},
    recent_signals:[
      {id:'preview-101',code:'P101',symbol:'BTCUSDT',direction:'BUY',access:'FREE',status:'ACTIVE',published_at:now,locked:false},
      {id:'preview-102',code:'P102',symbol:'SOLUSDT',direction:'SELL',access:'VIP',status:'ACTIVE',published_at:'2026-09-18T18:20:00+03:30',locked:false},
      {id:'preview-099',code:'P099',symbol:'BTCUSDT',direction:'SELL',access:'FREE',status:'CLOSED',published_at:'2026-09-18T10:10:00+03:30',result:'WIN',result_label_fa:'سود · نمونه نمایشی',locked:false}
    ],
    subscription:{vip:true,autotrade:true,vip_expires_at:later,autotrade_expires_at:later}
  };

  const activeSignals = [
    {
      id:'preview-101',code:'P101',symbol:'BTCUSDT',timeframe:'5M',direction:'BUY',access:'FREE',status:'ACTIVE',
      published_at:now,locked:false,entry_price:68000,stop_loss:67650,risk_percent:1,
      targets:[{target_no:1,price:68400},{target_no:2,price:68800}],
      live:{status:'LIVE',current_price:68240,floating_pnl:4.25,current_r:.69,volume:.01,stop_loss:67650,take_profit:68800,age_seconds:2,pnl_state:'IN_PROFIT'},
      timeline:[
        {action:'PUBLISHED',label_fa:'انتشار سیگنال',detail_fa:'PREVIEW DATA',created_at:now},
        {action:'UPDATE',label_fa:'بروزرسانی',detail_fa:'نمونه Timeline برای بررسی UI',created_at:'2026-09-19T00:04:00+03:30'}
      ]
    },
    {
      id:'preview-102',code:'P102',symbol:'SOLUSDT',timeframe:'5M',direction:'SELL',access:'VIP',status:'ACTIVE',
      published_at:'2026-09-18T18:20:00+03:30',locked:false,entry_price:245,stop_loss:248,risk_percent:.75,
      targets:[{target_no:1,price:241},{target_no:2,price:237}],
      live:{status:'LIVE',current_price:246.1,floating_pnl:-2.10,current_r:-.37,volume:.1,stop_loss:248,take_profit:237,age_seconds:3,pnl_state:'IN_LOSS'},
      timeline:[{action:'PUBLISHED',label_fa:'انتشار سیگنال',detail_fa:'PREVIEW DATA',created_at:'2026-09-18T18:20:00+03:30'}]
    }
  ];

  const closedSignals = [
    {id:'preview-099',code:'P099',symbol:'BTCUSDT',direction:'SELL',access:'FREE',status:'CLOSED',published_at:'2026-09-18T10:10:00+03:30',closed_at:'2026-09-18T11:02:00+03:30',result:'WIN',result_label_fa:'سود · نمونه نمایشی',locked:false},
    {id:'preview-098',code:'P098',symbol:'SOLUSDT',direction:'BUY',access:'VIP',status:'CLOSED',published_at:'2026-09-17T14:30:00+03:30',closed_at:'2026-09-17T15:10:00+03:30',result:'LOSS',result_label_fa:'ضرر · نمونه نمایشی',locked:false}
  ];

  const overview = {
    summary:{total:28,wins:18,losses:7,be:3,win_rate:64.3},
    risk:{status:'OK',net_r:8.4,average_r:.30,profit_factor:1.84,max_drawdown_r:-2.1,current_losing_streak:0,maximum_losing_streak:2,equity_curve_r:[0,.8,.2,1.3,2.1,1.4,3.2,4.0,3.5,5.1,6.4,5.7,7.3,8.4]},
    methodology:{verification_note:'PREVIEW DATA — ساختار نمایشی Track Record برای بررسی UI.',drawdown_rule:'اعداد این Preview داده معاملاتی واقعی نیستند.'}
  };

  const performanceDetails = {
    symbols:[
      {symbol:'BTCUSDT',total:16,wins:11,losses:4,be:1,win_rate:68.8},
      {symbol:'SOLUSDT',total:12,wins:7,losses:3,be:2,win_rate:58.3}
    ],
    channels:{
      FREE:{total:12,wins:7,losses:3,be:2,win_rate:58.3},
      VIP:{total:16,wins:11,losses:4,be:1,win_rate:68.8}
    }
  };

  const performanceTrades = [
    {id:'pt1',symbol:'BTCUSDT',direction:'BUY',close_time:'2026-09-18T20:10:00+03:30',realized_r:1.4,result_value:1.4,result_unit:'R',result_source:'PREVIEW',locked:false},
    {id:'pt2',symbol:'SOLUSDT',direction:'SELL',close_time:'2026-09-18T17:20:00+03:30',realized_r:-1,result_value:-1,result_unit:'R',result_source:'PREVIEW',locked:false},
    {id:'pt3',symbol:'BTCUSDT',direction:'SELL',close_time:'2026-09-17T14:00:00+03:30',realized_r:2.1,result_value:2.1,result_unit:'R',result_source:'PREVIEW',locked:false}
  ];

  const account = {
    vip:{state:'ACTIVE',expires_at:later,remaining_days:30},
    autotrade:{state:'ACTIVE',setup_state:'CONNECTED',active:true,license_valid:true,mt5_bound:true,health:{state:'HEALTHY'},headline_fa:'AutoTrade',message_fa:'PREVIEW DATA — اتصال نمایشی برای بررسی UI.',mt5_account_masked:'****1234',last_seen_at:now,cta_action:'trades',cta_fa:'معاملات من'},
    licenses:{
      active:[{id:901,status:'ACTIVE',display_status:'ACTIVE',display_expires_at:later,vip_access:true,autotrade_access:true}],
      history:[{id:812,status:'EXPIRED',display_status:'EXPIRED',display_expires_at:'2026-08-19T00:00:00+03:30',vip_access:true,autotrade_access:false}]
    },
    payments_count:2,
    is_admin:false
  };

  const tradeHealth = {
    state:{state:'HEALTHY',last_sync_at:now},
    checks:{subscription:true,license:true,mt5_account:true,ea_connected:true},
    mt5:{account_number:'90001234'},
    open_count:2,
    pending_count:1
  };

  const openTrades = [
    {ticket:'91001',signal_code:'P101',symbol:'BTCUSDT',direction:'BUY',volume:.01,entry_price:68000,current_price:68240,stop_loss:67650,take_profit:68800,profit:4.25,status:'OPEN',last_seen_at:now},
    {ticket:'91002',signal_code:'P102',symbol:'SOLUSDT',direction:'SELL',volume:.1,entry_price:245,current_price:246.1,stop_loss:248,take_profit:237,profit:-2.10,status:'OPEN',last_seen_at:now}
  ];

  const pendingTrades = [
    {ticket:'92001',signal_code:'P103',symbol:'BTCUSDT',direction:'BUY_LIMIT',volume:.01,entry_price:67200,stop_loss:66800,take_profit:68000,status:'PENDING',last_seen_at:now}
  ];

  const historyTrades = [
    {id:'h1',signal_id:'P099',ticket:'90091',event_type:'CLOSE',status:'CLOSED',symbol:'BTCUSDT',direction:'SELL',volume:.01,entry_price:68100,exit_price:67680,profit:5.8,created_at:'2026-09-18T11:02:00+03:30'},
    {id:'h2',signal_id:'P098',ticket:'90082',event_type:'CLOSE',status:'CLOSED',symbol:'SOLUSDT',direction:'BUY',volume:.1,entry_price:242,exit_price:239.5,profit:-3.1,created_at:'2026-09-17T15:10:00+03:30'}
  ];

  function clone(value) {
    return value == null ? value : JSON.parse(JSON.stringify(value));
  }

  function query(path) {
    return new URL(path, location.origin);
  }

  function previewBadge() {
    if (!active || document.getElementById('nexusPreviewBadge')) return;
    const badge = document.createElement('div');
    badge.id = 'nexusPreviewBadge';
    badge.className = 'nexus-preview-badge';
    badge.textContent = 'UI PREVIEW · داده نمایشی';
    document.body.appendChild(badge);
    document.body.dataset.nexusPreview = '1';
  }

  async function resolve(path, options = {}) {
    if (!active) throw new Error('Preview API is disabled');
    const u = query(path);
    const p = u.pathname;

    if (p === '/bootstrap') return clone(bootstrap);
    if (p === '/experience') return clone(home.experience);
    if (p === '/home') return clone(home);
    if (p === '/plans') return {plans:clone(plans)};
    if (p === '/account/status') return clone(account);
    if (p === '/autotrade/status') return clone(tradeHealth);
    if (p === '/notifications') return {unread_count:2,items:[
      {id:'n1',source:'system',title_fa:'نسخه Preview',body_fa:'این داده فقط برای بررسی UI است.',created_at:now,is_read:false,destination:'home'},
      {id:'n2',source:'autotrade',title_fa:'نمونه اعلان AutoTrade',body_fa:'وضعیت نمایشی برای بررسی کارت اعلان.',created_at:'2026-09-18T20:00:00+03:30',is_read:false,destination:'trades'}
    ]};
    if (/^\/notifications\//.test(p) || p === '/events') return {ok:true};

    if (p === '/performance' || p === '/performance/overview') return clone(overview);
    if (p === '/performance/details') return clone(performanceDetails);
    if (p === '/performance/trades') return {total:performanceTrades.length,items:clone(performanceTrades)};
    if (p.startsWith('/performance/trades/')) {
      const id=decodeURIComponent(p.split('/').pop());
      const base=performanceTrades.find(x=>String(x.id)===id) || performanceTrades[0];
      return {trade:{...clone(base),initial_entry:68000,initial_sl:67650,initial_tp:68400,final_exit:68720,lifecycle:[
        {action:'PUBLISHED',detail_fa:'PREVIEW DATA',created_at:'2026-09-18T19:00:00+03:30'},
        {action:'CLOSED',detail_fa:'نمونه رویداد برای بررسی Timeline',value:'1.40R',created_at:base.close_time}
      ]},methodology:clone(overview.methodology)};
    }

    if (p === '/signals') {
      const state=(u.searchParams.get('state')||'ACTIVE').toUpperCase();
      const access=(u.searchParams.get('access')||'ALL').toUpperCase();
      let rows=state==='CLOSED' ? closedSignals : activeSignals;
      if(access!=='ALL') rows=rows.filter(x=>x.access===access);
      return {total:rows.length,items:clone(rows)};
    }
    if (p === '/signals/closed-calendar') {
      const month=u.searchParams.get('month') || '2026-09';
      const day=u.searchParams.get('day') || '2026-09-18';
      return {month,day,days:[
        {day:'2026-09-17',net_pnl:-3.1},
        {day:'2026-09-18',net_pnl:5.8}
      ],items:day==='2026-09-18' ? [{
        id:'preview-099',symbol:'BTCUSDT',direction:'SELL',result:'WIN',realized_pnl:5.8,
        published_at:'2026-09-18T10:10:00+03:30',closed_at:'2026-09-18T11:02:00+03:30'
      }] : []};
    }
    if (p.startsWith('/signals/')) {
      const id=decodeURIComponent(p.split('/').pop());
      return clone([...activeSignals,...closedSignals].find(x=>String(x.id)===id) || activeSignals[0]);
    }

    if (p === '/trades') {
      const state=(u.searchParams.get('state')||'OPEN').toUpperCase();
      const items=state==='PENDING' ? pendingTrades : state==='HISTORY' || state==='CLOSED' ? historyTrades : openTrades;
      return {items:clone(items),total:items.length};
    }
    if (p.startsWith('/trades/live/')) {
      const ticket=decodeURIComponent(p.split('/').pop());
      const trade=openTrades.find(x=>String(x.ticket)===ticket) || openTrades[0];
      return {...clone(trade),source_signal:{id:'preview-101',code:'P101',symbol:trade.symbol},timeline:[
        {event_type:'OPEN',label_fa:'باز شدن معامله',created_at:'2026-09-18T23:50:00+03:30'},
        {event_type:'UPDATE',label_fa:'بروزرسانی موقعیت',created_at:now}
      ]};
    }
    if (p.startsWith('/trades/')) {
      const id=decodeURIComponent(p.split('/').pop());
      const trade=historyTrades.find(x=>String(x.id)===id) || historyTrades[0];
      return {...clone(trade),timeline:[
        {event_type:'OPEN',label_fa:'ورود',created_at:'2026-09-18T10:10:00+03:30'},
        {event_type:'CLOSE',label_fa:'بستن',created_at:trade.created_at}
      ]};
    }

    if (p === '/quote') {
      let code='BUNDLE30';
      try { code=JSON.parse(options.body||'{}').plan_code || code; } catch (_) {}
      const plan=plans.find(x=>x.code===code) || plans[0];
      return {mode:'new',plan:clone(plan),duration_days:plan.days,base_usdt:plan.price_usdt,total_usdt:plan.price_usdt,setup_fee_usdt:0,upgrade_credit_usdt:0,discount_percent:0};
    }

    if (p === '/payments') return {items:[]};
    throw new Error(`PREVIEW fixture unavailable: ${p}`);
  }

  window.NexusPreviewMode = {active: () => active};
  window.NexusPreviewApi = {resolve};

  if (active) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', previewBadge);
    else previewBadge();
  }
})();
