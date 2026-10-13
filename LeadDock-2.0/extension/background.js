// Delivers leads that were saved while LeadDock couldn't be reached (helper not installed yet / app closed).
importScripts('transport.js');

async function deliverWaitingLeads() {
  try {
    if ((await leaddockQueue()).length) await leaddockFlush();
  } catch (e) { /* try again on the next alarm */ }
  await leaddockBadge();
}

function schedule() {
  chrome.alarms.create('leaddock-deliver', { periodInMinutes: 5 });
}

chrome.runtime.onInstalled.addListener(() => { schedule(); deliverWaitingLeads(); });
chrome.runtime.onStartup.addListener(() => { schedule(); deliverWaitingLeads(); });
chrome.alarms.onAlarm.addListener(alarm => { if (alarm.name === 'leaddock-deliver') deliverWaitingLeads(); });
