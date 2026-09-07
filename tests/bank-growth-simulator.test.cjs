// Run: node --test tests/bank-growth-simulator.test.cjs
// Test the exact embedded core shipped in the standalone artifact, not a copied formula.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const html = fs.readFileSync(path.join(__dirname, '../reports/usdcusdt/bank-growth-simulator.html'), 'utf8');
const scripts = [...html.matchAll(/<script(?: [^>]*)?>([\s\S]*?)<\/script>/g)];
scripts.forEach((m) => new vm.Script(m[1]));
const sandbox = {module: {exports: {}}};
vm.runInNewContext(scripts[0][1], sandbox);
const math = sandbox.module.exports;
const base = {initial:100,rate:1389.94,edge:0.001,days:365,mode:'COMPOUNDING',degrade:false,fill:80,downtime:5,ratio:100,fee:0,slippage:0,release:0};
const near = (actual, expected, tolerance=1e-10) => assert.ok(Math.abs(actual-expected) <= tolerance*Math.max(1,Math.abs(expected)), `${actual} != ${expected}`);

test('standalone HTML has no required external assets', () => {
  assert.equal(scripts.length, 2);
  assert.ok(!/<script[^>]+src=|<link[^>]+href=|@import|url\(https?:/i.test(html));
  assert.ok(html.includes('CANONICAL CAMPAIGN RULER = 100 USDT'));
});
test('canonical starting bank, zero edge, cycles and default M007 reference', () => {
  assert.equal(math.point(base,0).bank,100);
  assert.equal(math.point({...base,edge:0},730).bank,100);
  const p=math.point(base,30);
  near(p.cycles,1389.94*30);
  near(p.bank,100*Math.pow(1.00001,1389.94*30));
  assert.ok(p.bank>151&&p.bank<152);
  assert.equal(math.doublingCycles(.00001),69316);
  near(math.target(base,200).days,69316/1389.94);
});
test('fill and downtime act on cycles; incremental fee and slippage act on edge', () => {
  const c={...base,degrade:true,rate:1390,fee:.0001,slippage:.0002};
  near(math.effective(c).rate,1056.4);
  near(math.effective(c).edge,.000007);
  near(math.point(c,7).bank,100*Math.exp(1056.4*7*Math.log1p(.000007)));
});
test('all scenario rates independently start with the same initial bank', () => {
  for(const rate of [500,1000,1390,2000,3000,1389.94]) assert.equal(math.point(base,0,rate).bank,100);
});
test('monthly drag is post-growth, stepwise, and hits current equity', () => {
  const c={...base,release:1};
  near(math.point(c,29).bank,math.point(base,29).bank);
  near(math.point(c,30).bank,math.point(base,30).bank*.99);
  near(math.point(c,65).bank,math.point(base,65).bank*.99**2);
});
test('fixed exposure separates additive pnl, equity and release losses', () => {
  const c={...base,mode:'FIXED_NOTIONAL_100',release:1};
  const gain=100*.00001*1389.94;
  const expected=((100+30*gain)*.99+30*gain)*.99+5*gain;
  const p=math.point(c,65);
  near(p.bank,expected);
  near(p.additivePnl,65*gain);
  near(p.bank,100+p.additivePnl-p.releaseLoss);
  const altered=math.point({...c,initial:200,release:0},7);
  near(altered.additivePnl,7*gain); // exposure stays 100, not sandbox initial capital
});
test('zero activity, negative edge and absorbing auxiliary ruin', () => {
  assert.equal(math.point({...base,rate:0},365).bank,100);
  assert.equal(math.target({...base,edge:0},110),null);
  assert.equal(math.target({...base,edge:-.001},110),null);
  const c={...base,mode:'FIXED_NOTIONAL_100',edge:-1,rate:100,release:0};
  const p=math.point(c,365);
  assert.equal(p.bank,0);assert.equal(p.ruined,true);assert.equal(p.cycles,100);
  assert.equal(p.additivePnl,-100);
  assert.ok(math.point({...base,edge:-.001},30).bank<100);
});
test('targets account for monthly losses and bounded unreachable horizon', () => {
  assert.equal(math.target({...base,rate:0},110),null);
  const c={...base,release:3};
  const t=math.target(c,200);
  assert.ok(t.days>math.target(base,200).days);
  assert.ok(math.point(c,t.days).bank>=200-1e-8);
  assert.equal(math.target({...base,rate:1},1000),null);
});
test('import rejects incompatible, unordered, invalid and injected payloads', () => {
  const data={initial_capital:100,currency:'USDT',start:'2026-01-01',points:[{day:0,cycles:0,bank:100},{day:1,cycles:500,bank:101}]};
  assert.equal(math.validateReal(data,100).length,2);
  assert.throws(()=>math.validateReal(data,200));
  assert.throws(()=>math.validateReal({...data,points:[...data.points,{day:1,cycles:1,bank:102}]},100));
  assert.throws(()=>math.validateReal({...data,points:[{day:0,cycles:0,bank:'<script>'}]},100));
});
