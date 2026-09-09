import { chromium } from '@playwright/test';
const session = process.argv[2];
const browser = await chromium.launch();
try {
  const page = await browser.newPage({viewport:{width:1440,height:1000}});
  await page.addInitScript(sid=>{
    localStorage.setItem('agent','windows-agent');
    localStorage.setItem('username','windows-test');
    localStorage.setItem('session:windows-agent:windows-test',sid);
  },session);
  await page.goto('http://127.0.0.1:18767/chat');
  await page.getByText('WINDOWS-COMPANION-OK',{exact:false}).first().waitFor({timeout:30000});
  await page.screenshot({path:'../artifacts/web/real-chat-desktop.png',fullPage:true});
  await page.goto('http://127.0.0.1:18767/admin');
  await page.getByRole('button',{name:'Agents',exact:true}).click();
  await page.getByText('Windows verification',{exact:true}).waitFor({timeout:30000});
  await page.screenshot({path:'../artifacts/web/real-admin-desktop.png',fullPage:true});
} finally { await browser.close(); }
