// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { OPENCLAW_DEVICE_AUTH_KEY, getOpenClawConnection, getOpenClawProxyConfig, openOpenClawWebSocket,
  getOpenClawDeviceGeneration, setOpenClawWsRelayEnabled } from "./_connection.js";
import { terminal } from "./_openshell.js";

const SCOPES = ["operator.read", "operator.write", "operator.admin"];
const CLIENT = { id:"gateway-client", version:"0.1.0", platform:"browser", mode:"ui" };
const LEGACY_CLIENT = { id:"openclaw-control-ui", version:"0.1.0", platform:"browser", mode:"webchat" };
const STORE = OPENCLAW_DEVICE_AUTH_KEY;
const VAULT = "nemoclaw_gateway_device_vault_v1";
const LIFETIME = 24 * 60 * 60 * 1000;
let active = null;

const encode = bytes => btoa(String.fromCharCode(...new Uint8Array(bytes)))
  .replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
const binding = connection => JSON.stringify([connection.rawUrl, connection.accessProvider, connection.accessSession]);
const assertCurrent = (connection, signal) => {
  signal?.throwIfAborted();
  const current = getOpenClawConnection();
  if (binding(connection) !== binding(current) || connection.token !== current.token)
    throw new Error("The connected gateway changed; run Connect again.");
};
const assertDeviceCurrent = (state, connection, signal) => {
  assertCurrent(connection, signal);
  if (state.generation !== getOpenClawDeviceGeneration())
    throw new Error("The connected gateway changed; run Connect again.");
};

// The tab stores only a random locator. IndexedDB retains nonextractable keys and
// authenticated ciphertext; neither format protects against same-origin script compromise.
function vaultRecord(handle, value) {
  return new Promise((resolve, reject) => {
    if (!globalThis.indexedDB) return reject(new Error("Allow browser storage to retain this course device."));
    const request = indexedDB.open(VAULT, 1);
    request.onupgradeneeded = () => request.result.createObjectStore("devices");
    request.onerror = request.onblocked = () => reject(new Error("Course device storage is unavailable."));
    request.onsuccess = () => {
      const db = request.result;
      try {
        const transaction = db.transaction("devices", "readwrite");
        const store = transaction.objectStore("devices");
        const operation = value === undefined ? store.get(handle) : value === null ? store.delete(handle) : store.put(value, handle);
        let result;
        operation.onsuccess = () => { result = operation.result; };
        const cursor = store.openCursor();
        cursor.onsuccess = () => {
          const item = cursor.result;
          if (!item) return;
          if (!Number.isFinite(item.value?.expiresAt) || item.value.expiresAt <= Date.now()) item.delete();
          item.continue();
        };
        transaction.oncomplete = () => { db.close(); resolve(result); };
        transaction.onerror = transaction.onabort = () => { db.close(); reject(new Error("Course device storage failed.")); };
      } catch (_) { db.close(); reject(new Error("Course device storage failed.")); }
    };
  });
}

const additionalData = (fingerprint, handle) => new TextEncoder().encode(JSON.stringify([VAULT, handle, fingerprint]));

export function assertOpenClawGatewayGrant(payload) {
  const scopes = payload?.auth?.scopes;
  if (!Array.isArray(scopes) || !SCOPES.every(scope => scopes.includes(scope)))
    throw new Error("Gateway authentication did not grant the required course permissions.");
  return payload;
}

async function identity(connection, signal) {
  assertCurrent(connection, signal);
  if (!globalThis.crypto?.subtle) throw new Error("OpenClaw device authentication requires HTTPS or localhost.");
  const generation = getOpenClawDeviceGeneration();
  const fingerprint = encode(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(binding(connection))));
  assertDeviceCurrent({generation},connection,signal);
  let handle = sessionStorage.getItem(STORE);
  if (handle && !/^[a-f0-9-]{36}$/.test(handle)) {
    // Discard the unpublished plaintext format rather than migrating its secrets.
    sessionStorage.removeItem(STORE); handle = null;
  }
  if (active?.fingerprint === fingerprint && active?.generation === generation && active?.handle === handle &&
      (!active.deviceToken || active.expiresAt > Date.now())) return active;
  let state;
  if (handle) {
    const saved = await vaultRecord(handle);
    try {
      if (saved?.expiresAt > Date.now() && saved.key?.extractable === false && saved.key.type === "private" &&
          saved.key.algorithm.name === "Ed25519" && saved.encryptionKey?.extractable === false &&
          saved.encryptionKey.algorithm.name === "AES-GCM" && saved.encryptionKey.algorithm.length === 256) {
        const decoded = await crypto.subtle.decrypt({name:"AES-GCM",iv:saved.iv,additionalData:additionalData(fingerprint,handle)},
          saved.encryptionKey,saved.ciphertext);
        const record = JSON.parse(new TextDecoder().decode(decoded));
        if (record.expiresAt === saved.expiresAt && /^[a-f0-9]{64}$/.test(record.id || "") && /^[A-Za-z0-9_-]{43}$/.test(record.publicKey || "") &&
            typeof record.deviceToken === "string" && record.deviceToken)
          state = {fingerprint,generation,handle,id:record.id,publicKey:record.publicKey,deviceToken:record.deviceToken,
            key:saved.key,encryptionKey:saved.encryptionKey,expiresAt:saved.expiresAt};
      }
    } catch (_) {}
    if (sessionStorage.getItem(STORE) !== handle) throw new Error("The connected gateway changed; run Connect again.");
  }
  if (!state) {
    const keys = await crypto.subtle.generateKey("Ed25519", false, ["sign", "verify"]);
    const raw = await crypto.subtle.exportKey("raw", keys.publicKey);
    const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", raw));
    state = { fingerprint, generation, handle:null, id:[...digest].map(byte => byte.toString(16).padStart(2,"0")).join(""),
      publicKey:encode(raw), key:keys.privateKey,
      encryptionKey:await crypto.subtle.generateKey({name:"AES-GCM",length:256},false,["encrypt","decrypt"]) };
  }
  assertDeviceCurrent(state, connection, signal);
  active = state;
  return state;
}

async function retainIdentity(state, connection, signal) {
  const handle = crypto.randomUUID();
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const expiresAt = Date.now()+LIFETIME;
  const plaintext = new TextEncoder().encode(JSON.stringify({id:state.id,publicKey:state.publicKey,deviceToken:state.deviceToken,expiresAt}));
  const ciphertext = await crypto.subtle.encrypt({name:"AES-GCM",iv,additionalData:additionalData(state.fingerprint,handle)},
    state.encryptionKey,plaintext);
  plaintext.fill(0);
  assertDeviceCurrent(state, connection, signal);
  try {
    await vaultRecord(handle,{key:state.key,encryptionKey:state.encryptionKey,iv,ciphertext,expiresAt});
    assertDeviceCurrent(state, connection, signal);
    sessionStorage.setItem(STORE,handle);
    state.handle = handle;
    state.expiresAt = expiresAt;
    return handle;
  } catch (error) {
    await vaultRecord(handle,null).catch(() => {});
    if (active === state) active = null;
    delete state.deviceToken;
    state.handle = null;
    throw error;
  }
}

async function signedParams(state, credential, challenge, deviceToken = false) {
  const { nonce, ts } = challenge || {};
  if (typeof nonce !== "string" || !nonce || !Number.isSafeInteger(ts) || ts < 0)
    throw new Error("Gateway sent an invalid device challenge.");
  const body = ["v2", state.id, CLIENT.id, CLIENT.mode, "operator", SCOPES.join(","), String(ts), credential, nonce].join("|");
  const signature = encode(await crypto.subtle.sign("Ed25519", state.key, new TextEncoder().encode(body)));
  return { minProtocol:4, maxProtocol:4, client:CLIENT, caps:["tool-events"], role:"operator", scopes:SCOPES,
    auth:deviceToken ? {deviceToken:credential} : {token:credential},
    device:{id:state.id,publicKey:state.publicKey,signature,signedAt:ts,nonce} };
}

export async function openclawGatewayConnectParams(token, challenge, signal = null, connection = getOpenClawConnection()) {
  assertCurrent(connection, signal);
  if (!active) {
    // Restore a previously authorized device after a course-page navigation.
    if (sessionStorage.getItem(STORE)) await identity(connection, signal);
  }
  if (active?.deviceToken) {
    const state = await identity(connection, signal);
    if (state.deviceToken) {
      const params = await signedParams(state, state.deviceToken, challenge, true);
      assertDeviceCurrent(state, connection, signal);
      return params;
    }
  }
  if (sessionStorage.getItem(STORE) === token)
    throw new Error("Course device storage changed; run Connect again.");
  return {minProtocol:4,maxProtocol:4,client:LEGACY_CLIENT,caps:["tool-events"],role:"operator",scopes:SCOPES,auth:{token}};
}

function handshake(connection, relay, state, credential, signal, deviceToken = false) {
  return new Promise((resolve, reject) => {
    let socket, settled = false;
    const id = crypto.randomUUID();
    const finish = (error, payload) => {
      if (settled) return;
      settled = true; clearTimeout(timer); signal?.removeEventListener("abort", stop);
      try { socket?.close(); } catch (_) {}
      error ? reject(error) : resolve(payload);
    };
    const stop = () => finish(signal.reason || new DOMException("Stopped", "AbortError"));
    const timer = setTimeout(() => finish(new Error("Gateway device handshake timed out.")), 15000);
    if (signal?.aborted) return stop();
    signal?.addEventListener("abort", stop, {once:true});
    try {
      socket = openOpenClawWebSocket(connection.rawUrl,"/cli/gateway",relay ? connection.accessSession : "",
        relay ? getOpenClawProxyConfig() : {enabled:false,base:""},connection.accessProvider);
    } catch (_) { finish(new Error("Gateway did not open.")); return; }
    socket.onmessage = async event => {
      let frame;
      try { frame = JSON.parse(event.data); } catch (_) { return; }
      if (frame.event === "connect.challenge") {
        try {
          assertDeviceCurrent(state,connection,signal);
          const value = await signedParams(state,credential,frame.payload,deviceToken);
          assertDeviceCurrent(state,connection,signal);
          if (!settled) socket.send(JSON.stringify({type:"req",id,method:"connect",params:value}));
        } catch (error) { finish(error); }
      } else if (frame.type === "res" && frame.id === id) {
        if (frame.ok) finish(null, frame.payload);
        else {
          const error = new Error("Gateway device authentication failed.");
          error.details = frame.error?.details;
          finish(error);
        }
      }
    };
    socket.onerror = () => finish(new Error("Gateway device transport failed."));
    socket.onclose = () => finish(new Error("Gateway closed during device authentication."));
  });
}

async function approveExactDevice(agentName, state, requestId, connection, signal) {
  assertDeviceCurrent(state,connection,signal);
  if (!/^[a-f0-9-]{36}$/.test(requestId || "")) throw new Error("Gateway did not identify its device pairing request.");
  const input = JSON.stringify({requestId,deviceId:state.id,publicKey:state.publicKey});
  // Approval reads its credential locally and returns only its outcome. Approve this
  // signed request/key and its bounded course scopes, never the latest request.
  const program = `const cp=require('node:child_process'),fs=require('node:fs'),crypto=require('node:crypto');
const input=${input},allowed=${JSON.stringify(SCOPES)};
(async()=>{let socket;try{
const binary=fs.realpathSync(cp.execFileSync('which',['openclaw'],{encoding:'utf8'}).trim());
const LocalGatewaySocket=require('node:module').createRequire(binary)('ws');
const dashboard=JSON.parse(cp.execFileSync('openclaw',['dashboard','--json'],{encoding:'utf8',stdio:['ignore','pipe','ignore'],timeout:30000}));
const token=new URLSearchParams(new URL(dashboard.url).hash.slice(1)).get('token'),url=new URL(dashboard.wsUrl);
if(!token||!['127.0.0.1','localhost','[::1]'].includes(url.hostname))throw Error();
socket=new LocalGatewaySocket(url);const calls=new Map();
const call=(method,params)=>new Promise((resolve,reject)=>{const id=crypto.randomUUID(),timer=setTimeout(()=>{calls.delete(id);reject(Error())},10000);calls.set(id,{resolve,reject,timer});socket.send(JSON.stringify({type:'req',id,method,params}))});
await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error()),10000);socket.on('error',()=>{clearTimeout(timer);reject(Error())});socket.on('message',async bytes=>{const frame=JSON.parse(bytes);if(frame.event==='connect.challenge'){try{await call('connect',{minProtocol:4,maxProtocol:4,client:{id:'gateway-client',version:'0.1.0',platform:'linux',mode:'backend'},role:'operator',scopes:['operator.admin','operator.approvals','operator.pairing','operator.questions','operator.read','operator.talk.secrets','operator.write'],auth:{token}});clearTimeout(timer);resolve()}catch{clearTimeout(timer);reject(Error())}}if(frame.type==='res'&&calls.has(frame.id)){const c=calls.get(frame.id);clearTimeout(c.timer);calls.delete(frame.id);frame.ok?c.resolve(frame.payload):c.reject(Error())}})});
const listed=await call('device.pair.list',{});
const owned=listed.pending.find(item=>item.requestId===input.requestId&&item.deviceId===input.deviceId&&item.publicKey===input.publicKey);
const paired=listed.paired.find(item=>item.deviceId===input.deviceId&&item.publicKey===input.publicKey);
if(owned){if(!Array.isArray(owned.scopes)||owned.scopes.some(scope=>!allowed.includes(scope)))throw Error();await call('device.pair.approve',{requestId:input.requestId})}else if(!paired)throw Error();
process.stdout.write(JSON.stringify({ok:true}));
}catch{process.stdout.write(JSON.stringify({ok:false}))}finally{socket?.close()}})();`;
  const result = await terminal(`openshell sandbox exec --name ${agentName} -- node -e eval(Buffer.from("${btoa(program)}","base64").toString())`,
    {baseUrl:connection.rawUrl,signal,totalMs:65000,idleMs:60000,openMs:10000});
  assertDeviceCurrent(state, connection, signal);
  let approved = false;
  try { approved = JSON.parse(result.output.trim()).ok === true; } catch (_) {}
  if (result.completion !== "exit" || result.exitCode !== 0 || !approved)
    throw new Error("The launchable could not authorize this course device. Check its device-pairing request.");
}

export async function reuseOpenClawGatewayAuth(connection, signal) {
  const state = await identity(connection, signal);
  if (!state.deviceToken) return "";
  for (const relay of [false, ...(connection.accessSession ? [true] : [])]) {
    try {
      const payload = await handshake(connection, relay, state, state.deviceToken, signal, true);
      assertOpenClawGatewayGrant(payload);
      assertDeviceCurrent(state, connection, signal);
      setOpenClawWsRelayEnabled(relay);
      return state.handle;
    } catch (_) { assertDeviceCurrent(state, connection, signal); }
  }
  return "";
}

export async function prepareOpenClawGatewayAuth(agentName, token, connection, signal) {
  const state = await identity(connection, signal);
  const routes = [false, ...(connection.accessSession ? [true] : [])];
  let lastError;
  for (const relay of routes) {
    try {
      let payload;
      try { payload = await handshake(connection, relay, state, token, signal); }
      catch (error) {
        assertDeviceCurrent(state, connection, signal);
        if (error.details?.code !== "PAIRING_REQUIRED") throw error;
        await approveExactDevice(agentName,state,error.details.requestId,connection,signal);
        payload = await handshake(connection, relay, state, token, signal);
      }
      assertOpenClawGatewayGrant(payload);
      if (!payload.auth.deviceToken) throw new Error("Gateway did not issue a device credential.");
      assertDeviceCurrent(state, connection, signal);
      state.deviceToken = payload.auth.deviceToken;
      const handle = await retainIdentity(state,connection,signal);
      active = state;
      setOpenClawWsRelayEnabled(relay);
      return handle;
    } catch (error) { assertDeviceCurrent(state, connection, signal); lastError = error; }
  }
  throw lastError;
}
